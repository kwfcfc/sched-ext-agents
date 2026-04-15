# Requirements: Round-Robin CPU Scheduler (sched_ext)

## Overview

Build a Linux sched_ext scheduler that implements simple round-robin scheduling.
Each task receives a fixed time quantum. Tasks are dispatched in FIFO order.
When a task exhausts its quantum, it is placed at the back of the queue.

## Functional Requirements

### FR-1: Equal time sharing
All runnable tasks receive equal CPU time regardless of weight. Each task gets
exactly one time quantum (default 5ms) before being preempted.

### FR-2: FIFO dispatch order
Tasks are dispatched in the order they were enqueued. The scheduler maintains a
FIFO queue; dispatch always picks the head of the queue.

### FR-3: Starvation freedom
No runnable task may wait more than N × quantum time without being scheduled,
where N is the number of runnable tasks. With a 5ms quantum and 100 tasks,
the worst-case wait is 500ms.

### FR-4: CPU affinity
The scheduler must respect `cpus_allowed` masks. A task must never be dispatched
to a CPU outside its affinity set.

### FR-5: Quantum expiry and re-enqueue
When a running task's time slice expires (detected via ops.stopping or tick),
it is re-enqueued at the tail of the run queue with a fresh quantum.

## Non-Functional Requirements

### NFR-1: eBPF safety
The scheduler must pass the kernel BPF verifier. This implies: bounded loops,
no unbounded memory access, stack usage under 512 bytes, only allowed helpers.

### NFR-2: Scheduling latency
Dispatch decision (ops.dispatch) must complete within 10μs on average.
Round-robin dispatch is O(1) — just dequeue the head.

### NFR-3: Overhead
Total scheduler overhead must not exceed 2% of CPU time under a mixed workload
of 200 tasks across 8 CPUs.

## Verification Goals

The following properties must be formally verified in Dafny:

1. **FIFO ordering**: Dispatch always returns the earliest-enqueued task
2. **Starvation bound**: Wait time bounded by N × quantum (decreasing measure)
3. **Affinity correctness**: Tasks never dispatched outside their CPU set
4. **eBPF well-formedness**: NFR-1 constraints encoded as type invariants
5. **Queue preservation**: Enqueue adds to tail, dispatch removes from head

Properties NFR-2 and NFR-3 are validated by testing, not formal proof.
