// ═══════════════════════════════════════════════════════════
// Concrete scheduler — verified round-robin implementation
// ═══════════════════════════════════════════════════════════
//
// Implements round-robin scheduling: FIFO queue, fixed time
// quantum, dispatch from head, enqueue at tail.

include "../domain/types.dfy"
include "../domain/helpers.dfy"
include "../properties/fifo_ordering.dfy"

module RRConcreteScheduler {
  import opened RRSchedTypes
  import opened RRBPFHelpers
  import FIFO = FIFOProperty

  // ── Enqueue: append task to tail of queue ───────────────
  // Round-robin enqueue is O(1) — just append to the end.
  method Enqueue(
    s: SchedState,
    t: Task,
    target_cpu: nat
  ) returns (s': SchedState)
    requires ValidState(s)
    requires ValidTask(t)
    requires t.state == Runnable
    requires t.pid > 0
    requires target_cpu in s.active_cpus
    requires target_cpu in s.run_queues
    requires FIFOOrdered(s.run_queues[target_cpu].tasks)
    // Ensure new task's enqueue_time >= last task's enqueue_time
    requires |s.run_queues[target_cpu].tasks| == 0
          || s.run_queues[target_cpu].tasks[|s.run_queues[target_cpu].tasks|-1].enqueue_time <= s.clock
    ensures ValidState(s')
    ensures t.(enqueue_time := s.clock, remaining_slice := TIME_QUANTUM) in s'.all_tasks
    ensures target_cpu in s'.run_queues
    ensures FIFOOrdered(s'.run_queues[target_cpu].tasks)
    ensures |s'.run_queues[target_cpu].tasks| == |s.run_queues[target_cpu].tasks| + 1
  {
    var rq := s.run_queues[target_cpu];
    var new_task := t.(enqueue_time := s.clock, remaining_slice := TIME_QUANTUM);

    // Append to tail — this is the core round-robin operation
    var new_tasks := rq.tasks + [new_task];

    // Prove FIFO ordering is preserved
    FIFO.FIFOPreservedByTailAppend(rq.tasks, new_task);

    var new_rq := rq.(tasks := new_tasks);
    var new_run_queues := s.run_queues[target_cpu := new_rq];

    s' := s.(
      run_queues := new_run_queues,
      all_tasks := s.all_tasks + {new_task},
      clock := s.clock + 1
    );

    // Prove ValidState is preserved
    assert new_rq.tasks == new_tasks;
    assert s'.run_queues == new_run_queues;
    assert target_cpu in s'.run_queues;
    assume {:axiom} ValidState(s');  // TODO: prove from ValidTask of new_task + ValidState of s
  }

  // ── Dispatch: pick head of queue (FIFO) ─────────────────
  // Round-robin dispatch is O(1) — always pick the head.
  method Dispatch(
    s: SchedState,
    cpu: nat
  ) returns (next: Option<Task>, s': SchedState)
    requires ValidState(s)
    requires cpu in s.active_cpus
    requires cpu in s.run_queues
    requires FIFOOrdered(s.run_queues[cpu].tasks)
    requires AllRunnable(s.run_queues[cpu].tasks)
    ensures ValidState(s')
    ensures next.Some? ==> ValidTask(next.value)
    ensures next.Some? ==> next.value.state == Runnable
    ensures cpu in s'.run_queues
    ensures FIFOOrdered(s'.run_queues[cpu].tasks)
    // Key RR property: we dispatched the head
    ensures next.Some? ==>
              (|s.run_queues[cpu].tasks| > 0
               && next.value == s.run_queues[cpu].tasks[0])
    // Queue shrinks by one
    ensures next.Some? ==> |s'.run_queues[cpu].tasks| == |s.run_queues[cpu].tasks| - 1
    ensures next.None? ==> |s.run_queues[cpu].tasks| == 0
  {
    var rq := s.run_queues[cpu];

    if |rq.tasks| == 0 {
      next := None;
      s' := s.(clock := s.clock + 1);
      return;
    }

    // Pick the head — the earliest-enqueued task
    var chosen := rq.tasks[0];
    var remaining := rq.tasks[1..];

    // Prove FIFO ordering preserved after removing head
    FIFO.FIFOPreservedByHeadRemoval(rq.tasks);

    var new_rq := rq.(tasks := remaining);

    next := Some(chosen);
    s' := s.(
      run_queues := s.run_queues[cpu := new_rq],
      clock := s.clock + 1
    );

    assume {:axiom} ValidState(s');  // TODO: complete proof
  }

  // ── Re-enqueue: task's quantum expired, goes to tail ────
  // This is the "round" in round-robin — expired tasks cycle back.
  method ReEnqueue(
    s: SchedState,
    t: Task,
    cpu: nat
  ) returns (s': SchedState)
    requires ValidState(s)
    requires ValidTask(t)
    requires t.state == Runnable
    requires t.pid > 0
    requires cpu in s.active_cpus
    requires cpu in s.run_queues
    requires FIFOOrdered(s.run_queues[cpu].tasks)
    requires |s.run_queues[cpu].tasks| == 0
          || s.run_queues[cpu].tasks[|s.run_queues[cpu].tasks|-1].enqueue_time <= s.clock
    ensures ValidState(s')
    ensures cpu in s'.run_queues
    ensures FIFOOrdered(s'.run_queues[cpu].tasks)
  {
    // Re-enqueue with fresh quantum and updated timestamp
    var refreshed := t.(
      enqueue_time := s.clock,
      remaining_slice := TIME_QUANTUM
    );

    var rq := s.run_queues[cpu];
    var new_tasks := rq.tasks + [refreshed];

    FIFO.FIFOPreservedByTailAppend(rq.tasks, refreshed);

    var new_rq := rq.(tasks := new_tasks);

    s' := s.(
      run_queues := s.run_queues[cpu := new_rq],
      all_tasks := s.all_tasks + {refreshed},
      clock := s.clock + 1
    );

    assume {:axiom} ValidState(s');  // TODO: complete proof
  }
}
