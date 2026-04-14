# Atomicity Boundaries

> Each Dafny action is one atomic step. This document maps each action
> to the mechanism that guarantees atomicity in the C/eBPF implementation.

## Why This Matters

If the C implementation can be interrupted mid-way through what Dafny models
as a single atomic step, other threads/CPUs may observe an inconsistent
intermediate state. The Dafny proofs assume atomicity; if reality breaks
that assumption, the proofs don't hold.

## Mapping

### Enqueue (Dafny: one atomic step)

**C function**: `s_enqueue()`
**Atomicity mechanism**: Kernel holds `rq_lock` before calling `ops.enqueue()`

The entire function body executes with the per-CPU runqueue lock held.
No other scheduling operation on the same CPU can interleave. Cross-CPU
visibility is handled by the lock's memory barrier semantics.

**What's covered**: Reading/writing task_ctx via task-local storage,
calling `scx_bpf_dispatch()`.

**What's NOT covered**: If `s_enqueue` accesses a shared BPF map that
other CPUs also access, the map operation itself is atomic (per-element),
but a read-modify-write sequence across multiple map entries is NOT atomic.
Use `bpf_spin_lock` if multi-entry atomicity is needed.

### Dispatch (Dafny: one atomic step)

**C function**: `s_dispatch()`
**Atomicity mechanism**: Kernel holds `rq_lock`

Same as enqueue — full function body is atomic w.r.t. per-CPU state.

### Select CPU (Dafny: one atomic step, no shared mutation)

**C function**: `s_select_cpu()`
**Atomicity mechanism**: None needed (read-only suggestion)

`select_cpu` runs WITHOUT `rq_lock`. It returns a CPU number as a hint.
The Dafny model must NOT assume this function can mutate shared state.
Any state it reads may be stale by the time the hint is acted upon.

### Tick / vruntime update (Dafny: one atomic step)

**C function**: `s_running()` (called when task starts, updates vruntime)
**Atomicity mechanism**: `rq_lock` held

The vruntime update (`ctx->vruntime += delta`) is a single 64-bit store
which is atomic on x86_64. On architectures without 64-bit atomic stores,
this would need `__sync_fetch_and_add`.

### Task Exit (Dafny: one atomic step)

**C function**: `s_exit_task()`
**Atomicity mechanism**: Kernel ensures task is not scheduled during exit

No `rq_lock` held, but the kernel guarantees the task is not on any
runqueue when `exit_task` is called. No concurrent scheduling decisions
can reference a dead task.

## Red Flags to Watch For

1. **Shared map access from enqueue + dispatch on different CPUs**: Both hold
   their own CPU's `rq_lock`, but these are DIFFERENT locks. Access to a
   global BPF_MAP_TYPE_HASH is NOT serialized between CPUs. Use per-CPU
   maps or `bpf_spin_lock`.

2. **Statistics counters**: `total_enqueues++` from multiple CPUs is a data
   race. Use `BPF_MAP_TYPE_PERCPU_ARRAY` for counters, aggregate in userspace.

3. **Global min_vruntime update**: If multiple CPUs update a global
   `min_vruntime`, use `__sync_val_compare_and_swap` to avoid lost updates.
