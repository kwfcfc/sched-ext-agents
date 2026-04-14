// ═══════════════════════════════════════════════════════════
// Domain model: the world of sched_ext scheduling
// ═══════════════════════════════════════════════════════════
//
// This file defines the core datatypes that every other spec file imports.
// Changes here propagate everywhere — modify with extreme care.

module SchedTypes {

  const NUM_CPUS: nat := 128    // upper bound, runtime config may be smaller
  const MAX_WEIGHT: nat := 1024
  const STACK_LIMIT: nat := 512 // eBPF stack limit in bytes

  datatype TaskState = Runnable | Running | Blocked | Dead

  datatype Task = Task(
    pid: nat,
    vruntime: nat,           // virtual runtime — key fairness metric
    weight: nat,             // scheduling weight (nice-derived)
    state: TaskState,
    cpu_affinity: set<nat>,  // allowed CPUs (empty = all)
    enqueue_time: nat        // timestamp of last enqueue (for starvation detection)
  )

  // A per-CPU run queue, modeled as a sequence sorted by vruntime
  datatype RunQueue = RunQueue(
    cpu: nat,
    tasks: seq<Task>,
    min_vruntime: nat        // monotonically increasing floor
  )

  // Events that drive the scheduler state machine
  datatype SchedEvent =
    | Enqueue(task: Task, flags: EnqueueFlags)
    | Dispatch(cpu: nat)
    | Select(task: Task, prev_cpu: nat)
    | Tick(cpu: nat)
    | TaskDead(pid: nat)
    | CpuOnline(cpu: nat)
    | CpuOffline(cpu: nat)

  datatype EnqueueFlags = EnqueueFlags(
    wakeup: bool,     // SCX_ENQ_WAKE
    last: bool        // SCX_ENQ_LAST — no more tasks to enqueue
  )

  // Global scheduler state
  datatype SchedState = SchedState(
    run_queues: map<nat, RunQueue>,
    all_tasks: set<Task>,
    clock: nat,              // logical clock for ordering
    active_cpus: set<nat>
  )

  // ── Well-formedness predicates ──────────────────────────
  predicate ValidTask(t: Task) {
    && t.weight > 0
    && t.weight <= MAX_WEIGHT
    && (t.cpu_affinity == {} || forall c :: c in t.cpu_affinity ==> c < NUM_CPUS)
  }

  predicate ValidState(s: SchedState) {
    && (forall cpu :: cpu in s.run_queues ==> cpu < NUM_CPUS)
    && (forall cpu :: cpu in s.run_queues ==>
          forall t :: t in s.run_queues[cpu].tasks ==> ValidTask(t))
    && s.active_cpus <= set cpu | cpu in s.run_queues
  }
}
