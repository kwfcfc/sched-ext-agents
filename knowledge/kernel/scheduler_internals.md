# Linux Kernel Scheduler Internals

## CFS (Completely Fair Scheduler)

CFS is the default Linux scheduler for `SCHED_NORMAL` tasks. sched_ext schedulers
replace CFS for tasks that opt in.

**Key concepts**:
- **vruntime**: Virtual runtime tracks how much CPU time a task has consumed, weighted by priority. Lower vruntime = more deserving of CPU time.
- **Red-black tree**: CFS stores runnable tasks in a red-black tree sorted by vruntime. Dispatch picks the leftmost node (minimum vruntime).
- **min_vruntime**: A per-runqueue monotonically increasing floor. New tasks start at `min_vruntime` to prevent starvation of existing tasks.
- **Weight**: Derived from nice value. Nice 0 = weight 1024. Nice -20 = weight 88761. Nice 19 = weight 15.

**vruntime calculation**:
```
delta_vruntime = wall_time_ns * NICE_0_WEIGHT / task_weight
```
Higher weight → vruntime grows slower → gets more CPU time.

## Run Queue (struct rq)

Each CPU has one `struct rq` containing:
- The CFS run queue (`struct cfs_rq`)
- The RT run queue
- The deadline run queue
- The sched_ext run queue (when sched_ext is enabled)
- Current running task
- Clock (updated on every tick)

**Locking**: The rq has a spinlock (`rq_lock`). Most scheduler operations hold this lock. sched_ext hooks document whether rq_lock is held.

## Load Balancing

The kernel periodically rebalances tasks across CPUs:
- **Scheduling domains**: Hierarchical groups of CPUs (SMT → core → LLC → NUMA node)
- **Load balancing** runs at each domain level, pulling tasks from busy CPUs to idle ones
- sched_ext can influence this via `ops.select_cpu()` and custom dispatch logic

## Preemption

- **Tick preemption**: Every ~4ms (configurable), the timer interrupt checks if the current task should yield
- **Wakeup preemption**: When a task wakes up with lower vruntime than the running task, preemption may occur
- **BPF programs run with preemption disabled**: A BPF hook runs atomically from the scheduler's perspective

## Task Lifecycle in sched_ext

```
fork/wake → ops.select_cpu() → ops.enqueue() → [on DSQ]
  → ops.dispatch() → ops.running() → [executing]
  → timer tick / yield → ops.stopping() → ops.enqueue() (if still runnable)
  → exit → ops.exit_task()
```
