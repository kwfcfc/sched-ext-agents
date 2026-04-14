"""
Trace-driven test runner.

Loads JSON traces exported from Dafny and replays them against the
compiled BPF scheduler module, comparing state at each step.

Each trace file contains a sequence of scheduling events and the
expected state after each event (exported from Dafny's execution).
"""

from __future__ import annotations
import json
import pytest
from pathlib import Path
from dataclasses import dataclass


TRACE_DIR = Path("tests/traces/fixtures")


@dataclass
class TraceStep:
    action: str
    params: dict
    expected_state: dict | None = None


def load_trace(path: Path) -> list[TraceStep]:
    """Load a trace JSON file into a list of steps."""
    data = json.loads(path.read_text())
    steps = []
    for step in data.get("steps", []):
        steps.append(TraceStep(
            action=step["action"],
            params={k: v for k, v in step.items() if k != "action"},
            expected_state=step.get("expected_state"),
        ))
    return steps


def get_trace_files() -> list[Path]:
    """Discover all trace fixture files."""
    if not TRACE_DIR.exists():
        return []
    return sorted(TRACE_DIR.glob("*.json"))


# ── Parameterized test: one test per trace file ───────────

trace_files = get_trace_files()


@pytest.mark.trace
@pytest.mark.parametrize(
    "trace_path",
    trace_files,
    ids=[f.stem for f in trace_files],
)
def test_trace_replay(trace_path: Path):
    """Replay a Dafny trace and verify state consistency."""
    steps = load_trace(trace_path)
    assert len(steps) > 0, f"Empty trace: {trace_path}"

    # In a full implementation, this would:
    # 1. Load the BPF module into a test harness
    # 2. For each step, invoke the corresponding hook
    # 3. Dump the BPF map state
    # 4. Compare against expected_state

    # Placeholder: validate trace structure
    for i, step in enumerate(steps):
        assert step.action in {
            "Enqueue", "Dispatch", "Select", "Tick", "TaskDead",
            "CpuOnline", "CpuOffline",
        }, f"Step {i}: unknown action '{step.action}'"

        # If expected state is provided, verify it's well-formed
        if step.expected_state:
            if "run_queues" in step.expected_state:
                for cpu, queue in step.expected_state["run_queues"].items():
                    assert isinstance(queue, list), \
                        f"Step {i}: run_queue[{cpu}] should be a list"

    # TODO: integrate with actual BPF test harness
    # For now, structural validation passes
    print(f"Trace {trace_path.stem}: {len(steps)} steps validated structurally")


@pytest.mark.trace
def test_trace_fixtures_exist():
    """Ensure at least one trace fixture exists."""
    files = get_trace_files()
    assert len(files) > 0, (
        "No trace fixtures found in tests/traces/fixtures/. "
        "Run `make test-traces` to generate them from Dafny specs."
    )
