// ═══════════════════════════════════════════════════════════
// invariants.h — Runtime assertions derived from Dafny specs
// ═══════════════════════════════════════════════════════════
//
// These macros translate Dafny invariants into BPF-safe runtime checks.
// In debug builds, violations are reported via bpf_printk.
// In release builds, they compile to no-ops.
//
// Each macro references the Dafny source file and line where the
// invariant is formally stated and proven.

#ifndef __INVARIANTS_H
#define __INVARIANTS_H

#ifdef DEBUG_INVARIANTS

#define ASSERT_INVARIANT(cond, msg)                          \
    do {                                                     \
        if (!(cond)) {                                       \
            bpf_printk("INVARIANT VIOLATED: %s", msg);       \
            bpf_printk("  at %s:%d", __FILE__, __LINE__);    \
        }                                                    \
    } while (0)

#define ASSERT_FAIRNESS(vrt_a, vrt_b, bound)                 \
    do {                                                     \
        u64 _diff = (vrt_a) > (vrt_b) ?                      \
                    (vrt_a) - (vrt_b) : (vrt_b) - (vrt_a);   \
        ASSERT_INVARIANT(_diff <= (bound),                   \
            "Fairness: vruntime divergence exceeds bound "   \
            "(specs/properties/fairness.dfy:Fairness)");     \
    } while (0)

#define ASSERT_CPU_VALID(cpu)                                \
    ASSERT_INVARIANT((cpu) >= 0 && (cpu) < MAX_CPUS,         \
        "CPU out of valid range "                            \
        "(specs/properties/cpu_affinity.dfy:ValidCpu)")

#define ASSERT_WEIGHT_VALID(w)                               \
    ASSERT_INVARIANT((w) > 0 && (w) <= 1024,                 \
        "Weight out of range "                               \
        "(specs/domain/types.dfy:ValidTask)")

#else  /* Release: no-op */

#define ASSERT_INVARIANT(cond, msg)       ((void)0)
#define ASSERT_FAIRNESS(vrt_a, vrt_b, b)  ((void)0)
#define ASSERT_CPU_VALID(cpu)             ((void)0)
#define ASSERT_WEIGHT_VALID(w)            ((void)0)

#endif /* DEBUG_INVARIANTS */

#endif /* __INVARIANTS_H */
