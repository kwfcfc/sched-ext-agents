# Runbook

## Running the Full Pipeline

```bash
# 1. Setup environment (one-time)
make setup

# 2. Edit .env with your Anthropic API key
vim .env

# 3. Generate vmlinux.h from your kernel
bash scripts/gen_vmlinux.sh

# 4. Run the full agent-driven pipeline
make pipeline

# Or run stages manually:
make spec          # Spec Agent generates Dafny specs
make verify        # Verify Agent checks specs
make build         # Compile to eBPF bytecode
make test          # Run all test suites
make report        # Generate verification certificate
```

## Resuming a Failed Pipeline

The pipeline saves state after every stage to `artifacts/pipeline_state.json`.

```bash
python -m agents.orchestrator.main --resume
```

## Debugging a Verification Failure

1. Check the proof log: `cat artifacts/proofs/spec_verify.log`
2. Open the failing `.dfy` file in VS Code (Dafny extension gives inline errors)
3. Look for `assume` statements — these are unproven obligations
4. Add intermediate `assert` statements to narrow down where the proof breaks

## Debugging a BPF Verifier Rejection

```bash
# Get detailed verifier output
sudo bpftool prog load impl/bpf/src/sched_ext_fair.bpf.o /sys/fs/bpf/test 2>&1 | head -200

# Common issues:
# - "back-edge" = unbounded loop → add a loop bound
# - "invalid mem access" = null pointer → add NULL check after map lookup
# - "stack depth exceeded" = too many local vars → reduce stack usage
```

## Running Individual Tests

```bash
# Trace-driven tests only
python -m pytest tests/traces/ -v

# Fuzz testing (custom duration)
python -m tests.fuzz.sched_fuzz --duration 120 --seed 42

# Performance benchmarks
python -m tests.perf.benchmark --baseline tests/perf/baseline/cfs_baseline.json
```

## Exporting Proof Certificate

```bash
python scripts/export_proof_certificate.py \
    --specs specs/ \
    --proofs artifacts/proofs/ \
    --tests artifacts/reports/ \
    --output artifacts/reports/verification-report.md
```

This generates a human-readable report and a machine-readable `certificate-manifest.json`.
