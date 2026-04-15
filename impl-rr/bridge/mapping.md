# Spec ↔ Implementation Mapping: Round-Robin Scheduler

## Variable Mapping

| Dafny (specs-rr/) | C/eBPF (impl-rr/bpf/src/) | Notes |
|---|---|---|
| `SchedState.run_queues` | Global DSQ (`SCX_DSQ_GLOBAL`) | Framework manages FIFO queue |
| `SchedState.clock` | `bpf_ktime_get_ns()` | Monotonic kernel clock |
| `SchedState.active_cpus` | Kernel CPU topology | Not directly accessed in BPF |
| `Task.pid` | `p->pid` (from `task_struct`) | Kernel-provided |
| `Task.state` | `p->scx.flags` | Kernel-managed |
| `Task.cpu_affinity` | `p->cpus_ptr` | Kernel-managed, enforced by `scx_bpf_select_cpu_dfl` |
| `Task.enqueue_time` | `struct task_ctx.enqueue_time` | In task-local storage map |
| `Task.remaining_slice` | `struct task_ctx.remaining_slice` | In task-local storage map |
| `TIME_QUANTUM` (5ms) | `TIME_QUANTUM_NS` (5000000) | Compile-time constant |

## Action Mapping

| Dafny Action | C Function | Hook | Lock Held |
|---|---|---|---|
| `RRAbstractScheduler.Init` | Module load | `SCX_OPS_DEFINE` | N/A |
| `RRAbstractScheduler.Select` | `rr_select_cpu()` | `ops.select_cpu` | No |
| `RRConcreteScheduler.Enqueue` | `rr_enqueue()` | `ops.enqueue` | rq_lock |
| `RRConcreteScheduler.Dispatch` | `rr_dispatch()` | `ops.dispatch` | rq_lock |
| `Tick (vruntime update)` | `rr_running()` | `ops.running` | rq_lock |
| `RRConcreteScheduler.ReEnqueue` | `rr_stopping()` | `ops.stopping` | rq_lock |
| `TaskDead` | `rr_exit_task()` | `ops.exit_task` | No |

## Key Design Decisions

### FIFO ordering via global DSQ
The sched_ext framework's global DSQ (`SCX_DSQ_GLOBAL`) inherently maintains FIFO ordering.
`scx_bpf_dispatch()` appends to the tail, `scx_bpf_consume()` dequeues from the head.
This directly implements the Dafny spec's `tasks + [new_task]` (enqueue) and `tasks[0]` (dispatch).

### Fixed time quantum
Unlike the vtime scheduler where slice depends on weight, round-robin uses a fixed
`TIME_QUANTUM_NS = 5ms` for all tasks. This is passed as the `slice` argument to
`scx_bpf_dispatch()`, letting the kernel handle preemption timing.

### Re-enqueue on quantum expiry
When `rr_stopping()` detects that `remaining_slice` is exhausted, the task will be
re-enqueued by the framework (calling `rr_enqueue` again), placing it at the tail
of the global DSQ — completing the "round" in round-robin.

## What the Spec Does NOT Model

- Memory allocation failures (BPF map operations)
- Preemption between BPF instructions (atomic hook assumption)
- NUMA topology effects
- Kernel version differences in sched_ext behavior
- Timer interrupt granularity affecting quantum precision
