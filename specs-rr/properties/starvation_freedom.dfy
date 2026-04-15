// ═══════════════════════════════════════════════════════════
// Property: Starvation Freedom (Round-Robin)
// ═══════════════════════════════════════════════════════════
//
// In round-robin, the starvation bound is N × quantum where
// N is the number of runnable tasks ahead in the queue.
// A task's position in the FIFO queue is a natural decreasing
// measure toward being scheduled.

include "../domain/types.dfy"

module RRStarvationFreedom {
  import opened RRSchedTypes

  // ── Core property ───────────────────────────────────────
  // Every runnable task has bounded wait time proportional to
  // its position in the queue times the time quantum.
  predicate NoStarvation(s: SchedState)
    requires ValidState(s)
  {
    forall cpu :: cpu in s.run_queues ==>
      forall i :: 0 <= i < |s.run_queues[cpu].tasks| ==>
        var t := s.run_queues[cpu].tasks[i];
        t.state == Runnable ==>
          // Wait time bounded by position × quantum
          (s.clock - t.enqueue_time) < (i + 1) * TIME_QUANTUM * MAX_TASKS
  }

  // ── Queue position as decreasing measure ────────────────
  // A task's index in the FIFO queue is its "distance to dispatch".
  // Each dispatch step decreases this by 1 for the head task.
  function QueuePosition(rq: RunQueue, pid: nat): nat
  {
    QueuePositionHelper(rq.tasks, pid, 0)
  }

  function QueuePositionHelper(tasks: seq<Task>, pid: nat, idx: nat): nat
  {
    if |tasks| == 0 then idx  // not found, return current index
    else if tasks[0].pid == pid then idx
    else QueuePositionHelper(tasks[1..], pid, idx + 1)
  }

  // ── Bounded wait lemma ──────────────────────────────────
  // After dispatching the head, every other task moves one
  // position closer to being dispatched.
  lemma DispatchReducesWait(
    rq: RunQueue,
    rq': RunQueue
  )
    requires |rq.tasks| > 0
    requires rq'.tasks == rq.tasks[1..]
    ensures |rq'.tasks| == |rq.tasks| - 1
    // Every remaining task is now one position closer
    ensures forall i :: 0 <= i < |rq'.tasks| ==>
              rq'.tasks[i] == rq.tasks[i + 1]
  {
    // Follows directly from sequence slicing
  }
}
