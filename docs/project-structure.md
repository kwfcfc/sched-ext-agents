# Project Structure

```
verified-sched-ext/
│
├── README.md
├── Makefile                          # Top-level build orchestration
├── pyproject.toml                    # Python project config (agents are Python)
├── dafny-project.toml                # Dafny project config
├── .env.example                      # API keys, model configs
├── .gitignore
│
├── .github/
│   └── workflows/
│       ├── verify.yml                # CI: run dafny verify on every PR
│       ├── build-bpf.yml             # CI: compile eBPF, run BPF verifier
│       └── test.yml                  # CI: trace tests + fuzz + perf
│
├── .vscode/
│   ├── settings.json                 # Dafny LSP + clangd config
│   └── tasks.json                    # Build/verify tasks
│
│
│ ════════════════════════════════════════════════════════════
│  FORMAL SPECIFICATIONS (Dafny)
│  The mathematical ground truth. Everything else derives from here.
│ ════════════════════════════════════════════════════════════
│
├── specs/
│   │
│   ├── domain/                       # Domain model — the "world" of scheduling
│   │   ├── types.dfy                 # Task, CPU, SchedEvent, RunQueue datatypes
│   │   ├── helpers.dfy               # BPF helper function contracts (pre/post conditions)
│   │   └── sched_ext_ops.dfy         # Abstract trait modeling sched_ext hook signatures
│   │
│   ├── properties/                   # What we want to prove — safety & liveness
│   │   ├── fairness.dfy              # Fairness invariant (vruntime bounded divergence)
│   │   ├── starvation_freedom.dfy    # No task starves (bounded wait)
│   │   ├── cpu_affinity.dfy          # CPU assignment respects affinity masks
│   │   └── ebpf_safety.dfy          # eBPF verifier constraints (bounded loops, stack depth)
│   │
│   └── refinements/                  # Stepwise refinement from abstract → concrete
│       ├── abstract_scheduler.dfy    # High-level: pick fairest task (nondeterministic)
│       ├── concrete_scheduler.dfy    # Low-level: red-black tree + vruntime arithmetic
│       └── refinement_proof.dfy      # Proof that concrete refines abstract
│
│
│ ════════════════════════════════════════════════════════════
│  AGENTS (Python)
│  Each agent is a module with: system prompt, tools, state machine.
│ ════════════════════════════════════════════════════════════
│
├── agents/
│   ├── __init__.py
│   ├── common/
│   │   ├── __init__.py
│   │   ├── llm.py                    # LLM client wrapper (Anthropic API)
│   │   ├── artifact_store.py         # Read/write shared artifacts (specs, code, reports)
│   │   ├── tool_runner.py            # Subprocess runner for external tools
│   │   └── message_types.py          # Typed inter-agent messages
│   │
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   ├── main.py                   # Entry point — parse requirements, run pipeline
│   │   ├── state_machine.py          # Pipeline state: spec→verify→impl→test→done
│   │   ├── router.py                 # Decides which agent handles a failure
│   │   └── prompts/
│   │       └── system.md             # Orchestrator system prompt
│   │
│   ├── spec/
│   │   ├── __init__.py
│   │   ├── agent.py                  # Spec agent: NL → Dafny
│   │   ├── domain_builder.py         # Generates types.dfy from API docs
│   │   ├── property_extractor.py     # Extracts formal properties from NL requirements
│   │   └── prompts/
│   │       ├── system.md             # "You are a formal methods expert..."
│   │       ├── examples/             # Few-shot examples of NL → Dafny
│   │       │   ├── fairness.md
│   │       │   └── bounded_wait.md
│   │       └── domain_context.md     # Injected sched_ext API summary
│   │
│   ├── verify/
│   │   ├── __init__.py
│   │   ├── agent.py                  # Verify agent: check spec consistency + eBPF constraints
│   │   ├── semantic_checker.py       # Cross-reference spec vs kernel semantics
│   │   ├── constraint_injector.py    # Inject eBPF verifier constraints into spec
│   │   └── prompts/
│   │       ├── system.md
│   │       └── ebpf_constraints.md   # Known eBPF limitations as prompt context
│   │
│   ├── impl/
│   │   ├── __init__.py
│   │   ├── agent.py                  # Impl agent: write Dafny impl + C bridge code
│   │   ├── lsp_client.py             # Talk to Dafny LSP for real-time diagnostics
│   │   ├── invariant_synthesizer.py  # Heuristics for generating loop invariants
│   │   ├── c_translator.py           # Dafny-verified algorithm → C/eBPF translation
│   │   └── prompts/
│   │       ├── system.md
│   │       └── dafny_idioms.md       # Common Dafny patterns the agent should know
│   │
│   └── test/
│       ├── __init__.py
│       ├── agent.py                  # Test agent: generate + run + diagnose tests
│       ├── trace_driver.py           # Drive eBPF module with Dafny traces
│       ├── fuzz_harness.py           # Generate fuzzing configs for sched events
│       ├── perf_analyzer.py          # Analyze perf/bpftool output
│       ├── diagnosis.py              # Classify failures: spec bug? impl bug? translation bug?
│       └── prompts/
│           ├── system.md
│           └── failure_triage.md     # How to diagnose different failure modes
│
│
│ ════════════════════════════════════════════════════════════
│  IMPLEMENTATION (C / eBPF)
│  The actual code that runs in the kernel.
│ ════════════════════════════════════════════════════════════
│
├── impl/
│   ├── bpf/
│   │   ├── src/
│   │   │   ├── sched_ext_fair.bpf.c     # Main eBPF scheduler source
│   │   │   ├── sched_ext_fair.h          # Shared types between BPF and userspace
│   │   │   └── invariants.h              # Runtime assert macros from Dafny invariants
│   │   ├── headers/
│   │   │   └── vmlinux.h                 # Auto-generated kernel type definitions
│   │   └── Makefile                      # clang -target bpf build rules
│   │
│   ├── bridge/
│   │   ├── mapping.md                    # CRITICAL: Dafny var → C struct mapping doc
│   │   ├── action_map.md                 # Dafny Action → C function mapping doc
│   │   └── atomicity_boundaries.md       # Which Dafny atomic steps map to which locks
│   │
│   └── generated/                        # Auto-generated from Dafny (gitignored mostly)
│       └── .gitkeep
│
│
│ ════════════════════════════════════════════════════════════
│  TESTS
│ ════════════════════════════════════════════════════════════
│
├── tests/
│   ├── conftest.py                       # Pytest fixtures: load BPF module, setup env
│   │
│   ├── traces/
│   │   ├── export_traces.py              # Script: TLC/Dafny → JSON trace files
│   │   ├── trace_runner.py               # Drive BPF module step-by-step from traces
│   │   └── fixtures/                     # Exported trace files (JSON)
│   │       ├── basic_enqueue_dequeue.json
│   │       ├── fairness_stress.json
│   │       └── starvation_scenario.json
│   │
│   ├── fuzz/
│   │   ├── sched_fuzz.py                 # Custom fuzzer: random sched event sequences
│   │   ├── syzkaller_config.json         # Syzkaller config for sched_ext syscalls
│   │   └── corpus/                       # Saved interesting fuzzer inputs
│   │       └── .gitkeep
│   │
│   ├── perf/
│   │   ├── benchmark.py                  # Scheduling latency + throughput benchmarks
│   │   ├── fairness_measure.py           # Measure actual vruntime divergence
│   │   └── baseline/                     # Baseline measurements for regression detection
│   │       └── cfs_baseline.json
│   │
│   └── fixtures/
│       ├── mock_tasks.json               # Predefined task sets for unit tests
│       └── cpu_topologies.json           # Different NUMA / CPU layouts
│
│
│ ════════════════════════════════════════════════════════════
│  KNOWLEDGE BASE
│  Domain knowledge that agents consult. Human-curated.
│ ════════════════════════════════════════════════════════════
│
├── knowledge/
│   ├── ebpf/
│   │   ├── sched_ext_ops_reference.md    # Every hook: signature, when called, constraints
│   │   ├── helper_functions.md           # BPF helpers: semantics, pre/post conditions
│   │   ├── verifier_constraints.md       # What the eBPF verifier checks
│   │   └── map_types.md                  # BPF map types and their guarantees
│   │
│   ├── dafny-patterns/
│   │   ├── loop_invariants.md            # Common invariant patterns
│   │   ├── ghost_state.md               # How to use ghost variables effectively
│   │   ├── refinement_patterns.md        # Refinement mapping recipes
│   │   └── common_errors.md             # Frequent Dafny verification failures + fixes
│   │
│   └── kernel/
│       ├── scheduler_internals.md        # CFS, runqueue, load balancing basics
│       ├── locking_model.md              # rq_lock, RCU, preemption
│       └── cpu_topology.md               # NUMA, LLC, scheduling domains
│
│
│ ════════════════════════════════════════════════════════════
│  TOOLS (wrappers around external toolchains)
│ ════════════════════════════════════════════════════════════
│
├── tools/
│   ├── lsp-bridge/
│   │   ├── client.py                     # Programmatic Dafny LSP client
│   │   └── diagnostic_parser.py          # Parse LSP diagnostics into structured errors
│   │
│   ├── dafny-runner/
│   │   ├── verify.py                     # Wrapper: dafny verify with timeout + retry
│   │   ├── build.py                      # Wrapper: dafny build --target:X
│   │   └── counterexample.py             # Extract counterexamples from failed verification
│   │
│   ├── bpf-compiler/
│   │   ├── compile.py                    # Wrapper: clang -target bpf with correct flags
│   │   ├── verify_bpf.py                # Wrapper: bpftool prog load (dry-run BPF verifier)
│   │   └── disasm.py                     # Disassemble .bpf.o for inspection
│   │
│   └── trace-exporter/
│       ├── dafny_to_json.py              # Convert Dafny execution traces to JSON
│       └── schema.py                     # Trace JSON schema definition
│
│
│ ════════════════════════════════════════════════════════════
│  BUILD / CI / CONFIG
│ ════════════════════════════════════════════════════════════
│
├── scripts/
│   ├── setup.sh                          # Install all dependencies
│   ├── gen_vmlinux.sh                    # Generate vmlinux.h from running kernel
│   └── export_proof_certificate.py       # Package proof artifacts for auditing
│
├── artifacts/                            # Pipeline outputs (gitignored except structure)
│   ├── specs/                            # Verified .dfy files (snapshot)
│   ├── proofs/                           # Verification logs + counterexamples
│   ├── bytecode/                         # Compiled .bpf.o files
│   └── reports/                          # Test reports, perf baselines, coverage
│
├── docs/
│   ├── project-structure.md              # This file
│   ├── requirements/
│   │   └── fair-scheduler.md             # Human-written requirements (input to pipeline)
│   ├── architecture.md                   # System design overview
│   ├── spec-impl-mapping.md              # How Dafny maps to C (living document)
│   └── runbook.md                        # How to operate the pipeline
│
├── Makefile                              # See below
├── pyproject.toml
├── dafny-project.toml
├── .env.example
└── .gitignore
```
