#!/bin/bash
# Generate vmlinux.h from the running kernel's BTF information.
# This header provides type definitions for all kernel structures
# that BPF programs can access.
set -euo pipefail

OUTPUT="impl/bpf/headers/vmlinux.h"
mkdir -p "$(dirname "$OUTPUT")"

if command -v bpftool &>/dev/null; then
    echo "Generating vmlinux.h from /sys/kernel/btf/vmlinux..."
    bpftool btf dump file /sys/kernel/btf/vmlinux format c > "$OUTPUT"
    echo "Done: $OUTPUT ($(wc -l < "$OUTPUT") lines)"
else
    echo "ERROR: bpftool not found. Install with: sudo apt install bpftool"
    exit 1
fi
