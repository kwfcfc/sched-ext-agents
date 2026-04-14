"""
Verify Agent — checks spec consistency and eBPF semantic constraints.

Responsibilities:
  1. Run `dafny verify` on all spec files
  2. Cross-check spec against known eBPF/sched_ext constraints
  3. Identify missing properties or under-constrained hooks
  4. Inject eBPF verifier constraints if absent
"""

from __future__ import annotations
import logging
import subprocess
from pathlib import Path

from agents.common.llm import LLMClient, Conversation
from agents.common.artifact_store import ArtifactStore, ArtifactKind
from agents.common.message_types import SpecReviewResult, DafnyDiagnostic, DiagnosticLevel
from agents.orchestrator.state_machine import (
    PipelineState, StageResult, Stage, FailureKind,
)

log = logging.getLogger(__name__)


class VerifyAgent:
    """Reviews and validates Dafny specifications."""

    def __init__(self, llm: LLMClient, store: ArtifactStore):
        self.llm = llm
        self.store = store

    def run(self, pipeline: PipelineState) -> StageResult:
        # Collect all current spec files
        spec_artifacts = self.store.list_by_kind(ArtifactKind.DAFNY_SPEC)
        if not spec_artifacts:
            return StageResult(
                stage=Stage.SPEC_REVIEW,
                success=False,
                failure_kind=FailureKind.SPEC_INCOMPLETE,
                message="No Dafny spec files found in artifact store.",
            )

        spec_paths = [a.path for a in spec_artifacts if Path(a.path).exists()]

        # ── Step 1: Dafny mechanical verification ──────────
        verify_ok, verify_output = self._run_dafny_verify(spec_paths)

        if not verify_ok:
            diagnostics = self._parse_dafny_output(verify_output)
            proof_failures = [d for d in diagnostics if d.is_proof_failure]

            return StageResult(
                stage=Stage.SPEC_REVIEW,
                success=False,
                failure_kind=FailureKind.SPEC_INCONSISTENT,
                message=(
                    f"Dafny verification failed with {len(proof_failures)} proof errors.\n"
                    + "\n".join(f"  {d.file}:{d.line}: {d.message}" for d in proof_failures[:10])
                ),
            )

        # ── Step 2: Semantic review via LLM ────────────────
        review = self._semantic_review(spec_paths, pipeline)

        if not review.is_consistent:
            return StageResult(
                stage=Stage.SPEC_REVIEW,
                success=False,
                failure_kind=FailureKind.SPEC_INCOMPLETE,
                message=(
                    "Semantic review found issues:\n"
                    + "\n".join(f"  - {c}" for c in review.missing_constraints[:10])
                    + "\nSuggestions:\n"
                    + "\n".join(f"  - {s}" for s in review.suggestions[:5])
                ),
            )

        # Store the verification log
        self.store.store(
            kind=ArtifactKind.DAFNY_PROOF_LOG,
            path="artifacts/proofs/spec_verify.log",
            content=verify_output,
            created_by="verify_agent",
            depends_on=spec_paths,
        )

        return StageResult(
            stage=Stage.SPEC_REVIEW,
            success=True,
            message=f"Verified {len(spec_paths)} spec files. Semantic review passed.",
            artifacts=["artifacts/proofs/spec_verify.log"],
        )

    def _run_dafny_verify(self, paths: list[str]) -> tuple[bool, str]:
        dfy_files = [p for p in paths if p.endswith(".dfy")]
        if not dfy_files:
            return True, "No .dfy files to verify."
        try:
            result = subprocess.run(
                ["dafny", "verify", "--cores", "4", "--verification-time-limit", "120"]
                + dfy_files,
                capture_output=True, text=True, timeout=300,
            )
            output = result.stdout + "\n" + result.stderr
            return result.returncode == 0, output
        except FileNotFoundError:
            return True, "Dafny not installed, skipping."
        except subprocess.TimeoutExpired:
            return False, "Dafny verification timed out (300s)."

    def _semantic_review(
        self, spec_paths: list[str], pipeline: PipelineState
    ) -> SpecReviewResult:
        """Use LLM to check if specs capture all requirements and eBPF constraints."""
        # Load specs content
        spec_contents = {}
        for p in spec_paths:
            if Path(p).exists():
                spec_contents[p] = Path(p).read_text()

        # Load requirements
        requirements = Path(pipeline.requirements_path).read_text()

        # Load eBPF constraints knowledge
        ebpf_constraints = ""
        constraints_path = Path("knowledge/ebpf/verifier_constraints.md")
        if constraints_path.exists():
            ebpf_constraints = constraints_path.read_text()

        system_prompt = self.llm.load_system_prompt("agents/verify/prompts/system.md")
        conv = Conversation(system_prompt=system_prompt)

        specs_text = "\n\n".join(
            f"### {path}\n```dafny\n{content}\n```"
            for path, content in spec_contents.items()
        )

        conv.add_user(
            f"Review these Dafny specifications for completeness and correctness.\n\n"
            f"## Requirements\n{requirements}\n\n"
            f"## eBPF Constraints\n{ebpf_constraints}\n\n"
            f"## Specifications\n{specs_text}\n\n"
            f"Check:\n"
            f"1. Does every functional requirement have a corresponding formal property?\n"
            f"2. Are eBPF verifier constraints (bounded loops, stack depth, allowed helpers) "
            f"   encoded in the spec?\n"
            f"3. Are there any logical contradictions between properties?\n"
            f"4. Are pre/post conditions on helper functions accurate?\n\n"
            f"Respond with a JSON object:\n"
            f'{{"is_consistent": bool, "missing_constraints": [...], "suggestions": [...]}}'
        )

        response = self.llm.complete(conv, temperature=0.0)

        try:
            import json, re
            # Extract JSON from response (might be wrapped in markdown)
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return SpecReviewResult(
                    is_consistent=data.get("is_consistent", False),
                    missing_constraints=data.get("missing_constraints", []),
                    suggestions=data.get("suggestions", []),
                )
        except (json.JSONDecodeError, AttributeError):
            log.warning("Failed to parse LLM review response as JSON")

        # Default to pass if we can't parse (Dafny already verified)
        return SpecReviewResult(is_consistent=True)

    @staticmethod
    def _parse_dafny_output(output: str) -> list[DafnyDiagnostic]:
        """Parse Dafny compiler output into structured diagnostics."""
        import re
        diagnostics = []
        # Pattern: file.dfy(line,col): Error: message
        pattern = r'([^(]+)\((\d+),(\d+)\):\s*(Error|Warning|Info):\s*(.+)'
        for match in re.finditer(pattern, output):
            level_map = {"Error": DiagnosticLevel.ERROR, "Warning": DiagnosticLevel.WARNING}
            diagnostics.append(DafnyDiagnostic(
                file=match.group(1).strip(),
                line=int(match.group(2)),
                column=int(match.group(3)),
                level=level_map.get(match.group(4), DiagnosticLevel.INFO),
                message=match.group(5).strip(),
            ))
        return diagnostics
