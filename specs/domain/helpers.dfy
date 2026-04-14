// ═══════════════════════════════════════════════════════════
// BPF helper function contracts
// ═══════════════════════════════════════════════════════════
//
// Each helper models a real BPF helper from the kernel.
// The pre/post conditions capture what the kernel guarantees.
// These are used by the Verify Agent to check spec completeness.

include "types.dfy"

module BPFHelpers {
  import opened SchedTypes

  // ── scx_bpf_dispatch() ──────────────────────────────────
  // Dispatches a task to a CPU's local DSQ.
  // Kernel constraint: must be called from ops.enqueue() or ops.dispatch()
  method {:extern} scx_bpf_dispatch(
    t: Task,
    dsq_id: nat,
    slice_ns: nat,       // time slice in nanoseconds
    enq_flags: nat
  )
    requires ValidTask(t)
    requires t.state == Runnable
    requires dsq_id < NUM_CPUS || dsq_id == SCX_DSQ_GLOBAL
    ensures t.state == Runnable  // task is now on the dispatch queue

  const SCX_DSQ_GLOBAL: nat := 0xFFFFFFFF  // global shared DSQ

  // ── scx_bpf_consume() ──────────────────────────────────
  // Consume a task from a DSQ into the CPU's local queue.
  // Called from ops.dispatch().
  method {:extern} scx_bpf_consume(dsq_id: nat) returns (found: bool)
    requires dsq_id < NUM_CPUS || dsq_id == SCX_DSQ_GLOBAL
    // If found, exactly one task was moved to the local CPU's run queue

  // ── bpf_get_smp_processor_id() ──────────────────────────
  // Returns the current CPU number. Always succeeds.
  function {:extern} bpf_get_smp_processor_id(): nat
    ensures bpf_get_smp_processor_id() < NUM_CPUS

  // ── bpf_ktime_get_ns() ─────────────────────────────────
  // Returns monotonic clock in nanoseconds.
  function {:extern} bpf_ktime_get_ns(): nat
    ensures bpf_ktime_get_ns() > 0

  // ── bpf_map operations (modeled as Dafny maps) ─────────
  // In real eBPF, these are bpf_map_lookup_elem / bpf_map_update_elem.
  // We model them as pure functions on Dafny maps for verification.

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
