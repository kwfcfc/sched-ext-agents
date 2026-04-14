# BPF Helper Functions — Semantics and Contracts

## scx_bpf_dispatch()

```
void scx_bpf_dispatch(struct task_struct *p, u64 dsq_id, u64 slice, u64 enq_flags)
```

**Semantics**: Places task `p` onto dispatch queue `dsq_id` with time slice `slice` ns.

**Pre-conditions**:
- `p` must be a valid, non-NULL task pointer
- `p` must be in a runnable state
- `dsq_id` must be either `SCX_DSQ_GLOBAL`, `SCX_DSQ_LOCAL`, or a valid custom DSQ
- Can only be called from `ops.enqueue()` or `ops.dispatch()` context

**Post-conditions**:
- Task is placed at the tail of the specified DSQ
- Task retains its runnable state
- If `dsq_id == SCX_DSQ_LOCAL`, task goes to the current CPU's local queue

**Failure modes**: None documented; if DSQ is invalid, kernel logs a warning.

**Dafny contract**:
```dafny
method scx_bpf_dispatch(t: Task, dsq_id: nat, slice: nat, flags: nat)
  requires ValidTask(t) && t.state == Runnable
  requires dsq_id < NUM_CPUS || dsq_id == SCX_DSQ_GLOBAL
  ensures t in target_dsq.tasks
```

---

## scx_bpf_consume()

```
bool scx_bpf_consume(u64 dsq_id)
```

**Semantics**: Moves one task from `dsq_id` to the calling CPU's local DSQ.

**Pre-conditions**:
- Can only be called from `ops.dispatch()` context
- `dsq_id` must be valid

**Post-conditions**:
- Returns `true` if a task was moved, `false` if DSQ was empty
- The moved task becomes the next candidate for execution on this CPU

**Dafny contract**:
```dafny
method scx_bpf_consume(dsq_id: nat) returns (found: bool)
  requires dsq_id < NUM_CPUS || dsq_id == SCX_DSQ_GLOBAL
  ensures found ==> |local_dsq'.tasks| == |local_dsq.tasks| + 1
```

---

## bpf_get_smp_processor_id()

```
u32 bpf_get_smp_processor_id(void)
```

**Semantics**: Returns the ID of the CPU currently executing this BPF program.

**Pre-conditions**: None (always succeeds).

**Post-conditions**: Return value is in `[0, nr_cpu_ids)`.

**Note**: The value is stable for the duration of the BPF program execution (preemption is disabled in BPF context).

---

## bpf_ktime_get_ns()

```
u64 bpf_ktime_get_ns(void)
```

**Semantics**: Returns the current kernel monotonic time in nanoseconds.

**Post-conditions**:
- Return value > 0
- Monotonically non-decreasing (but two calls in the same BPF program may return the same value)
- Not wall-clock time; not affected by NTP adjustments

---

## bpf_task_storage_get()

```
void *bpf_task_storage_get(struct bpf_map *map, struct task_struct *task, void *value, u64 flags)
```

**Semantics**: Get per-task storage associated with `task` in `map`.

**Pre-conditions**:
- `map` must be of type `BPF_MAP_TYPE_TASK_STORAGE`
- `task` must be a valid task pointer

**Post-conditions**:
- If storage exists: returns pointer to the stored value
- If storage does not exist and `flags & BPF_LOCAL_STORAGE_GET_F_CREATE`:
  creates storage initialized with `*value`, returns pointer
- If storage does not exist and no CREATE flag: returns NULL

**Critical**: Return value MUST be NULL-checked before dereferencing.

---

## bpf_map_lookup_elem() / bpf_map_update_elem()

```
void *bpf_map_lookup_elem(struct bpf_map *map, const void *key)
long bpf_map_update_elem(struct bpf_map *map, const void *key, const void *value, u64 flags)
```

**Lookup semantics**:
- Returns pointer to value if key exists, NULL otherwise
- Returned pointer is valid only for the duration of BPF program execution
- MUST NULL-check before use

**Update semantics**:
- `BPF_ANY` (0): create or update
- `BPF_NOEXIST` (1): create only, fail if exists
- `BPF_EXIST` (2): update only, fail if not exists
- Returns 0 on success, negative errno on failure
- Can fail with `-ENOMEM` if map is full (for hash maps)
- Can fail with `-EEXIST` or `-ENOENT` depending on flags

**Dafny modeling**: Use `Option<V>` for lookups, `bool` success for updates.
