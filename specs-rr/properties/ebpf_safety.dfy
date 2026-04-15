// ═══════════════════════════════════════════════════════════
// Property: eBPF Program Safety (Round-Robin)
// ═══════════════════════════════════════════════════════════

include "../domain/types.dfy"

module RREBPFSafety {
  import opened RRSchedTypes

  const MAX_STACK_DEPTH: nat := 512
  const MAX_CALL_DEPTH: nat := 8
  const MAX_LOOP_BOUND: nat := 1_000_000

  predicate StackSafe(stack_usage: nat, call_depth: nat)
  {
    && stack_usage <= MAX_STACK_DEPTH
    && call_depth <= MAX_CALL_DEPTH
  }

  predicate LoopBounded(iterations: nat)
  {
    iterations <= MAX_LOOP_BOUND
  }

  datatype BPFHelper =
    | ScxBpfDispatch
    | ScxBpfConsume
    | ScxBpfSelectCpuDfl
    | BpfGetSmpProcessorId
    | BpfKtimeGetNs
    | BpfTaskStorageGet
    | BpfTaskStorageDelete
    | BpfMapLookupElem
    | BpfMapUpdateElem
    | BpfPrintk

  predicate AllowedHelper(h: BPFHelper)
  {
    true
  }

  predicate BoundsChecked(index: nat, length: nat)
  {
    index < length
  }

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
