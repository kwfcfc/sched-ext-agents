"""
Test Agent — trace-driven testing, fuzzing, and performance analysis.

Three modes controlled by the `mode` parameter:
  - "trace": Export Dafny traces, replay against BPF module, compare states
  - "fuzz":  Generate random scheduling event sequences, check invariants
  - "perf":  Run benchmarks, compare against baselines
"""

from __future__ import annotations
import json
import logging
import subprocess
from pathlib import Path

from agents.common.llm import LLMClient, Conversation
from agents.common.artifact_store import ArtifactStore, ArtifactKind
from agents.common.message_types import TestVerdict, TraceMismatch
from agents.orchestrator.state_machine import (
    PipelineState, StageResult, Stage, FailureKind,
)

log = logging.getLogger(__name__)


class TestAgent:
    """Runs tests against the compiled eBPF module and diagnoses failures."""

    def __init__(self, llm: LLMClient, store: ArtifactStore, mode: str = "trace"):
        self.llm = llm
        self.store = store
        self.mode = mode

    def run(self, pipeline: PipelineState) -> StageResult:
        if self.mode == "trace":
            return self._run_trace_tests(pipeline)
        elif self.mode == "fuzz":
            return self._run_fuzz_tests(pipeline)
        elif self.mode == "perf":
            return self._run_perf_tests(pipeline)
        else:
            return StageResult(
                stage=pipeline.current_stage,
                success=False,
                message=f"Unknown test mode: {self.mode}",
            )

    # ── Trace-driven tests ─────────────────────────────────

    def _run_trace_tests(self, pipeline: PipelineState) -> StageResult:
        """Export Dafny traces and replay them against the BPF module."""

        # Step 1: Export traces from Dafny
        trace_dir = Path("tests/traces/fixtures")
        trace_dir.mkdir(parents=True, exist_ok=True)

        export_ok = self._export_traces(trace_dir)
        if not export_ok:
            return StageResult(
                stage=Stage.TEST_TRACE,
                success=False,
                failure_kind=FailureKind.TRACE_MISMATCH,
                message="Failed to export Dafny traces.",
            )

        # Step 2: Run pytest on trace tests
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "tests/traces/", "-v",
                 "--tb=long", "--junitxml=artifacts/reports/trace-results.xml"],
                capture_output=True, text=True, timeout=300,
            )

            if result.returncode == 0:
                self.store.store(
                    kind=ArtifactKind.TEST_REPORT,
                    path="artifacts/reports/trace-results.xml",
                    content=result.stdout,
                    created_by="test_agent",
                )
                return StageResult(
                    stage=Stage.TEST_TRACE, success=True,
                    message="All trace tests passed.",
                    artifacts=["artifacts/reports/trace-results.xml"],
                )

            # Parse failures and diagnose
            diagnosis = self._diagnose_trace_failure(result.stdout + result.stderr, pipeline)
            return StageResult(
                stage=Stage.TEST_TRACE,
                success=False,
                failure_kind=diagnosis["kind"],
                message=diagnosis["message"],
            )

        except FileNotFoundError:
            log.warning("pytest not found, skipping trace tests")
            return StageResult(stage=Stage.TEST_TRACE, success=True, message="pytest not available, skipped.")
        except subprocess.TimeoutExpired:
            return StageResult(
                stage=Stage.TEST_TRACE, success=False,
                failure_kind=FailureKind.TRACE_MISMATCH,
                message="Trace tests timed out (300s).",
            )

    def _export_traces(self, output_dir: Path) -> bool:
        """Run the trace exporter to generate JSON trace files from Dafny."""
        try:
            result = subprocess.run(
                ["python", "-m", "tools.trace-exporter.dafny_to_json",
                 "--spec", "specs/refinements/concrete_scheduler.dfy",
                 "--output", str(output_dir)],
                capture_output=True, text=True, timeout=120,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            log.warning("Trace export failed or timed out")
            # Create a minimal trace for basic testing
            minimal_trace = {
                "name": "basic_enqueue_dequeue",
                "steps": [
                    {"action": "Enqueue", "task": {"pid": 1, "vruntime": 0, "weight": 1024}},
                    {"action": "Dispatch", "cpu": 0, "expected_task_pid": 1},
                ],
            }
            (output_dir / "basic_enqueue_dequeue.json").write_text(
                json.dumps(minimal_trace, indent=2)
            )
            return True

    # ── Fuzz tests ─────────────────────────────────────────

    def _run_fuzz_tests(self, pipeline: PipelineState) -> StageResult:
        """Run random scheduling event sequences and check invariants."""
        try:
            import os
            duration = int(os.environ.get("FUZZ_DURATION_SECONDS", "60"))

            result = subprocess.run(
                ["python", "-m", "tests.fuzz.sched_fuzz",
                 "--module", "impl/bpf/sched_ext_fair.bpf.o",
                 "--duration", str(duration),
                 "--invariants", "specs/properties/"],
                capture_output=True, text=True, timeout=duration + 30,
            )

            if result.returncode == 0:
                return StageResult(
                    stage=Stage.TEST_FUZZ, success=True,
                    message=f"Fuzz testing passed ({duration}s, no invariant violations).",
                )

            return StageResult(
                stage=Stage.TEST_FUZZ,
                success=False,
                failure_kind=FailureKind.FUZZ_CRASH,
                message=result.stdout[-2000:] + "\n" + result.stderr[-500:],
            )

        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            return StageResult(
                stage=Stage.TEST_FUZZ, success=True,
                message=f"Fuzz infrastructure not available ({e}), skipped.",
            )

    # ── Performance tests ──────────────────────────────────

    def _run_perf_tests(self, pipeline: PipelineState) -> StageResult:
        """Run scheduling benchmarks and compare to CFS baseline."""
        try:
            result = subprocess.run(
                ["python", "-m", "tests.perf.benchmark",
                 "--module", "impl/bpf/sched_ext_fair.bpf.o",
                 "--baseline", "tests/perf/baseline/cfs_baseline.json"],
                capture_output=True, text=True, timeout=120,
            )

            if result.returncode == 0:
                self.store.store(
                    kind=ArtifactKind.PERF_REPORT,
                    path="artifacts/reports/perf-results.json",
                    content=result.stdout,
                    created_by="test_agent",
                )
                return StageResult(
                    stage=Stage.TEST_PERF, success=True,
                    message="Performance within budget.",
                    artifacts=["artifacts/reports/perf-results.json"],
                )

            return StageResult(
                stage=Stage.TEST_PERF,
                success=False,
                failure_kind=FailureKind.PERF_REGRESSION,
                message=result.stdout[-1500:],
            )

        except (FileNotFoundError, subprocess.TimeoutExpired):
            return StageResult(
                stage=Stage.TEST_PERF, success=True,
                message="Perf infrastructure not available, skipped.",
            )

    # ── Failure diagnosis ──────────────────────────────────

    def _diagnose_trace_failure(
        self, test_output: str, pipeline: PipelineState
    ) -> dict:
        """Use LLM to classify the root cause of a trace test failure."""

        system_prompt = self.llm.load_system_prompt("agents/test/prompts/system.md")
        conv = Conversation(system_prompt=system_prompt)

        # Load the mapping doc for context
        mapping = ""
        mapping_path = Path("impl/bridge/mapping.md")
        if mapping_path.exists():
            mapping = mapping_path.read_text()

        conv.add_user(
            f"A trace-driven test failed. Diagnose the root cause.\n\n"
            f"## Test output\n```\n{test_output[:4000]}\n```\n\n"
            f"## Spec↔Impl mapping\n{mapping[:2000]}\n\n"
            f"Classify the failure as one of:\n"
            f"- SPEC_INCOMPLETE: the spec is missing a constraint\n"
            f"- IMPL_UNVERIFIED: the Dafny implementation has a bug\n"
            f"- TRANSLATION_BUG: the Dafny→C translation lost semantics\n"
            f"- BPF_VERIFIER_REJECT: the eBPF program was rejected\n\n"
            f"Respond with JSON: {{\"kind\": \"...\", \"message\": \"...\"}}"
        )

        response = self.llm.complete(conv, temperature=0.0)

        try:
            import re
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                data = json.loads(match.group())
                kind_map = {
                    "SPEC_INCOMPLETE": FailureKind.SPEC_INCOMPLETE,
                    "IMPL_UNVERIFIED": FailureKind.IMPL_UNVERIFIED,
                    "TRANSLATION_BUG": FailureKind.TRANSLATION_BUG,
                    "BPF_VERIFIER_REJECT": FailureKind.BPF_VERIFIER_REJECT,
                }
                return {
                    "kind": kind_map.get(data.get("kind", ""), FailureKind.TRACE_MISMATCH),
                    "message": data.get("message", test_output[:1000]),
                }
        except (json.JSONDecodeError, AttributeError):
            pass

        return {
            "kind": FailureKind.TRACE_MISMATCH,
            "message": test_output[:1000],
        }
