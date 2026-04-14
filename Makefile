# ═══════════════════════════════════════════════════════════
# verified-sched-ext pipeline
# ═══════════════════════════════════════════════════════════

DAFNY        := dafny
CLANG        := clang-17
BPFTOOL      := bpftool
PYTHON       := python3
SPEC_DIR     := specs
IMPL_DIR     := impl/bpf
ARTIFACT_DIR := artifacts

.PHONY: all setup spec verify build test report clean

all: verify build test report

# ── Setup ──────────────────────────────────────────────────
setup:
	@echo "==> Installing dependencies..."
	bash scripts/setup.sh
	$(PYTHON) -m pip install -e ".[dev]"
	@echo "==> Generating vmlinux.h..."
	bash scripts/gen_vmlinux.sh

# ── Stage 1: Specification ─────────────────────────────────
spec:
	@echo "==> Running Spec Agent..."
	$(PYTHON) -m agents.spec.agent \
		--requirements docs/requirements/fair-scheduler.md \
		--output $(SPEC_DIR)/ \
		--knowledge knowledge/

# ── Stage 2: Verification ──────────────────────────────────
verify: verify-spec verify-impl

verify-spec:
	@echo "==> Verifying Dafny specifications..."
	$(DAFNY) verify \
		--cores 4 \
		--verification-time-limit 120 \
		$(SPEC_DIR)/domain/types.dfy \
		$(SPEC_DIR)/domain/helpers.dfy \
		$(SPEC_DIR)/domain/sched_ext_ops.dfy \
		$(SPEC_DIR)/properties/fairness.dfy \
		$(SPEC_DIR)/properties/starvation_freedom.dfy \
		$(SPEC_DIR)/properties/ebpf_safety.dfy

verify-impl:
	@echo "==> Verifying implementation against spec..."
	$(DAFNY) verify \
		--cores 4 \
		--verification-time-limit 300 \
		$(SPEC_DIR)/refinements/concrete_scheduler.dfy \
		$(SPEC_DIR)/refinements/refinement_proof.dfy

# ── Stage 3: Build eBPF ────────────────────────────────────
build: build-bpf verify-bpf

build-bpf:
	@echo "==> Compiling eBPF module..."
	$(MAKE) -C $(IMPL_DIR)

verify-bpf:
	@echo "==> Running BPF verifier (dry-run load)..."
	$(PYTHON) -m tools.bpf-compiler.verify_bpf \
		$(IMPL_DIR)/sched_ext_fair.bpf.o

# ── Stage 4: Test ──────────────────────────────────────────
test: test-traces test-fuzz test-perf

test-traces:
	@echo "==> Exporting Dafny traces..."
	$(PYTHON) -m tests.traces.export_traces \
		--spec $(SPEC_DIR)/refinements/concrete_scheduler.dfy \
		--output tests/traces/fixtures/
	@echo "==> Running trace-driven tests..."
	$(PYTHON) -m pytest tests/traces/ -v

test-fuzz:
	@echo "==> Running fuzz tests (60s budget)..."
	$(PYTHON) -m tests.fuzz.sched_fuzz \
		--module $(IMPL_DIR)/sched_ext_fair.bpf.o \
		--duration 60 \
		--invariants $(SPEC_DIR)/properties/

test-perf:
	@echo "==> Running performance benchmarks..."
	$(PYTHON) -m tests.perf.benchmark \
		--module $(IMPL_DIR)/sched_ext_fair.bpf.o \
		--baseline tests/perf/baseline/cfs_baseline.json

# ── Stage 5: Report ────────────────────────────────────────
report:
	@echo "==> Generating verification report..."
	$(PYTHON) scripts/export_proof_certificate.py \
		--specs $(SPEC_DIR)/ \
		--proofs $(ARTIFACT_DIR)/proofs/ \
		--tests $(ARTIFACT_DIR)/reports/ \
		--output $(ARTIFACT_DIR)/reports/verification-report.md

# ── Full pipeline (agent-driven) ───────────────────────────
pipeline:
	$(PYTHON) -m agents.orchestrator.main \
		--requirements docs/requirements/fair-scheduler.md \
		--max-iterations 10

# ── Cleanup ────────────────────────────────────────────────
clean:
	rm -rf $(ARTIFACT_DIR)/bytecode/*
	rm -rf $(ARTIFACT_DIR)/reports/*
	rm -rf impl/generated/*
	$(MAKE) -C $(IMPL_DIR) clean
