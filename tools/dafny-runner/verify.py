"""
Dafny verify wrapper with timeout, retry, and structured output.

Usage:
    python -m tools.dafny-runner.verify specs/domain/*.dfy
"""

from __future__ import annotations
import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class VerifyResult:
    success: bool
    files_verified: int
    errors: list[dict]
    warnings: list[dict]
    duration_seconds: float
    timed_out: bool = False


def run_verify(
    files: list[str],
    timeout: int = 120,
    cores: int = 4,
    retries: int = 1,
) -> VerifyResult:
    """Run dafny verify with structured result parsing."""
    import time

    existing = [f for f in files if Path(f).exists() and f.endswith(".dfy")]
    if not existing:
        return VerifyResult(success=True, files_verified=0, errors=[], warnings=[], duration_seconds=0)

    for attempt in range(retries + 1):
        t0 = time.time()
        try:
            result = subprocess.run(
                ["dafny", "verify",
                 "--cores", str(cores),
                 "--verification-time-limit", str(timeout)]
                + existing,
                capture_output=True, text=True,
                timeout=timeout * 2,  # overall timeout > per-method timeout
            )
            duration = time.time() - t0
            output = result.stdout + "\n" + result.stderr

            errors, warnings = _parse_diagnostics(output)

            return VerifyResult(
                success=result.returncode == 0,
                files_verified=len(existing),
                errors=errors,
                warnings=warnings,
                duration_seconds=duration,
            )

        except subprocess.TimeoutExpired:
            if attempt < retries:
                print(f"Attempt {attempt + 1} timed out, retrying...", file=sys.stderr)
                continue
            return VerifyResult(
                success=False,
                files_verified=len(existing),
                errors=[{"message": f"Verification timed out after {timeout * 2}s"}],
                warnings=[],
                duration_seconds=time.time() - t0,
                timed_out=True,
            )

    # Should not reach here
    return VerifyResult(success=False, files_verified=0, errors=[], warnings=[], duration_seconds=0)


def _parse_diagnostics(output: str) -> tuple[list[dict], list[dict]]:
    errors, warnings = [], []
    pattern = r'([^(]+)\((\d+),(\d+)\):\s*(Error|Warning):\s*(.+)'
    for match in re.finditer(pattern, output):
        entry = {
            "file": match.group(1).strip(),
            "line": int(match.group(2)),
            "col": int(match.group(3)),
            "message": match.group(5).strip(),
        }
        if match.group(4) == "Error":
            errors.append(entry)
        else:
            warnings.append(entry)
    return errors, warnings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--cores", type=int, default=4)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = run_verify(args.files, timeout=args.timeout, cores=args.cores)

    if args.json:
        print(json.dumps(asdict(result), indent=2))
    else:
        status = "PASS" if result.success else "FAIL"
        print(f"[{status}] Verified {result.files_verified} files in {result.duration_seconds:.1f}s")
        for e in result.errors:
            print(f"  ERROR: {e.get('file', '?')}:{e.get('line', '?')}: {e['message']}")
        for w in result.warnings:
            print(f"  WARN:  {w.get('file', '?')}:{w.get('line', '?')}: {w['message']}")

    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
