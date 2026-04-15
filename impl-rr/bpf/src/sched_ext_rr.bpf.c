// SPDX-License-Identifier: GPL-2.0
//
// sched_ext_rr.bpf.c — Verified Round-Robin Scheduler
//
// This implementation is derived from the Dafny specification in
// specs-rr/refinements/concrete_scheduler.dfy. See impl-rr/bridge/mapping.md
// for the variable and action mapping between spec and implementation.
//
// Target: Linux 6.12+ with sched_ext support (tested on 6.17)
// Build: clang -O2 -target bpf -I<vmlinux_dir> -c sched_ext_rr.bpf.c

#include "vmlinux.h"

// Stub structs needed by scx compat layer (not present in kernel 6.17 BTF,
// but the compat code references them behind bpf_core_type_exists guards)
struct scx_bpf_select_cpu_and_args { s32 prev_cpu; u64 wake_flags; const struct cpumask *cpus_allowed; u64 flags; };
struct scx_bpf_dsq_insert_vtime_args { u64 dsq_id; u64 slice; u64 vtime; u64 enq_flags; };

#include <scx/common.bpf.h>

char _license[] SEC("license") = "GPL";

// ── Constants (from Dafny: specs-rr/domain/types.dfy) ────
#define TIME_QUANTUM_NS  5000000ULL   /* 5ms — Dafny: TIME_QUANTUM */
#define SHARED_DSQ       0            /* global shared dispatch queue */

UEI_DEFINE(uei);

// ── Per-task context (Dafny: Task datatype) ───────────────
struct task_ctx {
    u64 enqueue_time;       // Dafny: Task.enqueue_time
    u64 remaining_slice;    // Dafny: Task.remaining_slice
};

// ── BPF maps ──────────────────────────────────────────────
struct {
    __uint(type, BPF_MAP_TYPE_TASK_STORAGE);
    __uint(map_flags, BPF_F_NO_PREALLOC);
    __type(key, int);
    __type(value, struct task_ctx);
} task_ctx_map SEC(".maps");

// ── Statistics ────────────────────────────────────────────
volatile u64 nr_enqueued, nr_dispatched;

// ── Helper: lookup task context ───────────────────────────
static struct task_ctx *lookup_task_ctx(struct task_struct *p)
{
    return bpf_task_storage_get(&task_ctx_map, p, 0, 0);
}

// ═══════════════════════════════════════════════════════════
// sched_ext operations — Round-Robin
// ═══════════════════════════════════════════════════════════

// Dafny action: RRAbstractScheduler.Select
// Select CPU for a waking task. Prefer previous CPU for cache warmth.
s32 BPF_STRUCT_OPS(rr_select_cpu, struct task_struct *p, s32 prev_cpu,
                   u64 wake_flags)
{
    bool is_idle = false;
    s32 cpu;

    cpu = scx_bpf_select_cpu_dfl(p, prev_cpu, wake_flags, &is_idle);
    if (is_idle) {
        // CPU is idle — dispatch directly to local DSQ, skip global queue
        scx_bpf_dsq_insert(p, SCX_DSQ_LOCAL, TIME_QUANTUM_NS, 0);
    }
    return cpu;
}

// Dafny action: RRConcreteScheduler.Enqueue
// Enqueue task to shared DSQ. FIFO ordering is maintained by the
// framework — scx_bpf_dsq_insert appends to tail.
void BPF_STRUCT_OPS(rr_enqueue, struct task_struct *p, u64 enq_flags)
{
    struct task_ctx *tctx;

    tctx = lookup_task_ctx(p);
    if (tctx) {
        // Record enqueue timestamp — Dafny: t.(enqueue_time := s.clock)
        tctx->enqueue_time = bpf_ktime_get_ns();
        tctx->remaining_slice = TIME_QUANTUM_NS;
    }

    // Insert to shared DSQ with fixed time quantum — FIFO tail append
    // Dafny post-condition: task ends up on dispatch queue (tail)
    scx_bpf_dsq_insert(p, SHARED_DSQ, TIME_QUANTUM_NS, enq_flags);
    __sync_fetch_and_add(&nr_enqueued, 1);
}

// Dafny action: RRConcreteScheduler.Dispatch
// Consume from shared DSQ — FIFO order means earliest-enqueued first.
void BPF_STRUCT_OPS(rr_dispatch, s32 cpu, struct task_struct *prev)
{
    // Move head of shared DSQ to this CPU's local queue — FIFO
    // Dafny: Dispatch picks rq.tasks[0]
    if (scx_bpf_dsq_move_to_local(SHARED_DSQ, 0))
        __sync_fetch_and_add(&nr_dispatched, 1);
}

// Dafny action: Tick — track running time
void BPF_STRUCT_OPS(rr_running, struct task_struct *p)
{
    struct task_ctx *tctx;

    tctx = lookup_task_ctx(p);
    if (tctx)
        tctx->enqueue_time = bpf_ktime_get_ns();
}

// Dafny action: RRConcreteScheduler.ReEnqueue (quantum expiry tracking)
void BPF_STRUCT_OPS(rr_stopping, struct task_struct *p, bool runnable)
{
    struct task_ctx *tctx;
    u64 now, used;

    tctx = lookup_task_ctx(p);
    if (!tctx)
        return;

    now = bpf_ktime_get_ns();
    used = now - tctx->enqueue_time;

    if (used >= tctx->remaining_slice)
        tctx->remaining_slice = 0;
    else
        tctx->remaining_slice -= used;
}

// Initialize per-task context
s32 BPF_STRUCT_OPS(rr_init_task, struct task_struct *p,
                   struct scx_init_task_args *args)
{
    struct task_ctx tctx_init = {
        .enqueue_time = 0,
        .remaining_slice = TIME_QUANTUM_NS,
    };

    if (bpf_task_storage_get(&task_ctx_map, p, &tctx_init,
                             BPF_LOCAL_STORAGE_GET_F_CREATE))
        return 0;

    return -ENOMEM;
}

// Scheduler init — create the shared DSQ
s32 BPF_STRUCT_OPS_SLEEPABLE(rr_init)
{
    return scx_bpf_create_dsq(SHARED_DSQ, -1);
}

// Scheduler exit
void BPF_STRUCT_OPS(rr_exit, struct scx_exit_info *ei)
{
    UEI_RECORD(uei, ei);
}

// ── Scheduler registration ────────────────────────────────
SCX_OPS_DEFINE(rr_ops,
    .select_cpu     = (void *)rr_select_cpu,
    .enqueue        = (void *)rr_enqueue,
    .dispatch       = (void *)rr_dispatch,
    .running        = (void *)rr_running,
    .stopping       = (void *)rr_stopping,
    .init_task      = (void *)rr_init_task,
    .init           = (void *)rr_init,
    .exit           = (void *)rr_exit,
    .timeout_ms     = 5000,
    .name           = "rr_verified");
