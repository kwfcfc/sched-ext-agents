FROM ubuntu:25.04

ENV DEBIAN_FRONTEND=noninteractive

# ── System dependencies ────────────────────────────────────
# Per https://github.com/sched-ext/scx/blob/main/INSTALL.md
# sched_ext requires Ubuntu 25.04+ and kernel 6.12+
RUN apt-get update && apt-get install -y \
    curl wget unzip \
    dotnet-sdk-8.0 \
    build-essential cmake \
    clang llvm lld \
    pkg-config libelf-dev \
    libbpf-dev libseccomp-dev \
    pahole \
    linux-headers-generic \
    python3 python3-pip python3-venv \
    git make \
    z3 \
    && rm -rf /var/lib/apt/lists/*

# ── Install Dafny via dotnet tool (works on arm64) ─────────
RUN dotnet tool install --global dafny --version 4.11.0
ENV PATH="/root/.dotnet/tools:${PATH}"

WORKDIR /workspace

CMD ["bash"]
