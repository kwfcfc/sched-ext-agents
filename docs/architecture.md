# Architecture

## Design Principles

1. **Formal spec is ground truth** — the Dafny specs in `specs/` are the single source of truth for scheduler behavior. Everything else (C code, tests, agents) derives from or validates against them.

2. **Agents are stateless** — each agent receives its full context (requirements, specs, failure messages) on every invocation. No hidden state between runs. The `ArtifactStore` provides shared persistence.

3. **Tools are the oracle** — Dafny verify, BPF verifier, and test harnesses are the final arbiters of correctness. If an agent's output fails verification, it's wrong regardless of how plausible it looks.

4. **Fail fast, route precisely** — failures are classified by kind and routed to the agent best positioned to fix them. A spec inconsistency goes to the Spec Agent, not the Impl Agent.

5. **Everything versioned** — every artifact in `artifacts/` has a version number, SHA-256, and creation timestamp in the manifest. Git provides history; the manifest provides structure.

## Pipeline Flow

```
Human Requirements (docs/requirements/*.md)
  │
  ▼
┌─────────────────────────────────────────┐
│         Orchestrator Agent              │
│  • Parses requirements                  │
│  • Manages pipeline state machine       │
│  • Routes failures to correct agent     │
│  • Enforces iteration budget            │
└──┬──────────┬──────────┬──────────┬─────┘
   │          │          │          │
   ▼          ▼          ▼          ▼
 Spec       Verify     Impl      Test
 Agent      Agent      Agent     Agent
   │          │          │          │
   │ writes   │ reads    │ reads   │ reads
   │ specs    │ specs    │ specs   │ everything
   │          │ checks   │ writes  │ writes
   │          │ semantics│ code    │ reports
   ▼          ▼          ▼          ▼
┌─────────────────────────────────────────┐
│         Artifact Store                  │
│  specs/ proofs/ bytecode/ reports/      │
│  manifest.json (typed, versioned)       │
└─────────────────────────────────────────┘
   │          │          │          │
   ▼          ▼          ▼          ▼
 Dafny     Dafny      clang     Linux
 verify    LSP        -target   sched
                      bpf       tools
```

## Agent Communication

Agents do NOT communicate directly. All data flows through the Artifact Store:

1. Spec Agent writes `.dfy` files → Artifact Store
2. Verify Agent reads `.dfy` files from Store → runs Dafny verify → writes proof logs
3. Impl Agent reads specs → writes `.dfy` impl + `.bpf.c` → Store
4. Test Agent reads everything → writes test reports → Store
5. Orchestrator reads StageResults → decides next step

## Failure Routing

```
Failure Kind              → Routed To        → Escalation (after 3 failures)
─────────────────────────────────────────────────────────────────────────
SPEC_INCONSISTENT         → Spec Agent       → (terminal — human review)
SPEC_INCOMPLETE           → Spec Agent       → (terminal — human review)
IMPL_UNVERIFIED           → Impl Agent       → Spec Review
INVARIANT_TOO_WEAK        → Impl Agent       → Spec Drafting
BPF_COMPILE_ERROR         → Impl Agent       → Impl Agent (retry)
BPF_VERIFIER_REJECT       → Impl Agent       → Impl Agent (retry)
TRACE_MISMATCH            → Impl Agent       → Spec Review
FUZZ_CRASH                → Spec Review      → Spec Drafting
PERF_REGRESSION           → Impl Agent       → Impl Agent (retry)
TRANSLATION_BUG           → Impl Agent       → Spec Review
```

## Security Boundaries

- BPF programs run in kernel context with limited capabilities
- The BPF verifier is the final security gate — it runs independently of our toolchain
- Agent-generated code should never be loaded into a production kernel without human review
- The proof certificate (`scripts/export_proof_certificate.py`) documents all `assume` statements that represent unproven obligations
