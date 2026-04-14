"""
BPF compilation and verification wrappers.

compile.py — wraps clang -target bpf
verify_bpf.py — wraps bpftool prog load (dry-run)
"""

from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path


def compile_bpf(
    source: str,
    output: str | None = None,
    debug: bool = False,
    clang: str = "clang-17",
) -> tuple[bool, str]:
    """Compile a .bpf.c file to .bpf.o using clang."""
    src = Path(source)
    if not src.exists():
        return False, f"Source not found: {source}"

    out = output or str(src.with_suffix(".bpf.o"))
    flags = [
        "-g", "-O2", "-target", "bpf",
        "-I", str(src.parent.parent / "headers"),
        "-I", str(src.parent),
        "-Wall", "-Werror",
    ]
    if debug:
        flags.append("-DDEBUG_INVARIANTS")

    cmd = [clang] + flags + ["-c", str(src), "-o", out]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    output_text = result.stdout + "\n" + result.stderr
    return result.returncode == 0, output_text.strip()


def verify_bpf_program(obj_path: str) -> tuple[bool, str]:
    """Dry-run load a BPF object to check kernel verifier acceptance."""
    pin_path = "/sys/fs/bpf/_verify_test"

    try:
        result = subprocess.run(
            ["sudo", "bpftool", "prog", "load", obj_path, pin_path],
            capture_output=True, text=True, timeout=30,
        )
        # Clean up pin
        subprocess.run(["sudo", "rm", "-f", pin_path], capture_output=True)

        output = result.stdout + "\n" + result.stderr
        return result.returncode == 0, output.strip()

    except FileNotFoundError:
        return False, "bpftool not found"
    except subprocess.TimeoutExpired:
        subprocess.run(["sudo", "rm", "-f", pin_path], capture_output=True)
        return False, "BPF verification timed out"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("bpf_object", help="Path to .bpf.o file")
    args = parser.parse_args()

    ok, msg = verify_bpf_program(args.bpf_object)
    print(f"{'PASS' if ok else 'FAIL'}: {msg}")
    sys.exit(0 if ok else 1)
