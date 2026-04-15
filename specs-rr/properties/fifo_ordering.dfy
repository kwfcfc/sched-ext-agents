// ═══════════════════════════════════════════════════════════
// Property: FIFO Dispatch Ordering
// ═══════════════════════════════════════════════════════════
//
// The core invariant of round-robin: tasks are dispatched in
// the order they were enqueued. The queue is always FIFO-ordered,
// and dispatch always picks the head.

include "../domain/types.dfy"

module FIFOProperty {
  import opened RRSchedTypes

  // ── Main FIFO predicate ─────────────────────────────────
  // All run queues maintain FIFO ordering by enqueue_time.
  predicate FIFOInvariant(s: SchedState)
    requires ValidState(s)
  {
    forall cpu :: cpu in s.run_queues ==>
      FIFOOrdered(s.run_queues[cpu].tasks)
  }

  // ── Dispatch correctness ────────────────────────────────
  // If there are tasks in the queue, dispatch returns the head
  // (the task with the earliest enqueue_time).
  predicate DispatchReturnsHead(rq: RunQueue, dispatched: Task)
  {
    && |rq.tasks| > 0
    && dispatched == rq.tasks[0]
    && dispatched.state == Runnable
  }

  // ── Enqueue correctness ─────────────────────────────────
  // After enqueue, the new task is at the tail and FIFO is preserved.
  predicate EnqueueAtTail(old_tasks: seq<Task>, new_tasks: seq<Task>, t: Task)
  {
    && |new_tasks| == |old_tasks| + 1
    && new_tasks == old_tasks + [t]
    && (FIFOOrdered(old_tasks) && (|old_tasks| == 0 || old_tasks[|old_tasks|-1].enqueue_time <= t.enqueue_time)
        ==> FIFOOrdered(new_tasks))
  }

  // ── FIFO preservation lemma ─────────────────────────────
  // Appending to the tail with a timestamp >= last preserves FIFO.
  lemma FIFOPreservedByTailAppend(tasks: seq<Task>, t: Task)
    requires FIFOOrdered(tasks)
    requires |tasks| == 0 || tasks[|tasks|-1].enqueue_time <= t.enqueue_time
    ensures FIFOOrdered(tasks + [t])
  {
    var result := tasks + [t];
    forall i, j | 0 <= i < j < |result|
      ensures result[i].enqueue_time <= result[j].enqueue_time
    {
      if j < |tasks| {
        // Both in original — FIFO ordering gives us this
        assert result[i] == tasks[i];
        assert result[j] == tasks[j];
      } else {
        // j == |tasks|, so result[j] == t
        assert result[j] == t;
        if i < |tasks| {
          // result[i] is in original, and t >= last >= all
          assert result[i] == tasks[i];
          if |tasks| > 0 {
            // tasks[i] <= tasks[|tasks|-1] <= t
            assert tasks[i].enqueue_time <= tasks[|tasks|-1].enqueue_time;
          }
        }
      }
    }
  }

  // ── FIFO preserved after dispatch (removing head) ───────
  lemma FIFOPreservedByHeadRemoval(tasks: seq<Task>)
    requires |tasks| > 0
    requires FIFOOrdered(tasks)
    ensures FIFOOrdered(tasks[1..])
  {
    var tail := tasks[1..];
    forall i, j | 0 <= i < j < |tail|
      ensures tail[i].enqueue_time <= tail[j].enqueue_time
    {
      assert tail[i] == tasks[i+1];
      assert tail[j] == tasks[j+1];
    }
  }
}
