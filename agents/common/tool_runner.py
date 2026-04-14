"""
Subprocess runner for external tools (Dafny, clang, bpftool, perf).

Provides structured output, timeout handling, and retry logic.
"""

from __future__ import annotations
import logging
import subprocess
import time
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class ToolResult:
    command: str
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False

    @property
    def success(self) -> bool:
        return self.returncode == 0 and not self.timed_out


def run_tool(
    cmd: list[str],
    timeout: int = 120,
    retries: int = 0,
    cwd: str | None = None,
) -> ToolResult:
    """Run an external tool with timeout and optional retry."""
    cmd_str = " ".join(cmd)

    for attempt in range(retries + 1):
        t0 = time.time()
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=timeout, cwd=cwd,
            )
            return ToolResult(
                command=cmd_str,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_seconds=time.time() - t0,
            )
        except subprocess.TimeoutExpired:
            duration = time.time() - t0
            if attempt < retries:
                log.warning("Tool timed out (attempt %d/%d): %s",
                            attempt + 1, retries + 1, cmd_str)
                continue
            return ToolResult(
                command=cmd_str, returncode=-1,
                stdout="", stderr=f"Timed out after {timeout}s",
                duration_seconds=duration, timed_out=True,
            )
        except FileNotFoundError:
            return ToolResult(
                command=cmd_str, returncode=-1,
                stdout="", stderr=f"Tool not found: {cmd[0]}",
                duration_seconds=0,
            )

    # Unreachable
    return ToolResult(command=cmd_str, returncode=-1, stdout="", stderr="Unknown error", duration_seconds=0)
