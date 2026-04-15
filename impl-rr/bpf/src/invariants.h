// ═══════════════════════════════════════════════════════════
// invariants.h — Runtime assertions for Round-Robin scheduler
// ═══════════════════════════════════════════════════════════
//
// Translates Dafny invariants (specs-rr/) into BPF-safe runtime checks.

#ifndef __RR_INVARIANTS_H
#define __RR_INVARIANTS_H

#ifdef DEBUG_INVARIANTS

#define ASSERT_INVARIANT(cond, msg)                          \
    do {                                                     \
        if (!(cond)) {                                       \
            bpf_printk("INVARIANT VIOLATED: %s", msg);       \
            bpf_printk("  at %s:%d", __FILE__, __LINE__);    \
        }                                                    \
    } while (0)

#define ASSERT_CPU_VALID(cpu)                                \
    ASSERT_INVARIANT((cpu) >= 0 && (cpu) < MAX_CPUS,         \
        "CPU out of valid range "                            \
        "(specs-rr/properties/cpu_affinity.dfy:AffinityRespected)")

#define ASSERT_QUANTUM_VALID(slice)                          \
    ASSERT_INVARIANT((slice) <= TIME_QUANTUM_NS,              \
        "Remaining slice exceeds quantum "                   \
        "(specs-rr/domain/types.dfy:ValidTask)")

#define ASSERT_ENQUEUE_TIME(ts)                              \
    ASSERT_INVARIANT((ts) > 0,                                \
        "Enqueue time must be positive "                     \
        "(specs-rr/properties/fifo_ordering.dfy)")

#else  /* Release: no-op */

#define ASSERT_INVARIANT(cond, msg)       ((void)0)
#define ASSERT_CPU_VALID(cpu)             ((void)0)
#define ASSERT_QUANTUM_VALID(slice)       ((void)0)
#define ASSERT_ENQUEUE_TIME(ts)           ((void)0)

#endif /* DEBUG_INVARIANTS */

#endif /* __RR_INVARIANTS_H */
