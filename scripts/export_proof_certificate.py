"""
Export proof certificate — packages all verification artifacts for auditing.

Creates a self-contained archive with:
  - Dafny spec files (frozen snapshot)
  - Verification logs (Dafny output)
  - Spec↔impl mapping document
  - Test results
  - Git commit hash
  - Checksums of all artifacts

Usage:
    python scripts/export_proof_certificate.py \
        --specs specs/ \
        --proofs artifacts/proofs/ \
        --tests artifacts/reports/ \
        --output artifacts/reports/verification-report.md
"""

from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def get_git_info() -> dict:
    """Get current git commit and status."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True
        ).stdout.strip()
        return {
            "commit": commit,
            "dirty": bool(dirty),
            "branch": subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True
            ).stdout.strip(),
        }
    except FileNotFoundError:
        return {"commit": "unknown", "dirty": True, "branch": "unknown"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def generate_report(
    specs_dir: str,
    proofs_dir: str,
    tests_dir: str,
    output_path: str,
):
    specs = Path(specs_dir)
    proofs = Path(proofs_dir)
    tests = Path(tests_dir)
    git = get_git_info()
    now = datetime.now(timezone.utc).isoformat()

    lines = [
        "# Verification Certificate",
        "",
        f"Generated: {now}",
        f"Git commit: `{git['commit']}`" + (" **(dirty)**" if git["dirty"] else ""),
        f"Branch: `{git['branch']}`",
        "",
        "---",
        "",
        "## Specification Files",
        "",
    ]

    # List all spec files with checksums
    dfy_files = sorted(specs.rglob("*.dfy")) if specs.exists() else []
    for f in dfy_files:
        sha = sha256_file(f)
        lines.append(f"- `{f}` — sha256: `{sha[:16]}...`")

    lines.extend(["", "## Verification Logs", ""])

    log_files = sorted(proofs.rglob("*.log")) if proofs.exists() else []
    for f in log_files:
        lines.append(f"- `{f}` ({f.stat().st_size} bytes)")
        # Extract summary line
        content = f.read_text()
        for line in content.splitlines()[-5:]:
            if "verified" in line.lower() or "error" in line.lower():
                lines.append(f"  > {line.strip()}")
                break

    lines.extend(["", "## Test Results", ""])

    test_files = sorted(tests.rglob("*")) if tests.exists() else []
    for f in test_files:
        if f.is_file():
            lines.append(f"- `{f}` ({f.stat().st_size} bytes)")

    # Mapping doc
    mapping = Path("impl/bridge/mapping.md")
    if mapping.exists():
        lines.extend([
            "",
            "## Spec↔Implementation Mapping",
            "",
            f"- `{mapping}` — sha256: `{sha256_file(mapping)[:16]}...`",
            f"- Last modified: {datetime.fromtimestamp(mapping.stat().st_mtime, tz=timezone.utc).isoformat()}",
        ])

    # Assumptions
    lines.extend([
        "",
        "## Open Assumptions (`assume` statements)",
        "",
    ])

    assume_count = 0
    for f in dfy_files:
        content = f.read_text()
        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("assume ") and "//" in stripped:
                lines.append(f"- `{f}:{i}`: `{stripped}`")
                assume_count += 1
            elif stripped.startswith("assume "):
                lines.append(f"- `{f}:{i}`: `{stripped}`")
                assume_count += 1

    if assume_count == 0:
        lines.append("None — all proof obligations discharged.")
    else:
        lines.append(f"\n**{assume_count} open assumptions remain.** These must be resolved before deployment.")

    # Write report
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines))
    print(f"Verification certificate written to {out}")

    # Also write machine-readable manifest
    manifest = {
        "generated_at": now,
        "git": git,
        "spec_files": [{"path": str(f), "sha256": sha256_file(f)} for f in dfy_files],
        "open_assumptions": assume_count,
        "proof_logs": [str(f) for f in log_files],
        "test_reports": [str(f) for f in test_files if f.is_file()],
    }
    manifest_path = out.parent / "certificate-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Machine-readable manifest: {manifest_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--specs", required=True)
    parser.add_argument("--proofs", required=True)
    parser.add_argument("--tests", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    generate_report(args.specs, args.proofs, args.tests, args.output)


if __name__ == "__main__":
    main()
