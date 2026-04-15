// ═══════════════════════════════════════════════════════════
// Domain model: Round-Robin sched_ext scheduling
// ═══════════════════════════════════════════════════════════
//
// Core datatypes for a simple round-robin scheduler.
// Key difference from vtime scheduler: no vruntime field,
// tasks are ordered purely by enqueue time (FIFO).

module RRSchedTypes {

  const NUM_CPUS: nat := 128
  const MAX_TASKS: nat := 4096
  const STACK_LIMIT: nat := 512     // eBPF stack limit in bytes
  const TIME_QUANTUM: nat := 5_000_000  // 5ms in nanoseconds

  datatype TaskState = Runnable | Running | Blocked | Dead

  datatype Task = Task(
    pid: nat,
    state: TaskState,
    cpu_affinity: set<nat>,   // allowed CPUs (empty = all)
    enqueue_time: nat,        // timestamp of last enqueue (FIFO key)
    remaining_slice: nat      // remaining time in current quantum
  )

  // A per-CPU run queue — FIFO: head is next to dispatch, tail is last enqueued
  datatype RunQueue = RunQueue(
    cpu: nat,
    tasks: seq<Task>
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
    wakeup: bool,
    last: bool
  )

  // Global scheduler state
  datatype SchedState = SchedState(
    run_queues: map<nat, RunQueue>,
    all_tasks: set<Task>,
    clock: nat,
    active_cpus: set<nat>
  )

  // ── Well-formedness predicates ──────────────────────────
  predicate ValidTask(t: Task) {
    && t.pid > 0
    && t.remaining_slice <= TIME_QUANTUM
    && (t.cpu_affinity == {} || forall c :: c in t.cpu_affinity ==> c < NUM_CPUS)
  }

  predicate ValidState(s: SchedState) {
    && (forall cpu :: cpu in s.run_queues ==> cpu < NUM_CPUS)
    && (forall cpu :: cpu in s.run_queues ==>
          forall t :: t in s.run_queues[cpu].tasks ==> ValidTask(t))
    && s.active_cpus <= set cpu | cpu in s.run_queues
  }

  // ── FIFO ordering predicate ─────────────────────────────
  // Tasks in a run queue are ordered by enqueue_time (earliest first)
  predicate FIFOOrdered(tasks: seq<Task>) {
    forall i, j :: 0 <= i < j < |tasks|
      ==> tasks[i].enqueue_time <= tasks[j].enqueue_time
  }

  // ── Helper: all tasks in queue are runnable ─────────────
  predicate AllRunnable(tasks: seq<Task>) {
    forall i :: 0 <= i < |tasks| ==> tasks[i].state == Runnable
  }
}
