# eBPF Verifier Constraints

The kernel's BPF verifier statically analyzes every BPF program before loading.
Any violation results in program rejection. These constraints MUST be reflected
in the Dafny specification.

## Hard Limits

| Constraint              | Limit            | Dafny modeling approach              |
|-------------------------|------------------|--------------------------------------|
| Max instructions        | 1M (verified)    | Not modeled (too low-level)          |
| Max stack depth         | 512 bytes        | `requires stack_usage <= 512`        |
| Max call chain depth    | 8 frames         | `requires call_depth <= 8`           |
| Loop bound              | Must be provable | `decreases` clause on every loop     |
| Map lookup              | May return NULL  | `Option<T>` return type              |
| Pointer arithmetic      | Bounds-checked   | `requires 0 <= idx < len`            |

## Bounded Loops

The verifier must prove that every loop terminates. In practice:
- Use `bpf_loop()` helper for counted iteration (kernel >= 5.17)
- Or use a `for` loop with a compile-time constant bound
- The verifier unrolls small loops and tracks state per iteration

In Dafny, model this as:
```dafny
while i < n
  invariant 0 <= i <= n
  decreases n - i
```

## Allowed Helper Functions (sched_ext context)

These helpers are available in sched_ext BPF programs:
- `scx_bpf_dispatch()` — dispatch task to a DSQ
- `scx_bpf_consume()` — consume from a DSQ
- `scx_bpf_select_cpu_dfl()` — default CPU selection
- `scx_bpf_kick_cpu()` — wake up an idle CPU
- `scx_bpf_get_online_cpumask()` — get online CPU mask
- `bpf_get_smp_processor_id()` — current CPU
- `bpf_ktime_get_ns()` — monotonic timestamp
- `bpf_task_storage_get/delete()` — per-task storage
- `bpf_map_lookup_elem/update_elem/delete_elem()` — map operations
- `bpf_printk()` — debug logging (debug builds only)

## Disallowed Operations

- No memory allocation (no `malloc`, `kmalloc`)
- No sleeping (no `schedule()`, `msleep()`)
- No floating point arithmetic
- No direct kernel memory access (only through helpers)
- No calling arbitrary kernel functions
- No accessing user-space memory without `bpf_probe_read()`

## Map Operation Semantics

```c
// Lookup: returns pointer to value or NULL
void *bpf_map_lookup_elem(map, key);
// MUST check for NULL before dereferencing

// Update: returns 0 on success, negative on error
int bpf_map_update_elem(map, key, value, flags);
// flags: BPF_ANY (create or update), BPF_NOEXIST (create only), BPF_EXIST (update only)
// Can fail with -ENOMEM if map is full
```

In Dafny, model lookups as `Option<V>` and updates as potentially failing operations.
