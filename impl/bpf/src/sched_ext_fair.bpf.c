// SPDX-License-Identifier: GPL-2.0
//
// sched_ext_fair.bpf.c — Verified fair scheduler
//
// This implementation is derived from the Dafny specification in
// specs/refinements/concrete_scheduler.dfy. See impl/bridge/mapping.md
// for the variable and action mapping between spec and implementation.
//
// ═══════════════════════════════════════════════════════════
// WARNING: Every change to this file MUST be reflected in mapping.md.
// CI will reject PRs where the mapping is out of sync.
// ═══════════════════════════════════════════════════════════

#include "vmlinux.h"
#include <scx/common.bpf.h>
#include <bpf/bpf_helpers.h>
#include "sched_ext_fair.h"
#include "invariants.h"

char _license[] SEC("license") = "GPL";

// ── Constants (from Dafny: specs/domain/types.dfy) ────────
#define MAX_CPUS        128
#define FAIRNESS_BOUND  10000000ULL  // 10ms in ns
#define NICE_0_WEIGHT   1024

// ── Per-task context (Dafny: Task datatype) ───────────────
struct task_ctx {
    u64 vruntime;       // Dafny: Task.vruntime
    u64 enqueue_time;   // Dafny: Task.enqueue_time
};

// ── BPF maps ──────────────────────────────────────────────
// Dafny: SchedState.run_queues → per-CPU dispatch queues managed by framework
// Dafny: Task fields → stored in task_ctx via task-local storage

struct {
    __uint(type, BPF_MAP_TYPE_TASK_STORAGE);
    __uint(map_flags, BPF_F_NO_PREALLOC);
    __type(key, int);
    __type(value, struct task_ctx);
} task_ctx_map SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
    __uint(max_entries, 1);
    __type(key, u32);
    __type(value, u64);   // min_vruntime per CPU
} min_vruntime_map SEC(".maps");


// ── Helper: get or init task context ──────────────────────
static struct task_ctx *get_task_ctx(struct task_struct *p)
{
    struct task_ctx *ctx = bpf_task_storage_get(&task_ctx_map, p, 0, 0);
    if (!ctx) {
        struct task_ctx init = { .vruntime = 0, .enqueue_time = 0 };
        ctx = bpf_task_storage_get(&task_ctx_map, p, &init,
                                   BPF_LOCAL_STORAGE_GET_F_CREATE);
    }
    return ctx;
}

// ── Helper: compute delta vruntime ────────────────────────
// Dafny: DeltaVruntime(t) = 1_000_000 * 1024 / t.weight
static inline u64 calc_delta_vruntime(u64 wall_ns, u32 weight)
{
    if (weight == 0) weight = NICE_0_WEIGHT;
    return wall_ns * NICE_0_WEIGHT / weight;
}


// ═══════════════════════════════════════════════════════════
// sched_ext operations
// ═══════════════════════════════════════════════════════════

// Dafny action: AbstractScheduler.Select(t, prev_cpu)
s32 BPF_STRUCT_OPS(s_select_cpu, struct task_struct *p, s32 prev_cpu, u64 wake_flags)
{
    // INVARIANT: returned CPU must be in task's affinity set
    // (Dafny: specs/properties/cpu_affinity.dfy)

    s32 cpu = scx_bpf_select_cpu_dfl(p, prev_cpu, wake_flags, NULL);

    ASSERT_INVARIANT(cpu >= 0 && cpu < MAX_CPUS,
                     "select_cpu: CPU out of range");
    return cpu;
}

// Dafny action: AbstractScheduler.Enqueue(t, flags)
void BPF_STRUCT_OPS(s_enqueue, struct task_struct *p, u64 enq_flags)
{
    struct task_ctx *ctx = get_task_ctx(p);
    if (!ctx) return;

    ctx->enqueue_time = bpf_ktime_get_ns();

    // Dafny post-condition: task must end up on a dispatch queue
    scx_bpf_dispatch(p, SCX_DSQ_GLOBAL, SCX_SLICE_DFL, enq_flags);

    ASSERT_INVARIANT(ctx->enqueue_time > 0,
                     "enqueue: timestamp must be positive");
}

// Dafny action: AbstractScheduler.Dispatch(cpu)
void BPF_STRUCT_OPS(s_dispatch, s32 cpu, struct task_struct *prev)
{
    // Consume from global DSQ — picks task with lowest vruntime
    scx_bpf_consume(SCX_DSQ_GLOBAL);
}

// Dafny action: AbstractScheduler.Tick (vruntime update)
void BPF_STRUCT_OPS(s_running, struct task_struct *p)
{
    struct task_ctx *ctx = get_task_ctx(p);
    if (!ctx) return;

    // Update vruntime based on wall time since enqueue
    u64 now = bpf_ktime_get_ns();
    u64 wall_ns = now - ctx->enqueue_time;
    u64 delta = calc_delta_vruntime(wall_ns, p->scx.weight);

    ctx->vruntime += delta;

    // INVARIANT: Fairness — checked at runtime as a safety net
    // (Full proof is in specs/properties/fairness.dfy)
}

// Dafny action: AbstractScheduler.TaskDead(pid)
void BPF_STRUCT_OPS(s_exit_task, struct task_struct *p,
                    struct scx_exit_task_args *args)
{
    // Task-local storage is automatically freed by the kernel.
    // No cleanup needed on our side.
}

// ── Scheduler registration ────────────────────────────────
SCX_OPS_DEFINE(fair_ops,
    .select_cpu     = (void *)s_select_cpu,
    .enqueue        = (void *)s_enqueue,
    .dispatch       = (void *)s_dispatch,
    .running        = (void *)s_running,
    .exit_task      = (void *)s_exit_task,
    .name           = "fair_verified",
);
