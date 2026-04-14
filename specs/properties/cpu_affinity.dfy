// ═══════════════════════════════════════════════════════════
// Property: CPU Affinity Correctness
// ═══════════════════════════════════════════════════════════

include "../domain/types.dfy"

module CpuAffinityProperty {
  import opened SchedTypes

  // A task must never be dispatched to a CPU outside its affinity set.
  predicate AffinityRespected(t: Task, assigned_cpu: nat)
  {
    && assigned_cpu < NUM_CPUS
    && (t.cpu_affinity == {} || assigned_cpu in t.cpu_affinity)
  }

  // System-wide: every running task is on a valid CPU.
  predicate AllAffinitiesRespected(s: SchedState)
    requires ValidState(s)
  {
    forall cpu :: cpu in s.run_queues ==>
      forall t :: t in s.run_queues[cpu].tasks ==>
        AffinityRespected(t, cpu)
  }
}
