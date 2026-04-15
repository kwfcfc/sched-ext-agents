// ═══════════════════════════════════════════════════════════
// Abstract scheduler — nondeterministic specification (RR)
// ═══════════════════════════════════════════════════════════
//
// Says WHAT the round-robin scheduler must do, not HOW.
// The concrete implementation must refine this module.

include "../domain/types.dfy"
include "../domain/helpers.dfy"
include "../properties/fifo_ordering.dfy"
include "../properties/starvation_freedom.dfy"

module RRAbstractScheduler {
  import opened RRSchedTypes
  import opened RRBPFHelpers
  import FIFO = FIFOProperty
  import SF = RRStarvationFreedom

  // ── Initial state ───────────────────────────────────────
  predicate Init(s: SchedState) {
    && s.all_tasks == {}
    && s.clock == 0
    && |s.active_cpus| > 0
    && ValidState(s)
    // All queues are empty at init
    && (forall cpu :: cpu in s.run_queues ==> |s.run_queues[cpu].tasks| == 0)
  }

  // ── Enqueue action ──────────────────────────────────────
  // A task becomes runnable and is added to a run queue.
  // Abstract: we only require the task ends up in the system
  // and FIFO structure is maintained.
  predicate Enqueue(s: SchedState, s': SchedState, t: Task, target_cpu: nat)
  {
    && ValidState(s)
    && ValidTask(t)
    && t.state == Runnable
    && target_cpu in s.active_cpus
    && target_cpu in s.run_queues
    // Post: task is in the system on the target CPU's queue
    && s'.all_tasks == s.all_tasks + {t.(enqueue_time := s.clock, remaining_slice := TIME_QUANTUM)}
    && s'.clock == s.clock + 1
    && s'.active_cpus == s.active_cpus
    // Run-queue structure: task appended at tail, other queues unchanged
    && target_cpu in s'.run_queues
    && s'.run_queues[target_cpu].tasks
         == s.run_queues[target_cpu].tasks + [t.(enqueue_time := s.clock, remaining_slice := TIME_QUANTUM)]
    && (forall c :: c in s.run_queues && c != target_cpu
          ==> c in s'.run_queues && s'.run_queues[c] == s.run_queues[c])
    && (forall c :: c in s'.run_queues ==> c in s.run_queues)
    // Clock is ahead of all existing enqueue times (FIFO appendability)
    && (|s.run_queues[target_cpu].tasks| == 0
        || s.run_queues[target_cpu].tasks[|s.run_queues[target_cpu].tasks| - 1].enqueue_time <= s.clock)
    && ValidState(s')
  }

  // ── Dispatch action ─────────────────────────────────────
  // Pick a runnable task from a CPU's queue.
  // Abstract: if there are runnable tasks on this CPU, one must be chosen.
  predicate Dispatch(s: SchedState, s': SchedState, cpu: nat, chosen: Option<Task>)
  {
    && ValidState(s)
    && cpu in s.active_cpus
    && cpu in s.run_queues
    // If the queue is non-empty, we must pick a task
    && (|s.run_queues[cpu].tasks| > 0 ==> chosen.Some?)
    && (|s.run_queues[cpu].tasks| == 0 ==> chosen.None?)
    // The chosen task must be from this CPU's queue
    && (chosen.Some? ==>
          (chosen.value in s.run_queues[cpu].tasks
           && chosen.value.state == Runnable))
    && s'.clock == s.clock + 1
    // Run-queue structure: head removed, other queues unchanged
    && cpu in s'.run_queues
    && (chosen.Some? ==>
          (|s.run_queues[cpu].tasks| > 0
           && s'.run_queues[cpu].tasks == s.run_queues[cpu].tasks[1..]))
    && (chosen.None? ==> s'.run_queues[cpu].tasks == s.run_queues[cpu].tasks)
    && (forall c :: c in s.run_queues && c != cpu
          ==> c in s'.run_queues && s'.run_queues[c] == s.run_queues[c])
    && (forall c :: c in s'.run_queues ==> c in s.run_queues)
    && ValidState(s')
  }

  // ── Tick action ─────────────────────────────────────────
  predicate Tick(s: SchedState, s': SchedState, cpu: nat)
  {
    && ValidState(s)
    && cpu in s.active_cpus
    && s'.clock == s.clock + 1
    && s'.active_cpus == s.active_cpus
    && s'.run_queues == s.run_queues    // Tick does not modify queues
    && ValidState(s')
  }

  // ── Next-state relation ─────────────────────────────────
  ghost predicate Next(s: SchedState, s': SchedState)
  {
    || (exists t, cpu :: Enqueue(s, s', t, cpu))
    || (exists cpu, chosen :: Dispatch(s, s', cpu, chosen))
    || (exists cpu :: Tick(s, s', cpu))
  }

  // ── Safety invariant ────────────────────────────────────
  predicate SafetyInvariant(s: SchedState)
    requires ValidState(s)
  {
    FIFO.FIFOInvariant(s)
  }
}
