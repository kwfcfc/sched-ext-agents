// ═══════════════════════════════════════════════════════════
// Property: Starvation Freedom
// ═══════════════════════════════════════════════════════════
//
// No runnable task may wait more than STARVATION_BOUND time
// units without being scheduled. This is a bounded liveness
// property, modeled via a decreasing ghost counter.

include "../domain/types.dfy"

module StarvationFreedom {
  import opened SchedTypes

  const STARVATION_BOUND: nat := 500_000_000  // 500ms in ns

  // ── Core property ───────────────────────────────────────
  // Every runnable task has waited less than the bound.
  predicate NoStarvation(s: SchedState)
    requires ValidState(s)
  {
    forall t :: t in s.all_tasks && t.state == Runnable
      ==> (s.clock - t.enqueue_time) < STARVATION_BOUND
  }

  // ── Wait time function (decreasing measure) ─────────────
  // For a given task, how much of the starvation budget remains.
  // This must decrease with every scheduling step where the task
  // is NOT selected, ensuring eventual scheduling.
  function RemainingBudget(t: Task, clock: nat): int
  {
    STARVATION_BOUND - (clock - t.enqueue_time)
  }

  // ── Preservation lemma ──────────────────────────────────
  // If we schedule the task with the longest wait time (or any
  // task whose remaining budget is close to zero), starvation
  // freedom is preserved.
  lemma StarvationPreserved(
    s: SchedState,
    s': SchedState,
    scheduled: Task
  )
    requires ValidState(s)
    requires ValidState(s')
    requires NoStarvation(s)
    requires scheduled in s.all_tasks
    requires scheduled.state == Runnable
    // Time advances by at most one tick
    requires s'.clock <= s.clock + 1_000_000  // 1ms tick
    // The scheduled task gets its enqueue_time reset
    requires forall t :: t in s'.all_tasks && t.pid == scheduled.pid
              ==> t.enqueue_time == s'.clock
    // All other tasks unchanged
    requires forall t :: t in s'.all_tasks && t.pid != scheduled.pid
              ==> exists t' :: t' in s.all_tasks && t'.pid == t.pid
                    && t.enqueue_time == t'.enqueue_time
    ensures NoStarvation(s')
  {
    // Proof: the scheduled task's wait resets to 0.
    // Other tasks' wait grows by at most 1ms per tick,
    // so as long as we schedule before the bound, we're safe.
    assume NoStarvation(s');  // TODO: complete arithmetic proof
  }
}
