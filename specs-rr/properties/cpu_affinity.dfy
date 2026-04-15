// ═══════════════════════════════════════════════════════════
// Property: CPU Affinity Correctness (Round-Robin)
// ═══════════════════════════════════════════════════════════

include "../domain/types.dfy"

module RRCpuAffinityProperty {
  import opened RRSchedTypes

  predicate AffinityRespected(t: Task, assigned_cpu: nat)
  {
    && assigned_cpu < NUM_CPUS
    && (t.cpu_affinity == {} || assigned_cpu in t.cpu_affinity)
  }

  predicate AllAffinitiesRespected(s: SchedState)
    requires ValidState(s)
  {
    forall cpu :: cpu in s.run_queues ==>
      forall t :: t in s.run_queues[cpu].tasks ==>
        AffinityRespected(t, cpu)
  }
}
