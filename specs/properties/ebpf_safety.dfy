// ═══════════════════════════════════════════════════════════
// Property: eBPF Program Safety
// ═══════════════════════════════════════════════════════════
//
// Encodes the constraints that the kernel BPF verifier enforces.
// Any implementation must satisfy these as type-level invariants.

include "../domain/types.dfy"

module EBPFSafety {
  import opened SchedTypes

  const MAX_STACK_DEPTH: nat := 512
  const MAX_CALL_DEPTH: nat := 8
  const MAX_LOOP_BOUND: nat := 1_000_000  // practical upper bound for BPF loops

  // ── Stack safety ────────────────────────────────────────
  // Total stack usage across all nested calls must not exceed 512 bytes.
  predicate StackSafe(stack_usage: nat, call_depth: nat)
  {
    && stack_usage <= MAX_STACK_DEPTH
    && call_depth <= MAX_CALL_DEPTH
  }

  // ── Loop termination ────────────────────────────────────
  // Every loop in a BPF program must have a provable upper bound.
  // In Dafny we enforce this via `decreases` clauses, but we also
  // need the bound to be reasonable for the BPF verifier.
  predicate LoopBounded(iterations: nat)
  {
    iterations <= MAX_LOOP_BOUND
  }

  // ── Helper function whitelist ───────────────────────────
  datatype BPFHelper =
    | ScxBpfDispatch
    | ScxBpfConsume
    | ScxBpfSelectCpuDfl
    | ScxBpfKickCpu
    | BpfGetSmpProcessorId
    | BpfKtimeGetNs
    | BpfTaskStorageGet
    | BpfTaskStorageDelete
    | BpfMapLookupElem
    | BpfMapUpdateElem
    | BpfMapDeleteElem
    | BpfPrintk

  predicate AllowedHelper(h: BPFHelper)
  {
    true  // all listed helpers are allowed in sched_ext context
  }

  // ── Pointer safety ──────────────────────────────────────
  // All array/map accesses must be bounds-checked.
  predicate BoundsChecked(index: nat, length: nat)
  {
    index < length
  }

  // ── Combined eBPF safety invariant ──────────────────────
  predicate EBPFProgramSafe(
    stack_usage: nat,
    call_depth: nat,
    max_loop_iterations: nat,
    helpers_used: set<BPFHelper>
  )
  {
    && StackSafe(stack_usage, call_depth)
    && LoopBounded(max_loop_iterations)
    && (forall h :: h in helpers_used ==> AllowedHelper(h))
  }
}
