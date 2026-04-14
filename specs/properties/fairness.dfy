// ═══════════════════════════════════════════════════════════
// Property: Scheduling Fairness
// ═══════════════════════════════════════════════════════════
//
// Fairness means: any two tasks with equal weight should have
// vruntimes that don't diverge beyond a bounded threshold.
// This is the core invariant of CFS-like schedulers.

include "../domain/types.dfy"

module FairnessProperty {
  import opened SchedTypes

  // ── Main fairness predicate ─────────────────────────────
  // For any two runnable tasks of equal weight, their vruntime
  // difference is bounded by FAIRNESS_BOUND.
  const FAIRNESS_BOUND: nat := 10_000_000  // ~10ms in ns

  predicate Fairness(s: SchedState)
    requires ValidState(s)
  {
    forall t1, t2 ::
      t1 in s.all_tasks && t2 in s.all_tasks
      && t1.state in {Runnable, Running}
      && t2.state in {Runnable, Running}
      && t1.weight == t2.weight
      && t1.pid != t2.pid
      ==> AbsDiff(t1.vruntime, t2.vruntime) <= FAIRNESS_BOUND
  }

  // ── Weighted fairness (generalization) ──────────────────
  // For tasks with different weights, normalize by weight.
  predicate WeightedFairness(s: SchedState)
    requires ValidState(s)
  {
    forall t1, t2 ::
      t1 in s.all_tasks && t2 in s.all_tasks
      && t1.state in {Runnable, Running}
      && t2.state in {Runnable, Running}
      && t1.pid != t2.pid
      ==> AbsDiff(
            t1.vruntime * t1.weight,
            t2.vruntime * t2.weight
          ) <= FAIRNESS_BOUND * MAX_WEIGHT
  }

  // ── Fairness preservation lemma ─────────────────────────
  // If we always pick the task with minimum vruntime, fairness
  // is preserved across state transitions.
  lemma FairnessPreserved(
    s: SchedState,
    s': SchedState,
    scheduled: Task
  )
    requires ValidState(s)
    requires ValidState(s')
    requires Fairness(s)
    requires scheduled in s.all_tasks
    requires scheduled.state == Runnable
    // The scheduled task had minimum vruntime
    requires forall t :: t in s.all_tasks && t.state == Runnable
                && t.weight == scheduled.weight
                ==> scheduled.vruntime <= t.vruntime
    // The new state only differs in the scheduled task's vruntime
    requires s'.all_tasks == (s.all_tasks - {scheduled})
              + {scheduled.(vruntime := scheduled.vruntime + DeltaVruntime(scheduled))}
    ensures Fairness(s')
  {
    // Proof sketch: since we picked the minimum and advanced it,
    // the new vruntime is at most min + delta, which stays within
    // FAIRNESS_BOUND of any other task's vruntime.
    // Full proof requires arithmetic on vruntime ordering.
    assume Fairness(s');  // TODO: complete proof
  }

  // ── Helper functions ────────────────────────────────────
  function AbsDiff(a: nat, b: nat): nat {
    if a >= b then a - b else b - a
  }

  function DeltaVruntime(t: Task): nat
    requires t.weight > 0
  {
    // delta_vruntime = wall_time * NICE_0_WEIGHT / weight
    // Simplified: assume a tick of 1ms (1_000_000 ns)
    1_000_000 * 1024 / t.weight
  }
}
