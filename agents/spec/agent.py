"""
Spec Agent — translates human requirements into Dafny formal specifications.

Workflow:
  1. Read human requirements (markdown)
  2. Load domain knowledge (eBPF/sched_ext API docs)
  3. Generate domain model (types, helpers, traits)
  4. Extract formal properties (invariants, pre/post conditions)
  5. Write .dfy files to specs/
  6. Run `dafny verify` on the specs as a self-check
  7. If verification fails, iterate on the spec
"""

from __future__ import annotations
import logging
import subprocess
from pathlib import Path

from agents.common.llm import LLMClient, Conversation
from agents.common.artifact_store import ArtifactStore, ArtifactKind
from agents.orchestrator.state_machine import (
    PipelineState, StageResult, Stage, FailureKind,
)

log = logging.getLogger(__name__)

SYSTEM_PROMPT_PATH = "agents/spec/prompts/system.md"
KNOWLEDGE_DIR = Path("knowledge")


class SpecAgent:
    """Generates Dafny specifications from natural language requirements."""

    def __init__(self, llm: LLMClient, store: ArtifactStore):
        self.llm = llm
        self.store = store

    def run(self, pipeline: PipelineState) -> StageResult:
        requirements = Path(pipeline.requirements_path).read_text()

        # Load domain knowledge for context injection
        knowledge = self._load_knowledge()

        # Build conversation
        system_prompt = self.llm.load_system_prompt(SYSTEM_PROMPT_PATH)
        conv = Conversation(
            system_prompt=system_prompt,
            knowledge_context=knowledge,
        )

        # Check if we're iterating on a previous failure
        prev_failures = [
            r for r in pipeline.history
            if r.stage in (Stage.SPEC_DRAFTING, Stage.SPEC_REVIEW)
            and not r.success
        ]

        if prev_failures:
            last_failure = prev_failures[-1]
            conv.add_user(
                f"The previous specification attempt failed:\n"
                f"```\n{last_failure.message[:3000]}\n```\n\n"
                f"Here are the current requirements:\n\n{requirements}\n\n"
                f"Please fix the specification to address the failure above. "
                f"Output each .dfy file in a <file path=\"...\"> block."
            )
        else:
            conv.add_user(
                f"Here are the requirements for a sched_ext scheduler:\n\n"
                f"{requirements}\n\n"
                f"Generate the Dafny formal specification. Produce:\n"
                f"1. Domain model (types, helper contracts, sched_ext ops trait)\n"
                f"2. Safety/liveness properties (fairness, starvation, affinity)\n"
                f"3. eBPF safety constraints\n\n"
                f"Output each .dfy file in a <file path=\"specs/...\"> block."
            )

        # Get LLM response
        response = self.llm.complete(conv, temperature=0.0)

        # Parse file blocks from response
        files = self._parse_file_blocks(response)
        if not files:
            return StageResult(
                stage=Stage.SPEC_DRAFTING,
                success=False,
                failure_kind=FailureKind.SPEC_INCONSISTENT,
                message="Spec agent produced no file blocks in response.",
            )

        # Write files to disk and store as artifacts
        artifacts = []
        for path, content in files.items():
            full_path = Path(path)
            full_path.parent.mkdir(parents=True, exist_ok=True)
            self.store.store(
                kind=ArtifactKind.DAFNY_SPEC,
                path=path,
                content=content,
                created_by="spec_agent",
                tags={"iteration": str(pipeline.iteration)},
            )
            artifacts.append(path)
            log.info("Wrote spec: %s (%d chars)", path, len(content))

        # Self-check: run dafny verify on the generated specs
        verify_ok, verify_msg = self._self_verify(artifacts)

        if not verify_ok:
            # Try one self-correction pass
            log.info("Spec self-check failed, attempting correction...")
            conv.add_user(
                f"The specification you generated has verification errors:\n"
                f"```\n{verify_msg[:3000]}\n```\n\n"
                f"Please fix the errors and output corrected files."
            )
            response2 = self.llm.complete(conv, temperature=0.0)
            files2 = self._parse_file_blocks(response2)

            if files2:
                for path, content in files2.items():
                    self.store.store(
                        kind=ArtifactKind.DAFNY_SPEC,
                        path=path,
                        content=content,
                        created_by="spec_agent",
                        tags={"iteration": str(pipeline.iteration), "corrected": "true"},
                    )
                    artifacts.append(path)

                verify_ok, verify_msg = self._self_verify(
                    [p for p in files2.keys()]
                )

        if not verify_ok:
            return StageResult(
                stage=Stage.SPEC_DRAFTING,
                success=False,
                failure_kind=FailureKind.SPEC_INCONSISTENT,
                message=verify_msg[:2000],
                artifacts=artifacts,
            )

        return StageResult(
            stage=Stage.SPEC_DRAFTING,
            success=True,
            artifacts=artifacts,
            message=f"Generated {len(files)} spec files, all verified.",
        )

    def _load_knowledge(self) -> str:
        """Concatenate relevant knowledge files into a single context string."""
        sections = []
        knowledge_files = [
            "ebpf/sched_ext_ops_reference.md",
            "ebpf/helper_functions.md",
            "ebpf/verifier_constraints.md",
            "dafny-patterns/loop_invariants.md",
            "kernel/scheduler_internals.md",
        ]
        for rel_path in knowledge_files:
            full = KNOWLEDGE_DIR / rel_path
            if full.exists():
                sections.append(f"## {rel_path}\n\n{full.read_text()}")
        return "\n\n---\n\n".join(sections)

    def _self_verify(self, dfy_files: list[str]) -> tuple[bool, str]:
        """Run `dafny verify` on the given files. Returns (success, output)."""
        existing = [f for f in dfy_files if Path(f).exists() and f.endswith(".dfy")]
        if not existing:
            return True, "No .dfy files to verify."

        try:
            result = subprocess.run(
                ["dafny", "verify", "--cores", "4", "--verification-time-limit", "60"]
                + existing,
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                return True, result.stdout
            return False, result.stdout + "\n" + result.stderr
        except FileNotFoundError:
            log.warning("Dafny not found, skipping self-verify")
            return True, "Dafny not available, skipped."
        except subprocess.TimeoutExpired:
            return False, "Dafny verification timed out (120s)"

    @staticmethod
    def _parse_file_blocks(response: str) -> dict[str, str]:
        """Extract <file path=\"...\">...</file> blocks from LLM response."""
        import re
        pattern = r'<file\s+path="([^"]+)">\s*\n(.*?)\n\s*</file>'
        matches = re.findall(pattern, response, re.DOTALL)
        return {path: content.strip() for path, content in matches}
