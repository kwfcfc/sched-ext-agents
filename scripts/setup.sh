#!/bin/bash
# ═══════════════════════════════════════════════════════════
# Setup script for verified-sched-ext development environment
# ═══════════════════════════════════════════════════════════
set -euo pipefail

echo "==> Checking system requirements..."

# ── Check OS ───────────────────────────────────────────────
if [[ ! -f /etc/os-release ]] || ! grep -q "Ubuntu\|Debian" /etc/os-release; then
    echo "WARNING: This script is designed for Ubuntu/Debian. YMMV on other distros."
fi

# ── Dafny ──────────────────────────────────────────────────
DAFNY_VERSION="4.4.0"
if ! command -v dafny &>/dev/null; then
    echo "==> Installing Dafny ${DAFNY_VERSION}..."
    DAFNY_URL="https://github.com/dafny-lang/dafny/releases/download/v${DAFNY_VERSION}/dafny-${DAFNY_VERSION}-x64-ubuntu-20.04.zip"
    wget -q "$DAFNY_URL" -O /tmp/dafny.zip
    sudo unzip -q -o /tmp/dafny.zip -d /opt/dafny
    sudo ln -sf /opt/dafny/dafny/dafny /usr/local/bin/dafny
    rm /tmp/dafny.zip
    echo "    Dafny installed: $(dafny --version)"
else
    echo "    Dafny found: $(dafny --version)"
fi

# ── LLVM / Clang (for eBPF compilation) ───────────────────
CLANG_VERSION="17"
if ! command -v clang-${CLANG_VERSION} &>/dev/null; then
    echo "==> Installing clang-${CLANG_VERSION}..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq clang-${CLANG_VERSION} llvm-${CLANG_VERSION} lld-${CLANG_VERSION}
else
    echo "    clang-${CLANG_VERSION} found"
fi

# ── libbpf + bpftool ──────────────────────────────────────
if ! command -v bpftool &>/dev/null; then
    echo "==> Installing bpftool and libbpf-dev..."
    sudo apt-get install -y -qq bpftool libbpf-dev linux-headers-$(uname -r)
else
    echo "    bpftool found"
fi

# ── Python ─────────────────────────────────────────────────
PYTHON_MIN="3.11"
if ! python3 -c "import sys; assert sys.version_info >= (3, 11)" 2>/dev/null; then
    echo "ERROR: Python >= ${PYTHON_MIN} is required."
    echo "       Install with: sudo apt install python3.11"
    exit 1
else
    echo "    Python found: $(python3 --version)"
fi

# ── Performance tools ─────────────────────────────────────
echo "==> Installing perf and trace-cmd..."
sudo apt-get install -y -qq linux-tools-common linux-tools-$(uname -r) trace-cmd || \
    echo "    WARNING: Could not install perf tools (may need kernel-matched package)"

# ── Python dependencies ───────────────────────────────────
echo "==> Installing Python dependencies..."
python3 -m pip install -e ".[dev]" --quiet

# ── Create output directories ─────────────────────────────
echo "==> Creating directory structure..."
mkdir -p artifacts/{specs,proofs,bytecode,reports}
mkdir -p impl/generated
mkdir -p tests/fuzz/corpus

# ── .env file ─────────────────────────────────────────────
if [[ ! -f .env ]]; then
    echo "==> Creating .env from .env.example..."
    cp .env.example .env
    echo "    NOTE: Edit .env and add your ANTHROPIC_API_KEY"
fi

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Setup complete!"
echo ""
echo "  Next steps:"
echo "    1. Edit .env with your ANTHROPIC_API_KEY"
echo "    2. Run: bash scripts/gen_vmlinux.sh"
echo "    3. Run: make pipeline"
echo "═══════════════════════════════════════════════════════"
