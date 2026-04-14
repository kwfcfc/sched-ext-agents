/* SPDX-License-Identifier: GPL-2.0 */
#ifndef __SCHED_EXT_FAIR_H
#define __SCHED_EXT_FAIR_H

/*
 * Shared type definitions between BPF and userspace.
 * Corresponds to Dafny types in specs/domain/types.dfy.
 * See impl/bridge/mapping.md for the full mapping.
 */

#define MAX_CPUS         128
#define FAIRNESS_BOUND   10000000ULL  /* 10ms in ns */
#define STARVATION_BOUND 500000000ULL /* 500ms in ns */
#define NICE_0_WEIGHT    1024

/* Per-task scheduling context — stored in BPF task-local storage.
 * Dafny: Task datatype (partial — pid, state, weight come from kernel) */
struct task_ctx {
    __u64 vruntime;       /* Dafny: Task.vruntime */
    __u64 enqueue_time;   /* Dafny: Task.enqueue_time */
};

/* Scheduler statistics — exported via BPF map for monitoring */
struct sched_stats {
    __u64 total_enqueues;
    __u64 total_dispatches;
    __u64 total_ticks;
    __u64 max_vruntime_divergence;  /* for fairness monitoring */
    __u64 max_wait_ns;              /* for starvation monitoring */
};

#endif /* __SCHED_EXT_FAIR_H */
