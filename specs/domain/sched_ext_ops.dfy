// ═══════════════════════════════════════════════════════════
// Abstract sched_ext operations trait
// ═══════════════════════════════════════════════════════════
//
// Defines the interface that any sched_ext scheduler must implement.
// Concrete implementations in specs/refinements/ refine this trait.

include "types.dfy"
include "helpers.dfy"

module SchedExtOps {
  import opened SchedTypes
  import opened BPFHelpers

  // The abstract scheduler interface.
  // Each method corresponds to a sched_ext hook.
  trait SchedOps {

    // ── ops.select_cpu ─────────────────────────────────────
    // Suggest a CPU for a waking task. No rq lock held.
    method select_cpu(t: Task, prev_cpu: nat, wake_flags: nat)
      returns (cpu: nat)
      requires ValidTask(t)
      requires prev_cpu < NUM_CPUS
      ensures cpu < NUM_CPUS
      ensures t.cpu_affinity != {} ==> cpu in t.cpu_affinity

    // ── ops.enqueue ────────────────────────────────────────
    // Place a task on a dispatch queue. rq lock held.
    method enqueue(
      ghost s: SchedState,
      t: Task,
      flags: EnqueueFlags
    ) returns (ghost s': SchedState)
      requires ValidState(s)
      requires ValidTask(t)
      requires t.state == Runnable
      ensures ValidState(s')
      ensures t in s'.all_tasks

    // ── ops.dispatch ───────────────────────────────────────
    // Select the next task to run on a CPU. rq lock held.
    method dispatch(
      ghost s: SchedState,
      cpu: nat
    ) returns (next: Option<Task>, ghost s': SchedState)
      requires ValidState(s)
      requires cpu in s.active_cpus
      ensures ValidState(s')
      ensures next.Some? ==> ValidTask(next.value)
      ensures next.Some? ==> next.value.state == Runnable

    // ── ops.running ────────────────────────────────────────
    // Called when a task starts executing. Update accounting.
    method running(
      ghost s: SchedState,
      t: Task
    ) returns (ghost s': SchedState)
      requires ValidState(s)
      requires ValidTask(t)
      ensures ValidState(s')

    // ── ops.exit_task ──────────────────────────────────────
    // Called when a task is destroyed. Cleanup.
    method exit_task(
      ghost s: SchedState,
      pid: nat
    ) returns (ghost s': SchedState)
      requires ValidState(s)
      ensures ValidState(s')
      ensures forall t :: t in s'.all_tasks ==> t.pid != pid
  }
}
