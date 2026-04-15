/* SPDX-License-Identifier: GPL-2.0 */
#ifndef __SCHED_EXT_RR_H
#define __SCHED_EXT_RR_H

/*
 * Shared type definitions for Round-Robin sched_ext scheduler.
 * Corresponds to Dafny types in specs-rr/domain/types.dfy.
 * See impl-rr/bridge/mapping.md for the full mapping.
 */

#define MAX_CPUS         128
#define TIME_QUANTUM_NS  5000000ULL   /* 5ms in ns — Dafny: TIME_QUANTUM */
#define MAX_TASKS        4096

/* Per-task scheduling context — stored in BPF task-local storage.
 * Dafny: Task datatype (pid, state come from kernel) */
struct task_ctx {
    __u64 enqueue_time;     /* Dafny: Task.enqueue_time */
    __u64 remaining_slice;  /* Dafny: Task.remaining_slice */
};

/* Scheduler statistics — exported via BPF map for monitoring */
struct sched_stats {
    __u64 total_enqueues;
    __u64 total_dispatches;
    __u64 total_requeues;      /* quantum-expired re-enqueues */
    __u64 max_wait_ns;         /* for starvation monitoring */
};

#endif /* __SCHED_EXT_RR_H */
