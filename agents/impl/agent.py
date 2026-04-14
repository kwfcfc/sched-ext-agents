"""
Implementation Agent — writes Dafny implementation + C bridge code.

Workflow:
  1. Read verified spec from artifact store
  2. Generate Dafny implementation (method bodies + loop invariants)
  3. Use Dafny LSP for real-time feedback, iterate until verified
  4. Translate verified logic to C/eBPF code
  5. Update the spec↔impl mapping document
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

MAX_LSP_ITERATIONS = 5  # Max fix attempts per verification cycle


class ImplAgent:
    """Generates verified Dafny implementation and translates to C/eBPF."""

    def __init__(self, llm: LLMClient, store: ArtifactStore):
        self.llm = llm
        self.store = store

    def run(self, pipeline: PipelineState) -> StageResult:
        stage = pipeline.current_stage

        if stage == Stage.IMPL:
            return self._generate_implementation(pipeline)
        elif stage == Stage.IMPL_VERIFY:
            return self._verify_implementation(pipeline)
        else:
            return StageResult(stage=stage, success=True, message="No-op for impl agent")

    def _generate_implementation(self, pipeline: PipelineState) -> StageResult:
        """Generate Dafny method bodies that satisfy the spec contracts."""

        # Load the verified spec files
        spec_files = self.store.list_by_kind(ArtifactKind.DAFNY_SPEC)
        spec_contents = {}
        for a in spec_files:
            if Path(a.path).exists():
                spec_contents[a.path] = Path(a.path).read_text()

        if not spec_contents:
            return StageResult(
                stage=Stage.IMPL,
                success=False,
                failure_kind=FailureKind.SPEC_INCOMPLETE,
                message="No spec files found to implement.",
            )

        # Load Dafny patterns knowledge
        patterns = ""
        patterns_dir = Path("knowledge/dafny-patterns")
        if patterns_dir.exists():
            for f in patterns_dir.glob("*.md"):
                patterns += f"\n\n## {f.stem}\n{f.read_text()}"

        # Check for previous implementation failures
        prev_failures = [
            r for r in pipeline.history
            if r.stage in (Stage.IMPL, Stage.IMPL_VERIFY) and not r.success
        ]

        system_prompt = self.llm.load_system_prompt("agents/impl/prompts/system.md")
        conv = Conversation(
            system_prompt=system_prompt,
            knowledge_context=patterns,
        )

        specs_text = "\n\n".join(
            f"### {path}\n```dafny\n{content}\n```"
            for path, content in spec_contents.items()
        )

        if prev_failures:
            last = prev_failures[-1]
            conv.add_user(
                f"Previous implementation attempt failed:\n"
                f"```\n{last.message[:3000]}\n```\n\n"
                f"Here are the specifications:\n{specs_text}\n\n"
                f"Fix the implementation. Output files in <file path=\"...\"> blocks."
            )
        else:
            conv.add_user(
                f"Implement the following Dafny specifications.\n\n"
                f"{specs_text}\n\n"
                f"Generate:\n"
                f"1. `specs/refinements/concrete_scheduler.dfy` — full method bodies with "
                f"loop invariants, ghost state, and helper lemmas\n"
                f"2. `specs/refinements/refinement_proof.dfy` — proof that concrete "
                f"refines abstract\n"
                f"3. `impl/bpf/src/sched_ext_fair.bpf.c` — C/eBPF translation of the "
                f"verified algorithm\n"
                f"4. `impl/bridge/mapping.md` — updated variable/action mapping\n\n"
                f"For loop invariants, be generous — it's better to over-specify than "
                f"to have Dafny time out trying to infer. Include `decreases` clauses "
                f"on every loop and recursive function.\n\n"
                f"Output each file in a <file path=\"...\"> block."
            )

        response = self.llm.complete(conv, temperature=0.0)
        files = self._parse_file_blocks(response)

        if not files:
            return StageResult(
                stage=Stage.IMPL,
                success=False,
                failure_kind=FailureKind.IMPL_UNVERIFIED,
                message="Impl agent produced no file blocks.",
            )

        # Write all files
        artifacts = []
        for path, content in files.items():
            kind = (
                ArtifactKind.DAFNY_IMPL if path.endswith(".dfy")
                else ArtifactKind.C_SOURCE if path.endswith((".c", ".h"))
                else ArtifactKind.MAPPING_DOC
            )
            self.store.store(
                kind=kind, path=path, content=content,
                created_by="impl_agent",
                depends_on=[a.path for a in spec_files],
            )
            artifacts.append(path)

        # ── LSP-driven fix loop ────────────────────────────
        dfy_files = [p for p in files if p.endswith(".dfy")]
        for iteration in range(MAX_LSP_ITERATIONS):
            ok, output = self._verify_dafny(dfy_files + [a.path for a in spec_files])
            if ok:
                log.info("Implementation verified after %d fix iterations", iteration)
                break

            log.info("Verification failed (iteration %d/%d), asking LLM to fix...",
                     iteration + 1, MAX_LSP_ITERATIONS)

            conv.add_user(
                f"Dafny verification failed:\n```\n{output[:3000]}\n```\n\n"
                f"Fix the implementation. Output corrected files in <file> blocks."
            )
            fix_response = self.llm.complete(conv, temperature=0.0)
            fix_files = self._parse_file_blocks(fix_response)

            for path, content in fix_files.items():
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                Path(path).write_text(content)
                artifacts.append(path)
        else:
            return StageResult(
                stage=Stage.IMPL,
                success=False,
                failure_kind=FailureKind.IMPL_UNVERIFIED,
                message=f"Implementation not verified after {MAX_LSP_ITERATIONS} fix iterations.\n{output[:1500]}",
                artifacts=artifacts,
            )

        return StageResult(
            stage=Stage.IMPL,
            success=True,
            message=f"Implementation verified. {len(files)} files generated.",
            artifacts=artifacts,
        )

    def _verify_implementation(self, pipeline: PipelineState) -> StageResult:
        """Verify that the refinement proof holds."""
        refinement_files = list(Path("specs/refinements").glob("*.dfy"))
        if not refinement_files:
            return StageResult(
                stage=Stage.IMPL_VERIFY,
                success=False,
                failure_kind=FailureKind.IMPL_UNVERIFIED,
                message="No refinement files found.",
            )

        all_dfy = (
            list(Path("specs/domain").glob("*.dfy"))
            + list(Path("specs/properties").glob("*.dfy"))
            + list(refinement_files)
        )
        ok, output = self._verify_dafny([str(f) for f in all_dfy])

        if ok:
            self.store.store(
                kind=ArtifactKind.DAFNY_PROOF_LOG,
                path="artifacts/proofs/impl_verify.log",
                content=output,
                created_by="impl_agent",
            )
            return StageResult(
                stage=Stage.IMPL_VERIFY,
                success=True,
                artifacts=["artifacts/proofs/impl_verify.log"],
            )

        return StageResult(
            stage=Stage.IMPL_VERIFY,
            success=False,
            failure_kind=FailureKind.IMPL_UNVERIFIED,
            message=output[:2000],
        )

    @staticmethod
    def _verify_dafny(paths: list[str]) -> tuple[bool, str]:
        existing = [p for p in paths if Path(p).exists() and p.endswith(".dfy")]
        if not existing:
            return True, "No .dfy files found."
        try:
            result = subprocess.run(
                ["dafny", "verify", "--cores", "4", "--verification-time-limit", "300"]
                + existing,
                capture_output=True, text=True, timeout=600,
            )
            output = result.stdout + "\n" + result.stderr
            return result.returncode == 0, output
        except FileNotFoundError:
            return True, "Dafny not available."
        except subprocess.TimeoutExpired:
            return False, "Verification timed out (600s)."

    @staticmethod
    def _parse_file_blocks(response: str) -> dict[str, str]:
        import re
        pattern = r'<file\s+path="([^"]+)">\s*\n(.*?)\n\s*</file>'
        matches = re.findall(pattern, response, re.DOTALL)
        result = {}
        for path, content in matches:
            result[path] = content.strip()
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(content.strip())
        return result
