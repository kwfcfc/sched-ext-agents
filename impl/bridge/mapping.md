# Specification ↔ Implementation Mapping

> **This is a living document.** Every PR that modifies `specs/` or `impl/bpf/src/`
> MUST update this file. Reviewers: reject PRs that don't.

## Variable Mapping

| Dafny (specs/domain/types.dfy)       | C (impl/bpf/src/)                           | Notes                              |
|--------------------------------------|----------------------------------------------|------------------------------------|
| `SchedState.run_queues`              | `struct bpf_map *run_queues` (per-CPU array) | BPF_MAP_TYPE_PERCPU_ARRAY          |
| `SchedState.all_tasks`               | N/A (kernel owns task lifecycle)             | Modeled only in spec               |
| `SchedState.clock`                   | `bpf_ktime_get_ns()`                        | Monotonic, not wall clock           |
| `SchedState.active_cpus`             | `scx_bpf_get_online_cpumask()`              | Bitmap in kernel, set in Dafny      |
| `Task.pid`                           | `p->pid` (struct task_struct)                |                                    |
| `Task.vruntime`                      | `struct task_ctx.vruntime` (BPF map value)   | Stored in task-local storage        |
| `Task.weight`                        | `p->scx.weight`                             | Set by sched_ext framework          |
| `Task.state`                         | Implicit in kernel scheduler state           | Modeled explicitly in Dafny only    |
| `Task.cpu_affinity`                  | `p->cpus_ptr`                               | Kernel cpumask                      |
| `RunQueue.tasks`                     | Red-black tree in `struct rq_map_value`      | Sorted by vruntime in both          |
| `RunQueue.min_vruntime`              | `struct rq_map_value.min_vruntime`           |                                    |

## Action Mapping

| Dafny Action                          | C Function                        | Hook / Context                      |
|---------------------------------------|-----------------------------------|-------------------------------------|
| `AbstractScheduler.Enqueue(t, flags)` | `s_enqueue()`                     | `ops.enqueue()`, rq lock held       |
| `AbstractScheduler.Dispatch(cpu)`     | `s_dispatch()`                    | `ops.dispatch()`, rq lock held      |
| `AbstractScheduler.Select(t, prev)`   | `s_select_cpu()`                  | `ops.select_cpu()`, no lock         |
| `AbstractScheduler.Tick(cpu)`         | `s_running()` / `s_tick()`        | `ops.running()` or timer tick       |
| `AbstractScheduler.TaskDead(pid)`     | `s_exit_task()`                   | `ops.exit_task()`                   |

## Atomicity Boundaries

> **Critical**: each Dafny action is one atomic step. The corresponding
> C function must execute as-if atomically with respect to shared state.

| Dafny Atomic Step     | C Atomicity Mechanism                      | Verified By            |
|-----------------------|--------------------------------------------|------------------------|
| `Enqueue`             | rq_lock held by sched_ext framework        | Kernel guarantees      |
| `Dispatch`            | rq_lock held by sched_ext framework        | Kernel guarantees      |
| `Select`              | Returns a suggestion; no shared mutation    | Lock-free by design    |
| `Tick` (vruntime update) | `__sync_fetch_and_add` on per-task vruntime | BPF atomic ops        |

## What the Spec Does NOT Model

These are explicitly out of scope — verified by testing, not proof:

- Memory allocation failures (eBPF has no malloc)
- BPF map operation failures (ENOMEM on update)
- Preemption between BPF instructions (BPF programs run to completion)
- NUMA topology effects on cache performance
- Kernel version differences in sched_ext behavior
- Integer overflow in vruntime (handled by wraparound logic in C, not in Dafny)
