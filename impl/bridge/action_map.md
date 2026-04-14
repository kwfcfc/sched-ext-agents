# Action Mapping: Dafny → C

> Detailed mapping from each Dafny Next-state action to the corresponding
> C function, including the exact lines where state mutations occur.

## AbstractScheduler.Enqueue → s_enqueue()

| Dafny operation | C equivalent | File:Line |
|---|---|---|
| `s'.all_tasks == s.all_tasks + {t}` | `scx_bpf_dispatch(p, ...)` | sched_ext_fair.bpf.c:s_enqueue |
| `t.enqueue_time := s.clock` | `ctx->enqueue_time = bpf_ktime_get_ns()` | sched_ext_fair.bpf.c:s_enqueue |
| `s'.clock == s.clock + 1` | Implicit (kernel clock advances) | N/A |

**Notes**: The Dafny model adds the task to `all_tasks` as a set operation.
In C, the task already exists in the kernel; `scx_bpf_dispatch` places it
on a dispatch queue, making it visible to `dispatch()`.

## AbstractScheduler.Dispatch → s_dispatch()

| Dafny operation | C equivalent | File:Line |
|---|---|---|
| Pick task with min vruntime | `scx_bpf_consume(SCX_DSQ_GLOBAL)` | sched_ext_fair.bpf.c:s_dispatch |
| `chosen.state := Running` | Kernel sets state after dispatch | N/A |
| `chosen.vruntime += delta` | Updated in `s_running()` | sched_ext_fair.bpf.c:s_running |

**Notes**: In the abstract model, dispatch and vruntime update are one step.
In the implementation, they're split: `s_dispatch()` picks the task,
`s_running()` updates vruntime when it actually starts. This is safe because
both run with `rq_lock` held and no other operation can interleave on the same CPU.

## AbstractScheduler.Select → s_select_cpu()

| Dafny operation | C equivalent | File:Line |
|---|---|---|
| Return cpu in affinity set | `scx_bpf_select_cpu_dfl(p, prev_cpu, ...)` | sched_ext_fair.bpf.c:s_select_cpu |
| No state mutation | No state mutation | — |

## AbstractScheduler.Tick → s_running()

| Dafny operation | C equivalent | File:Line |
|---|---|---|
| `t.vruntime += DeltaVruntime(t)` | `ctx->vruntime += delta` | sched_ext_fair.bpf.c:s_running |
| `s'.clock == s.clock + 1` | Implicit | N/A |

## AbstractScheduler.TaskDead → s_exit_task()

| Dafny operation | C equivalent | File:Line |
|---|---|---|
| `forall t :: t in s'.all_tasks ==> t.pid != pid` | Task-local storage auto-freed | sched_ext_fair.bpf.c:s_exit_task |
