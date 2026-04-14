"""
Pipeline state machine for the orchestrator agent.

States:
  INIT → SPEC_DRAFTING → SPEC_REVIEW → IMPL → IMPL_VERIFY →
  BPF_COMPILE → BPF_VERIFY → TEST_TRACE → TEST_FUZZ → TEST_PERF →
  REPORT → DONE

Transitions can go backward on failure (e.g., IMPL_VERIFY → SPEC_REVIEW
if the spec itself is found to be inconsistent).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional
import json
import time


class Stage(Enum):
    INIT          = auto()
    SPEC_DRAFTING = auto()
    SPEC_REVIEW   = auto()
    IMPL          = auto()
    IMPL_VERIFY   = auto()
    BPF_COMPILE   = auto()
    BPF_VERIFY    = auto()
    TEST_TRACE    = auto()
    TEST_FUZZ     = auto()
    TEST_PERF     = auto()
    REPORT        = auto()
    DONE          = auto()


class FailureKind(Enum):
    SPEC_INCONSISTENT   = "spec_inconsistent"     # Dafny verify on spec fails
    SPEC_INCOMPLETE     = "spec_incomplete"        # Missing property or domain element
    IMPL_UNVERIFIED     = "impl_unverified"        # Dafny can't prove impl meets spec
    INVARIANT_TOO_WEAK  = "invariant_too_weak"     # Loop invariant insufficient
    BPF_COMPILE_ERROR   = "bpf_compile_error"      # clang fails
    BPF_VERIFIER_REJECT = "bpf_verifier_reject"    # Kernel BPF verifier rejects
    TRACE_MISMATCH      = "trace_mismatch"         # Runtime state != Dafny trace
    FUZZ_CRASH          = "fuzz_crash"              # Crash or invariant violation
    PERF_REGRESSION     = "perf_regression"         # Below baseline
    TRANSLATION_BUG     = "translation_bug"         # Dafny→C semantic mismatch


# ── Routing table: which agent handles which failure ───────
FAILURE_ROUTING: dict[FailureKind, Stage] = {
    FailureKind.SPEC_INCONSISTENT:   Stage.SPEC_DRAFTING,
    FailureKind.SPEC_INCOMPLETE:     Stage.SPEC_DRAFTING,
    FailureKind.IMPL_UNVERIFIED:     Stage.IMPL,
    FailureKind.INVARIANT_TOO_WEAK:  Stage.IMPL,
    FailureKind.BPF_COMPILE_ERROR:   Stage.IMPL,
    FailureKind.BPF_VERIFIER_REJECT: Stage.IMPL,       # usually stack/loop issue
    FailureKind.TRACE_MISMATCH:      Stage.IMPL,       # translation bug
    FailureKind.FUZZ_CRASH:          Stage.SPEC_REVIEW, # might be spec gap
    FailureKind.PERF_REGRESSION:     Stage.IMPL,
    FailureKind.TRANSLATION_BUG:     Stage.IMPL,
}


@dataclass
class StageResult:
    stage: Stage
    success: bool
    failure_kind: Optional[FailureKind] = None
    message: str = ""
    artifacts: list[str] = field(default_factory=list)  # file paths produced
    duration_seconds: float = 0.0


@dataclass
class PipelineState:
    """Persistent state for the pipeline. Serialized to artifacts/pipeline_state.json."""
    current_stage: Stage = Stage.INIT
    iteration: int = 0
    max_iterations: int = 10
    history: list[StageResult] = field(default_factory=list)
    requirements_path: str = ""
    started_at: float = field(default_factory=time.time)

    # ── Forward transitions ────────────────────────────────
    FORWARD: dict[Stage, Stage] = {
        Stage.INIT:          Stage.SPEC_DRAFTING,
        Stage.SPEC_DRAFTING: Stage.SPEC_REVIEW,
        Stage.SPEC_REVIEW:   Stage.IMPL,
        Stage.IMPL:          Stage.IMPL_VERIFY,
        Stage.IMPL_VERIFY:   Stage.BPF_COMPILE,
        Stage.BPF_COMPILE:   Stage.BPF_VERIFY,
        Stage.BPF_VERIFY:    Stage.TEST_TRACE,
        Stage.TEST_TRACE:    Stage.TEST_FUZZ,
        Stage.TEST_FUZZ:     Stage.TEST_PERF,
        Stage.TEST_PERF:     Stage.REPORT,
        Stage.REPORT:        Stage.DONE,
    }

    def advance(self, result: StageResult) -> Stage:
        """Process a stage result and return the next stage."""
        self.history.append(result)
        self.iteration += 1

        if self.iteration >= self.max_iterations:
            raise RuntimeError(
                f"Pipeline exceeded {self.max_iterations} iterations. "
                f"Last failure: {result.failure_kind}"
            )

        if result.success:
            self.current_stage = self.FORWARD[result.stage]
        else:
            # Route backward based on failure kind
            target = FAILURE_ROUTING.get(result.failure_kind, Stage.SPEC_REVIEW)
            self.current_stage = target

        return self.current_stage

    def save(self, path: Path = Path("artifacts/pipeline_state.json")):
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "current_stage": self.current_stage.name,
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "requirements_path": self.requirements_path,
            "started_at": self.started_at,
            "history": [
                {
                    "stage": r.stage.name,
                    "success": r.success,
                    "failure_kind": r.failure_kind.value if r.failure_kind else None,
                    "message": r.message,
                    "artifacts": r.artifacts,
                    "duration_seconds": r.duration_seconds,
                }
                for r in self.history
            ],
        }
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: Path = Path("artifacts/pipeline_state.json")) -> PipelineState:
        data = json.loads(path.read_text())
        state = cls(
            current_stage=Stage[data["current_stage"]],
            iteration=data["iteration"],
            max_iterations=data["max_iterations"],
            requirements_path=data["requirements_path"],
            started_at=data["started_at"],
        )
        for h in data["history"]:
            state.history.append(StageResult(
                stage=Stage[h["stage"]],
                success=h["success"],
                failure_kind=FailureKind(h["failure_kind"]) if h["failure_kind"] else None,
                message=h["message"],
                artifacts=h["artifacts"],
                duration_seconds=h["duration_seconds"],
            ))
        return state
