"""
Failure Router — decides which agent handles a given failure.

When the orchestrator receives a failed StageResult, it consults this router
to determine where to send the failure for remediation. The router considers:
  - The failure kind (e.g., spec inconsistency vs BPF verifier rejection)
  - The failure history (avoid infinite loops between agents)
  - The iteration budget remaining
"""

from __future__ import annotations
import logging

from agents.orchestrator.state_machine import (
    PipelineState, Stage, FailureKind, FAILURE_ROUTING,
)

log = logging.getLogger(__name__)

# If the same failure routes to the same stage 3 times, escalate
MAX_SAME_ROUTE_COUNT = 3


class FailureRouter:
    """Routes failures to the appropriate agent for remediation."""

    def route(self, pipeline: PipelineState, failure_kind: FailureKind) -> Stage:
        """Determine which stage should handle this failure."""
        default_target = FAILURE_ROUTING.get(failure_kind, Stage.SPEC_REVIEW)

        # Count how many times we've already routed to this target
        route_count = sum(
            1 for r in pipeline.history
            if not r.success and r.stage == default_target
        )

        if route_count >= MAX_SAME_ROUTE_COUNT:
            # Escalate: if we keep failing at impl, maybe it's a spec problem
            escalation = self._escalate(default_target)
            log.warning(
                "Failure %s routed to %s %d times, escalating to %s",
                failure_kind, default_target, route_count, escalation,
            )
            return escalation

        return default_target

    @staticmethod
    def _escalate(stuck_stage: Stage) -> Stage:
        """When a stage keeps failing, escalate to an earlier stage."""
        escalation_map = {
            Stage.IMPL:          Stage.SPEC_REVIEW,
            Stage.IMPL_VERIFY:   Stage.SPEC_DRAFTING,
            Stage.BPF_COMPILE:   Stage.IMPL,
            Stage.BPF_VERIFY:    Stage.IMPL,
            Stage.TEST_TRACE:    Stage.SPEC_REVIEW,
            Stage.TEST_FUZZ:     Stage.SPEC_DRAFTING,
            Stage.TEST_PERF:     Stage.IMPL,
        }
        return escalation_map.get(stuck_stage, Stage.SPEC_DRAFTING)
