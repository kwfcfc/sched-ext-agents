# sched_ext Operations Reference

## Hook Lifecycle

When a sched_ext scheduler is loaded, the kernel calls these hooks in this order
for each scheduling event:

```
Task wakes up / becomes runnable
  → ops.select_cpu(task, prev_cpu, wake_flags)     [no lock]
  → ops.enqueue(task, enq_flags)                    [rq lock held]

CPU needs next task to run
  → ops.dispatch(cpu, prev_task)                    [rq lock held]

Task starts running
  → ops.running(task)                               [rq lock held]

Task stops running (preempted or yields)
  → ops.stopping(task, runnable)                    [rq lock held]

Task exits
  → ops.exit_task(task, args)                       [no lock]
```

## ops.select_cpu()

```c
s32 (*select_cpu)(struct task_struct *p, s32 prev_cpu, u64 wake_flags);
```

- Called when a task wakes up to suggest which CPU it should run on
- **No rq lock held** — cannot safely modify shared scheduler state
- Return value: suggested CPU number
- The returned CPU is a hint; the framework may override it
- Common strategy: return prev_cpu if idle (cache warmth), else find idlest CPU

## ops.enqueue()

```c
void (*enqueue)(struct task_struct *p, u64 enq_flags);
```

- Called to enqueue a task into the scheduler
- **rq lock held** — safe to modify per-CPU state atomically
- `enq_flags` contains: SCX_ENQ_WAKE (wakeup), SCX_ENQ_LAST (no more tasks coming)
- Must call `scx_bpf_dispatch()` to place task on a DSQ (dispatch queue)
- If not dispatched, the task is lost (kernel logs an error)

## ops.dispatch()

```c
void (*dispatch)(s32 cpu, struct task_struct *prev);
```

- Called when a CPU's local DSQ is empty and it needs work
- **rq lock held**
- Typically calls `scx_bpf_consume(SCX_DSQ_GLOBAL)` to pull from the shared queue
- Can also dispatch tasks directly to the local CPU's DSQ

## ops.running()

```c
void (*running)(struct task_struct *p);
```

- Called when a task actually starts executing on a CPU
- **rq lock held**
- Good place to record start time for vruntime accounting

## ops.stopping()

```c
void (*stopping)(struct task_struct *p, bool runnable);
```

- Called when a task stops running (preempted, yielded, or blocked)
- **rq lock held**
- `runnable`: true if the task is still runnable (preempted), false if blocked
- Good place to update vruntime based on elapsed time

## ops.exit_task()

```c
void (*exit_task)(struct task_struct *p, struct scx_exit_task_args *args);
```

- Called when a task is being destroyed
- **No rq lock** — cleanup only, no scheduling decisions
- Free any per-task resources (BPF map entries, task-local storage)

## Dispatch Queues (DSQs)

- `SCX_DSQ_GLOBAL` (0xFFFFFFFF): shared across all CPUs
- Per-CPU local DSQs: `SCX_DSQ_LOCAL` (consumed automatically by the CPU)
- Custom DSQs: created with `scx_bpf_create_dsq()`
- Tasks in a DSQ are consumed in FIFO order by default
