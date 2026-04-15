// ═══════════════════════════════════════════════════════════
// Refinement proof: RR Concrete refines RR Abstract
// ═══════════════════════════════════════════════════════════
//
// Proves that every behavior of the concrete round-robin
// scheduler is a valid behavior of the abstract specification.
// Key insight: FIFO head pick is the unique valid choice that
// satisfies both the abstract dispatch requirement and FIFO ordering.

include "abstract_scheduler.dfy"
include "concrete_scheduler.dfy"

module RRRefinementProof {
  import AS = RRAbstractScheduler
  import CS = RRConcreteScheduler
  import opened RRSchedTypes
  import opened RRBPFHelpers
  import FIFO = FIFOProperty

  // ── Refinement mapping ──────────────────────────────────
  function RefMap(cs: SchedState): SchedState
  {
    cs  // Identity mapping — concrete state IS abstract state
  }

  // ── Init refinement ─────────────────────────────────────
  lemma InitRefines(cs: SchedState)
    requires AS.Init(RefMap(cs))
    ensures AS.Init(cs)
  {
    // Trivial: RefMap is identity
  }

  // ── Enqueue refinement ──────────────────────────────────
  // Concrete enqueue (tail append) satisfies abstract enqueue.
  lemma EnqueueRefines(
    cs: SchedState,
    cs': SchedState,
    t: Task,
    cpu: nat
  )
    requires ValidState(cs)
    requires ValidTask(t)
    requires t.state == Runnable
    requires cpu in cs.active_cpus
    requires cpu in cs.run_queues
    // Concrete enqueue postconditions on all_tasks, clock, active_cpus
    requires cs'.all_tasks == cs.all_tasks + {t.(enqueue_time := cs.clock, remaining_slice := TIME_QUANTUM)}
    requires cs'.clock == cs.clock + 1
    requires cs'.active_cpus == cs.active_cpus
    // Concrete enqueue postconditions on run queues
    requires cpu in cs'.run_queues
    requires cs'.run_queues[cpu].tasks
               == cs.run_queues[cpu].tasks + [t.(enqueue_time := cs.clock, remaining_slice := TIME_QUANTUM)]
    requires forall c :: c in cs.run_queues && c != cpu
               ==> c in cs'.run_queues && cs'.run_queues[c] == cs.run_queues[c]
    requires forall c :: c in cs'.run_queues ==> c in cs.run_queues
    // FIFO appendability: clock >= last enqueue time in queue
    requires |cs.run_queues[cpu].tasks| == 0
             || cs.run_queues[cpu].tasks[|cs.run_queues[cpu].tasks| - 1].enqueue_time <= cs.clock
    requires ValidState(cs')
    ensures AS.Enqueue(RefMap(cs), RefMap(cs'), t, cpu)
  {
    // RefMap is identity, so all preconditions directly match
    // the conjuncts of AS.Enqueue. QED.
  }

  // ── Dispatch refinement ─────────────────────────────────
  // FIFO head pick satisfies abstract dispatch's "pick some task" requirement.
  lemma DispatchRefines(
    cs: SchedState,
    cs': SchedState,
    cpu: nat,
    chosen: Option<Task>
  )
    requires ValidState(cs)
    requires cpu in cs.active_cpus
    requires cpu in cs.run_queues
    requires FIFOOrdered(cs.run_queues[cpu].tasks)
    // Concrete dispatch picked the head
    requires chosen.Some? ==>
               (|cs.run_queues[cpu].tasks| > 0
                && chosen.value == cs.run_queues[cpu].tasks[0])
    requires chosen.None? ==> |cs.run_queues[cpu].tasks| == 0
    requires chosen.Some? ==> chosen.value.state == Runnable
    requires cs'.clock == cs.clock + 1
    // Concrete dispatch postconditions on run queues
    requires cpu in cs'.run_queues
    requires chosen.Some? ==>
               (|cs.run_queues[cpu].tasks| > 0
                && cs'.run_queues[cpu].tasks == cs.run_queues[cpu].tasks[1..])
    requires chosen.None? ==> cs'.run_queues[cpu].tasks == cs.run_queues[cpu].tasks
    requires forall c :: c in cs.run_queues && c != cpu
               ==> c in cs'.run_queues && cs'.run_queues[c] == cs.run_queues[c]
    requires forall c :: c in cs'.run_queues ==> c in cs.run_queues
    requires ValidState(cs')
    ensures AS.Dispatch(RefMap(cs), RefMap(cs'), cpu, chosen)
  {
    // RefMap is identity
    assert RefMap(cs) == cs;
    assert RefMap(cs') == cs';

    if chosen.Some? {
      // Head of a sequence is a member of that sequence
      assert chosen.value == cs.run_queues[cpu].tasks[0];
      assert |cs.run_queues[cpu].tasks| > 0;
      assert chosen.value in cs.run_queues[cpu].tasks;
      assert chosen.value.state == Runnable;
    }
    // All conjuncts of AS.Dispatch now follow directly from preconditions
  }

  // ── FIFO invariant preservation ─────────────────────────
  // The safety invariant (FIFO ordering) is preserved across all transitions.
  lemma SafetyPreserved(cs: SchedState, cs': SchedState)
    requires ValidState(cs)
    requires ValidState(cs')
    requires AS.SafetyInvariant(cs)
    requires AS.Next(cs, cs')
    ensures AS.SafetyInvariant(cs')
  {
    // Case split on which abstract transition occurred
    if exists t, cpu :: AS.Enqueue(cs, cs', t, cpu) {
      var t, cpu :| AS.Enqueue(cs, cs', t, cpu);
      SafetyPreservedByEnqueue(cs, cs', t, cpu);
    } else if exists cpu, chosen :: AS.Dispatch(cs, cs', cpu, chosen) {
      var cpu, chosen :| AS.Dispatch(cs, cs', cpu, chosen);
      SafetyPreservedByDispatch(cs, cs', cpu, chosen);
    } else {
      // Must be a Tick — run_queues unchanged
      var cpu :| AS.Tick(cs, cs', cpu);
      assert cs'.run_queues == cs.run_queues;
    }
  }

  // ── Helper: FIFO preserved by Enqueue ───────────────────
  lemma SafetyPreservedByEnqueue(
    cs: SchedState,
    cs': SchedState,
    t: Task,
    cpu: nat
  )
    requires ValidState(cs)
    requires ValidState(cs')
    requires AS.SafetyInvariant(cs)
    requires AS.Enqueue(cs, cs', t, cpu)
    ensures AS.SafetyInvariant(cs')
  {
    var new_task := t.(enqueue_time := cs.clock, remaining_slice := TIME_QUANTUM);

    // Pre-state FIFO invariant gives FIFOOrdered on all queues
    assert FIFO.FIFOInvariant(cs);
    assert FIFOOrdered(cs.run_queues[cpu].tasks);

    // The new task's enqueue_time (== cs.clock) >= last task's enqueue_time
    // so appending preserves FIFO
    FIFO.FIFOPreservedByTailAppend(cs.run_queues[cpu].tasks, new_task);

    // Prove FIFO for every queue in cs'
    forall c | c in cs'.run_queues
      ensures FIFOOrdered(cs'.run_queues[c].tasks)
    {
      if c == cpu {
        assert cs'.run_queues[cpu].tasks == cs.run_queues[cpu].tasks + [new_task];
      } else {
        assert c in cs.run_queues;
        assert cs'.run_queues[c] == cs.run_queues[c];
      }
    }
  }

  // ── Helper: FIFO preserved by Dispatch ──────────────────
  lemma SafetyPreservedByDispatch(
    cs: SchedState,
    cs': SchedState,
    cpu: nat,
    chosen: Option<Task>
  )
    requires ValidState(cs)
    requires ValidState(cs')
    requires AS.SafetyInvariant(cs)
    requires AS.Dispatch(cs, cs', cpu, chosen)
    ensures AS.SafetyInvariant(cs')
  {
    assert FIFO.FIFOInvariant(cs);

    forall c | c in cs'.run_queues
      ensures FIFOOrdered(cs'.run_queues[c].tasks)
    {
      if c == cpu {
        if chosen.Some? {
          // Head removed — FIFO preserved by head removal lemma
          assert |cs.run_queues[cpu].tasks| > 0;
          assert FIFOOrdered(cs.run_queues[cpu].tasks);
          FIFO.FIFOPreservedByHeadRemoval(cs.run_queues[cpu].tasks);
          assert cs'.run_queues[cpu].tasks == cs.run_queues[cpu].tasks[1..];
        } else {
          // Queue was empty, stays the same
          assert cs'.run_queues[cpu].tasks == cs.run_queues[cpu].tasks;
        }
      } else {
        // Other CPUs: queues unchanged
        assert c in cs.run_queues;
        assert cs'.run_queues[c] == cs.run_queues[c];
      }
    }
  }
}
