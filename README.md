# verified-sched-ext

A formally verified Linux sched_ext scheduler module, built with a multi-agent pipeline that goes from human requirements to deployable eBPF bytecode with proof artifacts.

## Architecture

```
Human Requirements
       │
       ▼
┌─────────────────────────────────────────────┐
│            Orchestrator Agent                │
│  (task routing, state machine, feedback)     │
└──┬──────────┬──────────┬──────────┬─────────┘
   ▼          ▼          ▼          ▼
 Spec      Verify      Impl      Test
 Agent     Agent       Agent     Agent
   │          │          │          │
   ▼          ▼          ▼          ▼
 Dafny     Dafny      LSP +     Linux
 specs     verify     clang     sched tools
```

## Quick Start

```bash
# Install dependencies
make setup

# Run the full pipeline from a requirements file
python -m agents.orchestrator.main --requirements docs/requirements/fair-scheduler.md

# Or run individual stages
make spec          # Generate Dafny specification
make verify        # Verify specification + implementation
make build         # Compile to eBPF bytecode
make test          # Run all tests
make report        # Generate verification report
```

## Project Structure

See `docs/project-structure.md` for a detailed explanation of every directory and file.

## Prerequisites

- Dafny >= 4.4 (with Z3 backend)
- LLVM/clang >= 17 (with BPF target)
- Linux kernel >= 6.12 (with sched_ext support)
- Python >= 3.11
- bpftool, perf, trace-cmd
