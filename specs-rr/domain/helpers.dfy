// ═══════════════════════════════════════════════════════════
// BPF helper function contracts (Round-Robin version)
// ═══════════════════════════════════════════════════════════

include "types.dfy"

module RRBPFHelpers {
  import opened RRSchedTypes

  // ── scx_bpf_dispatch() ──────────────────────────────────
  method {:extern} {:axiom} scx_bpf_dispatch(
    t: Task,
    dsq_id: nat,
    slice_ns: nat,
    enq_flags: nat
  )
    requires ValidTask(t)
    requires t.state == Runnable
    requires dsq_id < NUM_CPUS || dsq_id == SCX_DSQ_GLOBAL
    ensures t.state == Runnable

  const SCX_DSQ_GLOBAL: nat := 0xFFFFFFFF

  // ── scx_bpf_consume() ──────────────────────────────────
  method {:extern} {:axiom} scx_bpf_consume(dsq_id: nat) returns (found: bool)
    requires dsq_id < NUM_CPUS || dsq_id == SCX_DSQ_GLOBAL

  // ── bpf_get_smp_processor_id() ──────────────────────────
  function {:extern} {:axiom} bpf_get_smp_processor_id(): nat
    ensures bpf_get_smp_processor_id() < NUM_CPUS

  // ── bpf_ktime_get_ns() ─────────────────────────────────
  function {:extern} {:axiom} bpf_ktime_get_ns(): nat
    ensures bpf_ktime_get_ns() > 0

  // ── Map operations ─────────────────────────────────────
  function map_lookup<K, V>(m: map<K, V>, key: K): Option<V>
  {
    if key in m then Some(m[key]) else None
  }

  function map_update<K, V>(m: map<K, V>, key: K, val: V): map<K, V>
  {
    m[key := val]
  }

  datatype Option<T> = Some(value: T) | None
}
