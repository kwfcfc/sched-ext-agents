// ═══════════════════════════════════════════════════════════
// Abstract scheduler — nondeterministic specification
// ═══════════════════════════════════════════════════════════
//
// This is the highest-level specification. It says WHAT the scheduler
// must do, not HOW. The concrete implementation (concrete_scheduler.dfy)
// must refine this module.

include "../domain/types.dfy"
include "../domain/helpers.dfy"
include "../properties/fairness.dfy"
include "../properties/starvation_freedom.dfy"

module AbstractScheduler {
  import opened SchedTypes
  import opened BPFHelpers
  import FP = FairnessProperty
  import SF = StarvationFreedom

  // ── Initial state ───────────────────────────────────────
  predicate Init(s: SchedState) {
    && s.all_tasks == {}
    && s.clock == 0
    && |s.active_cpus| > 0
    && ValidState(s)
  }

  // ── Enqueue action ──────────────────────────────────────
  // A task becomes runnable and is added to the scheduler.
  predicate Enqueue(s: SchedState, s': SchedState, t: Task, flags: EnqueueFlags)
  {
    && ValidState(s)
    && ValidTask(t)
    && t.state == Runnable
    // Post-state: task is in the system
    && s'.all_tasks == s.all_tasks + {t.(enqueue_time := s.clock)}
    && s'.clock == s.clock + 1
    && s'.active_cpus == s.active_cpus
    && ValidState(s')
  }

  // ── Dispatch action ─────────────────────────────────────
  // Nondeterministically pick a runnable task for a CPU.
  // The ONLY constraint: if there's a runnable task, one must be chosen.
  // Fairness and starvation properties further constrain which.
  predicate Dispatch(s: SchedState, s': SchedState, cpu: nat, chosen: Option<Task>)
  {
    && ValidState(s)
    && cpu in s.active_cpus
    // If there are runnable tasks, we must pick one
    && (exists t :: t in s.all_tasks && t.state == Runnable)
        ==> chosen.Some?
    // The chosen task must be valid
    && (chosen.Some? ==> chosen.value in s.all_tasks
                      && chosen.value.state == Runnable)
    // State update
    && s'.clock == s.clock + 1
    && ValidState(s')
  }

  // ── Tick action ─────────────────────────────────────────
  // Time advances. Running tasks accumulate vruntime.
  predicate Tick(s: SchedState, s': SchedState, cpu: nat)
  {
    && ValidState(s)
    && cpu in s.active_cpus
    && s'.clock == s.clock + 1
    && s'.active_cpus == s.active_cpus
    && ValidState(s')
  }

  // ── Next-state relation ─────────────────────────────────
  predicate Next(s: SchedState, s': SchedState)
  {
    || (exists t, f :: Enqueue(s, s', t, f))
    || (exists cpu, chosen :: Dispatch(s, s', cpu, chosen))
    || (exists cpu :: Tick(s, s', cpu))
  }

  // ── Safety invariant ────────────────────────────────────
  // The conjunction of all safety properties.
  predicate SafetyInvariant(s: SchedState)
    requires ValidState(s)
  {
    && FP.Fairness(s)
    && SF.NoStarvation(s)
  }
}
