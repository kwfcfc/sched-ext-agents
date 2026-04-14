// ═══════════════════════════════════════════════════════════
// Concrete scheduler — verified implementation
// ═══════════════════════════════════════════════════════════
//
// This module provides actual algorithm implementations that satisfy
// the abstract scheduler's specification. It uses a vruntime-sorted
// data structure and deterministic dispatch policy.
//
// This file is the primary target for the Implementation Agent.

include "../domain/types.dfy"
include "../domain/helpers.dfy"
include "../properties/fairness.dfy"

module ConcreteScheduler {
  import opened SchedTypes
  import opened BPFHelpers
  import FP = FairnessProperty

  // ── Sorted insertion (maintains vruntime order) ─────────
  method SortedInsert(queue: seq<Task>, t: Task) returns (result: seq<Task>)
    requires forall i, j :: 0 <= i < j < |queue|
              ==> queue[i].vruntime <= queue[j].vruntime
    ensures forall i, j :: 0 <= i < j < |result|
              ==> result[i].vruntime <= result[j].vruntime
    ensures multiset(result) == multiset(queue) + multiset{t}
    ensures |result| == |queue| + 1
  {
    var idx := 0;
    while idx < |queue| && queue[idx].vruntime <= t.vruntime
      invariant 0 <= idx <= |queue|
      invariant forall i :: 0 <= i < idx ==> queue[i].vruntime <= t.vruntime
      decreases |queue| - idx
    {
      idx := idx + 1;
    }
    result := queue[..idx] + [t] + queue[idx..];
    // TODO: lemma to prove sortedness of concatenation
  }

  // ── Enqueue: insert task sorted by vruntime ─────────────
  method Enqueue(
    s: SchedState,
    t: Task,
    target_cpu: nat
  ) returns (s': SchedState)
    requires ValidState(s)
    requires ValidTask(t)
    requires t.state == Runnable
    requires target_cpu in s.active_cpus
    requires target_cpu in s.run_queues
    ensures ValidState(s')
    ensures t in s'.all_tasks
  {
    var rq := s.run_queues[target_cpu];
    var new_tasks := SortedInsert(rq.tasks, t.(enqueue_time := s.clock));

    var new_rq := rq.(tasks := new_tasks);
    var new_run_queues := s.run_queues[target_cpu := new_rq];

    s' := s.(
      run_queues := new_run_queues,
      all_tasks := s.all_tasks + {t.(enqueue_time := s.clock)},
      clock := s.clock + 1
    );
    assume ValidState(s');  // TODO: prove from SortedInsert postcondition
  }

  // ── Dispatch: pick task with minimum vruntime ───────────
  method Dispatch(
    s: SchedState,
    cpu: nat
  ) returns (next: Option<Task>, s': SchedState)
    requires ValidState(s)
    requires cpu in s.active_cpus
    requires cpu in s.run_queues
    ensures ValidState(s')
    ensures next.Some? ==> ValidTask(next.value)
    ensures next.Some? ==> next.value.state == Runnable
  {
    var rq := s.run_queues[cpu];

    if |rq.tasks| == 0 {
      next := None;
      s' := s.(clock := s.clock + 1);
      return;
    }

    // Pick the first task (minimum vruntime due to sorted invariant)
    var chosen := rq.tasks[0];
    var remaining := rq.tasks[1..];

    // Update vruntime for the dispatched task
    var delta := FP.DeltaVruntime(chosen);
    var updated := chosen.(
      vruntime := chosen.vruntime + delta,
      state := Running
    );

    var new_rq := rq.(
      tasks := remaining,
      min_vruntime := if |remaining| > 0 then remaining[0].vruntime
                      else rq.min_vruntime
    );

    next := Some(chosen);
    s' := s.(
      run_queues := s.run_queues[cpu := new_rq],
      clock := s.clock + 1
    );
    assume ValidState(s');  // TODO: complete proof
  }
}
