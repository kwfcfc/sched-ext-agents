"""
Typed inter-agent messages.

Agents communicate through the ArtifactStore (files on disk), but sometimes
need structured metadata about what happened. These types provide that.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class DiagnosticLevel(Enum):
    ERROR   = "error"
    WARNING = "warning"
    INFO    = "info"


@dataclass
class DafnyDiagnostic:
    """A single diagnostic from Dafny verification."""
    file: str
    line: int
    column: int
    level: DiagnosticLevel
    message: str
    related_property: str = ""   # e.g. "fairness", "starvation_freedom"

    @property
    def is_proof_failure(self) -> bool:
        return self.level == DiagnosticLevel.ERROR and any(
            kw in self.message.lower()
            for kw in ["postcondition", "invariant", "assertion", "ensures", "requires"]
        )


@dataclass
class SpecReviewResult:
    """Output of the Verify Agent's spec review."""
    is_consistent: bool
    diagnostics: list[DafnyDiagnostic] = field(default_factory=list)
    missing_constraints: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass
class ImplVerifyResult:
    """Output of Dafny verification on implementation code."""
    all_proved: bool
    unproved_obligations: list[str] = field(default_factory=list)
    diagnostics: list[DafnyDiagnostic] = field(default_factory=list)
    proof_time_seconds: float = 0.0


@dataclass
class TraceStep:
    """A single step in an execution trace."""
    action: str              # e.g. "Enqueue", "Dispatch"
    pre_state: dict          # State before the action
    post_state: dict         # State after the action
    properties_held: list[str] = field(default_factory=list)


@dataclass
class TraceMismatch:
    """A divergence between Dafny trace and actual execution."""
    step_index: int
    action: str
    expected_state: dict
    actual_state: dict
    divergent_fields: list[str] = field(default_factory=list)
    diagnosis: str = ""      # Agent's analysis of the root cause


@dataclass
class TestVerdict:
    """Aggregated test results from the Test Agent."""
    trace_tests_passed: int = 0
    trace_tests_failed: int = 0
    trace_mismatches: list[TraceMismatch] = field(default_factory=list)
    fuzz_iterations: int = 0
    fuzz_crashes: int = 0
    fuzz_invariant_violations: int = 0
    perf_latency_p50_us: float = 0.0
    perf_latency_p99_us: float = 0.0
    perf_overhead_percent: float = 0.0
    perf_within_budget: bool = True
