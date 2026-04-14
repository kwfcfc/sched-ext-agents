# Requirements: Fair CPU Scheduler (sched_ext)

## Overview

Build a Linux sched_ext scheduler that implements proportional fair scheduling
based on virtual runtime (vruntime), similar to CFS but running as a BPF program.

## Functional Requirements

### FR-1: Proportional fairness
Tasks with equal weight must receive equal CPU time over any window of 100ms or longer.
Tasks with different weights receive CPU time proportional to their weight ratio.

### FR-2: Starvation freedom
No runnable task may wait more than 500ms without being scheduled, regardless of
system load or the presence of higher-weight tasks.

### FR-3: CPU affinity
The scheduler must respect `cpus_allowed` masks. A task must never be dispatched
to a CPU outside its affinity set.

### FR-4: Idle CPU selection
When a task wakes up, select the idlest CPU within the task's affinity set.
Prefer the previous CPU if it is idle (cache warmth).

### FR-5: Multi-CPU dispatch
Each CPU independently dispatches from its local run queue. A global overflow
queue handles tasks when all local queues are balanced.

## Non-Functional Requirements

### NFR-1: eBPF safety
The scheduler must pass the kernel BPF verifier. This implies: bounded loops,
no unbounded memory access, stack usage under 512 bytes, only allowed helpers.

### NFR-2: Scheduling latency
Dispatch decision (ops.dispatch) must complete within 10μs on average.

### NFR-3: Overhead
Total scheduler overhead (all hooks combined) must not exceed 2% of CPU time
under a mixed workload of 200 tasks across 8 CPUs.

## Verification Goals

The following properties must be formally verified in Dafny:

1. **Fairness invariant**: FR-1 expressed as bounded vruntime divergence
2. **Starvation bound**: FR-2 expressed as a decreasing measure on wait time
3. **Affinity correctness**: FR-3 as a post-condition on select_cpu and dispatch
4. **eBPF well-formedness**: NFR-1 constraints encoded as type invariants

Properties NFR-2 and NFR-3 are validated by testing, not formal proof.
