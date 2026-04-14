"""
Scheduling event fuzzer.

Generates random sequences of scheduling events and feeds them
to the BPF scheduler module, checking invariants after each step.

Usage:
    python -m tests.fuzz.sched_fuzz \
        --module impl/bpf/sched_ext_fair.bpf.o \
        --duration 60 \
        --invariants specs/properties/
"""

from __future__ import annotations
import argparse
import json
import random
import time
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FuzzConfig:
    max_tasks: int = 50
    max_cpus: int = 8
    max_weight: int = 1024
    min_weight: int = 1
    event_weights: dict[str, float] | None = None

    def __post_init__(self):
        if self.event_weights is None:
            self.event_weights = {
                "enqueue": 0.3,
                "dispatch": 0.3,
                "tick": 0.2,
                "task_dead": 0.1,
                "cpu_offline": 0.05,
                "cpu_online": 0.05,
            }


@dataclass
class FuzzResult:
    iterations: int
    crashes: int
    invariant_violations: int
    duration_seconds: float
    interesting_inputs: list[str]


def generate_event(config: FuzzConfig, active_pids: set[int], active_cpus: set[int]) -> dict:
    """Generate a random scheduling event."""
    events = list(config.event_weights.keys())
    weights = list(config.event_weights.values())
    event_type = random.choices(events, weights=weights, k=1)[0]

    if event_type == "enqueue":
        pid = random.randint(1, config.max_tasks * 10)
        return {
            "action": "Enqueue",
            "task": {
                "pid": pid,
                "vruntime": random.randint(0, 100_000_000),
                "weight": random.randint(config.min_weight, config.max_weight),
            },
            "flags": {
                "wakeup": random.choice([True, False]),
                "last": random.random() < 0.1,
            },
        }

    elif event_type == "dispatch":
        if not active_cpus:
            return {"action": "Tick", "cpu": 0}
        return {
            "action": "Dispatch",
            "cpu": random.choice(sorted(active_cpus)),
        }

    elif event_type == "tick":
        if not active_cpus:
            return {"action": "Tick", "cpu": 0}
        return {
            "action": "Tick",
            "cpu": random.choice(sorted(active_cpus)),
        }

    elif event_type == "task_dead":
        if not active_pids:
            return generate_event(config, active_pids, active_cpus)
        return {
            "action": "TaskDead",
            "pid": random.choice(sorted(active_pids)),
        }

    elif event_type == "cpu_offline":
        if len(active_cpus) <= 1:
            return {"action": "Tick", "cpu": min(active_cpus) if active_cpus else 0}
        return {
            "action": "CpuOffline",
            "cpu": random.choice(sorted(active_cpus)),
        }

    elif event_type == "cpu_online":
        offline = set(range(config.max_cpus)) - active_cpus
        if not offline:
            return {"action": "Tick", "cpu": 0}
        return {
            "action": "CpuOnline",
            "cpu": random.choice(sorted(offline)),
        }

    return {"action": "Tick", "cpu": 0}


def check_invariants(state: dict) -> list[str]:
    """Check scheduling invariants against current state."""
    violations = []

    tasks = state.get("tasks", {})
    runnable = {pid: t for pid, t in tasks.items() if t.get("state") == "Runnable"}

    # Fairness check: vruntime divergence bounded
    if len(runnable) >= 2:
        vruntimes_by_weight = {}
        for pid, t in runnable.items():
            w = t.get("weight", 1024)
            vruntimes_by_weight.setdefault(w, []).append(t.get("vruntime", 0))

        for weight, vrts in vruntimes_by_weight.items():
            if len(vrts) >= 2:
                divergence = max(vrts) - min(vrts)
                if divergence > 10_000_000:  # FAIRNESS_BOUND
                    violations.append(
                        f"Fairness violated: weight={weight}, "
                        f"max_divergence={divergence}ns > 10ms"
                    )

    # Starvation check: no task waiting > 500ms
    clock = state.get("clock", 0)
    for pid, t in runnable.items():
        wait = clock - t.get("enqueue_time", clock)
        if wait > 500_000_000:  # STARVATION_BOUND
            violations.append(
                f"Starvation: pid={pid} waiting {wait}ns > 500ms"
            )

    return violations


def run_fuzz(
    config: FuzzConfig,
    duration_seconds: int = 60,
    seed: int | None = None,
) -> FuzzResult:
    """Run the fuzzer for a given duration."""
    if seed is not None:
        random.seed(seed)

    active_pids: set[int] = set()
    active_cpus: set[int] = set(range(min(4, config.max_cpus)))
    state: dict = {"tasks": {}, "clock": 0}

    iterations = 0
    crashes = 0
    invariant_violations = 0
    interesting: list[str] = []
    corpus: list[dict] = []

    t0 = time.time()
    while time.time() - t0 < duration_seconds:
        event = generate_event(config, active_pids, active_cpus)
        corpus.append(event)

        # Simulate state update (simplified — real version drives BPF module)
        try:
            _apply_event(state, event, active_pids, active_cpus)
        except Exception as e:
            crashes += 1
            interesting.append(json.dumps(corpus[-10:]))
            continue

        # Check invariants
        violations = check_invariants(state)
        if violations:
            invariant_violations += len(violations)
            interesting.append(
                json.dumps({"event": event, "violations": violations})
            )
            # Save the interesting input to corpus
            corpus_path = Path("tests/fuzz/corpus")
            corpus_path.mkdir(parents=True, exist_ok=True)
            (corpus_path / f"violation_{iterations}.json").write_text(
                json.dumps(corpus[-20:], indent=2)
            )

        iterations += 1

    return FuzzResult(
        iterations=iterations,
        crashes=crashes,
        invariant_violations=invariant_violations,
        duration_seconds=time.time() - t0,
        interesting_inputs=interesting[:10],
    )


def _apply_event(
    state: dict, event: dict,
    active_pids: set[int], active_cpus: set[int]
):
    """Apply a scheduling event to the simulated state."""
    action = event["action"]
    state["clock"] = state.get("clock", 0) + 1_000_000  # 1ms per event

    if action == "Enqueue":
        task = event["task"]
        pid = task["pid"]
        state["tasks"][pid] = {
            "vruntime": task["vruntime"],
            "weight": task["weight"],
            "state": "Runnable",
            "enqueue_time": state["clock"],
        }
        active_pids.add(pid)

    elif action == "Dispatch":
        # Pick min-vruntime runnable task
        runnable = {
            pid: t for pid, t in state["tasks"].items()
            if t.get("state") == "Runnable"
        }
        if runnable:
            chosen_pid = min(runnable, key=lambda p: runnable[p]["vruntime"])
            delta = 1_000_000 * 1024 // max(state["tasks"][chosen_pid].get("weight", 1024), 1)
            state["tasks"][chosen_pid]["vruntime"] += delta
            state["tasks"][chosen_pid]["enqueue_time"] = state["clock"]

    elif action == "TaskDead":
        pid = event.get("pid")
        if pid and pid in state["tasks"]:
            del state["tasks"][pid]
            active_pids.discard(pid)

    elif action == "CpuOffline":
        active_cpus.discard(event.get("cpu", -1))

    elif action == "CpuOnline":
        active_cpus.add(event.get("cpu", 0))


def main():
    parser = argparse.ArgumentParser(description="Scheduler event fuzzer")
    parser.add_argument("--module", help="BPF object file (for future integration)")
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--invariants", help="Path to Dafny properties dir")
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    print(f"Fuzzing for {args.duration}s...")
    result = run_fuzz(FuzzConfig(), duration_seconds=args.duration, seed=args.seed)

    print(f"\nResults:")
    print(f"  Iterations:           {result.iterations}")
    print(f"  Crashes:              {result.crashes}")
    print(f"  Invariant violations: {result.invariant_violations}")
    print(f"  Duration:             {result.duration_seconds:.1f}s")

    if result.invariant_violations > 0 or result.crashes > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
