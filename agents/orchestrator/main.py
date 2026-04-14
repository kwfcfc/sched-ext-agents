"""
Orchestrator Agent — main entry point.

Reads human requirements, drives the pipeline through all stages,
routes failures back to the appropriate agent, and enforces iteration limits.

Usage:
    python -m agents.orchestrator.main --requirements docs/requirements/fair-scheduler.md
    python -m agents.orchestrator.main --resume  # resume from last saved state
"""

from __future__ import annotations
import argparse
import logging
import time
from pathlib import Path

from agents.common.artifact_store import ArtifactStore, ArtifactKind
from agents.common.llm import LLMClient
from agents.orchestrator.state_machine import (
    PipelineState, Stage, StageResult, FailureKind,
)
from agents.orchestrator.router import FailureRouter
from agents.spec.agent import SpecAgent
from agents.verify.agent import VerifyAgent
from agents.impl.agent import ImplAgent
from agents.test.agent import TestAgent

log = logging.getLogger(__name__)


class Orchestrator:
    """Top-level pipeline controller."""

    def __init__(
        self,
        requirements_path: str,
        store: ArtifactStore,
        llm: LLMClient,
        max_iterations: int = 10,
    ):
        self.store = store
        self.llm = llm
        self.router = FailureRouter()

        # Initialize sub-agents
        self.agents = {
            Stage.SPEC_DRAFTING: SpecAgent(llm=llm, store=store),
            Stage.SPEC_REVIEW:   VerifyAgent(llm=llm, store=store),
            Stage.IMPL:          ImplAgent(llm=llm, store=store),
            Stage.IMPL_VERIFY:   ImplAgent(llm=llm, store=store),  # same agent, verify mode
            Stage.TEST_TRACE:    TestAgent(llm=llm, store=store, mode="trace"),
            Stage.TEST_FUZZ:     TestAgent(llm=llm, store=store, mode="fuzz"),
            Stage.TEST_PERF:     TestAgent(llm=llm, store=store, mode="perf"),
        }

        self.state = PipelineState(
            requirements_path=requirements_path,
            max_iterations=max_iterations,
        )

    def run(self) -> bool:
        """Run the pipeline to completion. Returns True if all stages pass."""
        requirements = Path(self.state.requirements_path).read_text()
        log.info("Starting pipeline for: %s", self.state.requirements_path)
        log.info("Requirements:\n%s", requirements[:500])

        # Store requirements as the first artifact
        self.store.store(
            kind=ArtifactKind.MAPPING_DOC,
            path="artifacts/requirements_snapshot.md",
            content=requirements,
            created_by="orchestrator",
        )

        # Advance to first real stage
        self.state.current_stage = Stage.SPEC_DRAFTING

        while self.state.current_stage != Stage.DONE:
            stage = self.state.current_stage
            log.info(
                "═══ Stage: %s (iteration %d/%d) ═══",
                stage.name, self.state.iteration + 1, self.state.max_iterations,
            )

            result = self._run_stage(stage)
            next_stage = self.state.advance(result)

            if result.success:
                log.info("✓ %s passed (%.1fs)", stage.name, result.duration_seconds)
            else:
                log.warning(
                    "✗ %s failed: %s → routing to %s",
                    stage.name, result.failure_kind, next_stage.name,
                )

            # Persist state after every stage (crash recovery)
            self.state.save()

        log.info("Pipeline completed in %d iterations.", self.state.iteration)
        return True

    def _run_stage(self, stage: Stage) -> StageResult:
        """Dispatch a single stage to the appropriate agent or tool."""
        t0 = time.time()

        try:
            if stage in self.agents:
                result = self.agents[stage].run(self.state)
            elif stage == Stage.BPF_COMPILE:
                result = self._run_bpf_compile()
            elif stage == Stage.BPF_VERIFY:
                result = self._run_bpf_verify()
            elif stage == Stage.REPORT:
                result = self._generate_report()
            else:
                result = StageResult(stage=stage, success=True, message="No-op stage")
        except Exception as e:
            log.exception("Stage %s crashed", stage.name)
            result = StageResult(
                stage=stage,
                success=False,
                failure_kind=FailureKind.SPEC_INCONSISTENT,
                message=f"Unhandled exception: {e}",
            )

        result.duration_seconds = time.time() - t0
        result.stage = stage
        return result

    def _run_bpf_compile(self) -> StageResult:
        """Compile eBPF module using clang."""
        import subprocess
        try:
            proc = subprocess.run(
                ["make", "-C", "impl/bpf"],
                capture_output=True, text=True, timeout=60,
            )
            if proc.returncode != 0:
                return StageResult(
                    stage=Stage.BPF_COMPILE,
                    success=False,
                    failure_kind=FailureKind.BPF_COMPILE_ERROR,
                    message=proc.stderr[:2000],
                )
            return StageResult(
                stage=Stage.BPF_COMPILE,
                success=True,
                artifacts=["impl/bpf/sched_ext_fair.bpf.o"],
            )
        except subprocess.TimeoutExpired:
            return StageResult(
                stage=Stage.BPF_COMPILE,
                success=False,
                failure_kind=FailureKind.BPF_COMPILE_ERROR,
                message="Compilation timed out after 60s",
            )

    def _run_bpf_verify(self) -> StageResult:
        """Dry-run BPF verifier via bpftool."""
        import subprocess
        try:
            proc = subprocess.run(
                ["sudo", "bpftool", "prog", "load",
                 "impl/bpf/sched_ext_fair.bpf.o", "/sys/fs/bpf/test_verify"],
                capture_output=True, text=True, timeout=30,
            )
            # Clean up
            subprocess.run(
                ["sudo", "rm", "-f", "/sys/fs/bpf/test_verify"],
                capture_output=True,
            )
            if proc.returncode != 0:
                return StageResult(
                    stage=Stage.BPF_VERIFY,
                    success=False,
                    failure_kind=FailureKind.BPF_VERIFIER_REJECT,
                    message=proc.stderr[:2000],
                )
            return StageResult(stage=Stage.BPF_VERIFY, success=True)
        except subprocess.TimeoutExpired:
            return StageResult(
                stage=Stage.BPF_VERIFY,
                success=False,
                failure_kind=FailureKind.BPF_VERIFIER_REJECT,
                message="BPF verifier timed out",
            )

    def _generate_report(self) -> StageResult:
        """Compile a verification report from all artifacts."""
        report_lines = [
            "# Verification Report",
            f"Requirements: {self.state.requirements_path}",
            f"Iterations: {self.state.iteration}",
            f"Duration: {time.time() - self.state.started_at:.0f}s",
            "",
            "## Stage History",
        ]
        for r in self.state.history:
            status = "PASS" if r.success else "FAIL"
            report_lines.append(
                f"- [{status}] {r.stage.name} ({r.duration_seconds:.1f}s)"
                + (f" — {r.failure_kind.value}: {r.message[:80]}" if not r.success else "")
            )

        report_lines.extend([
            "",
            "## Artifacts Produced",
        ])
        for meta in sorted(self.store._manifest.values(), key=lambda m: m.created_at):
            report_lines.append(f"- `{meta.path}` ({meta.kind.value}, v{meta.version})")

        content = "\n".join(report_lines)
        self.store.store(
            kind=ArtifactKind.TEST_REPORT,
            path="artifacts/reports/verification-report.md",
            content=content,
            created_by="orchestrator",
        )
        return StageResult(
            stage=Stage.REPORT,
            success=True,
            artifacts=["artifacts/reports/verification-report.md"],
        )


def main():
    parser = argparse.ArgumentParser(description="Run the verified sched_ext pipeline")
    parser.add_argument("--requirements", type=str, help="Path to requirements markdown")
    parser.add_argument("--resume", action="store_true", help="Resume from saved state")
    parser.add_argument("--max-iterations", type=int, default=10)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    store = ArtifactStore(root=Path("."))
    llm = LLMClient()

    if args.resume:
        state = PipelineState.load()
        orch = Orchestrator(
            requirements_path=state.requirements_path,
            store=store, llm=llm,
            max_iterations=state.max_iterations,
        )
        orch.state = state
    else:
        if not args.requirements:
            parser.error("--requirements is required unless --resume is used")
        orch = Orchestrator(
            requirements_path=args.requirements,
            store=store, llm=llm,
            max_iterations=args.max_iterations,
        )

    success = orch.run()
    raise SystemExit(0 if success else 1)


if __name__ == "__main__":
    main()
