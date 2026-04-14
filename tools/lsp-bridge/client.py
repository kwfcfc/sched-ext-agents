"""
Programmatic client for the Dafny Language Server Protocol.

The Impl Agent uses this to get real-time verification feedback as it
writes code — just like a human developer using an IDE, but in a loop.

Usage:
    async with DafnyLSPClient("/path/to/dafny") as lsp:
        diagnostics = await lsp.check_file("specs/refinements/concrete_scheduler.dfy")
        for d in diagnostics:
            print(f"{d.severity}: {d.message} at line {d.line}")
"""

from __future__ import annotations
import asyncio
import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import AsyncIterator


class Severity(Enum):
    ERROR = 1
    WARNING = 2
    INFO = 3
    HINT = 4


@dataclass
class Diagnostic:
    file: str
    line: int
    col: int
    end_line: int
    end_col: int
    severity: Severity
    message: str
    source: str = "dafny"

    @property
    def is_verification_error(self) -> bool:
        """True if this is a failed proof, not a syntax error."""
        return (
            self.severity == Severity.ERROR
            and any(kw in self.message.lower() for kw in [
                "postcondition", "invariant", "decreases",
                "assertion", "precondition", "ensures", "requires"
            ])
        )

    @property
    def is_timeout(self) -> bool:
        return "timed out" in self.message.lower()


class DafnyLSPClient:
    """Async client wrapping the Dafny language server via stdio."""

    def __init__(self, dafny_path: str = "dafny"):
        self.dafny_path = dafny_path
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}

    async def __aenter__(self):
        self._process = await asyncio.create_subprocess_exec(
            self.dafny_path, "server",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        # Send initialize request
        await self._send("initialize", {
            "processId": os.getpid(),
            "capabilities": {},
            "rootUri": f"file://{Path.cwd()}",
        })
        await self._send("initialized", {})
        return self

    async def __aexit__(self, *exc):
        if self._process:
            await self._send("shutdown", {})
            self._process.terminate()
            await self._process.wait()

    async def check_file(self, filepath: str) -> list[Diagnostic]:
        """Open a file, wait for verification, return diagnostics."""
        uri = f"file://{Path(filepath).resolve()}"
        content = Path(filepath).read_text()

        # Open the document
        await self._notify("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": "dafny",
                "version": 1,
                "text": content,
            }
        })

        # Collect diagnostics until verification completes
        diagnostics = []
        async for batch in self._collect_diagnostics(uri, timeout=300):
            diagnostics.extend(batch)

        return diagnostics

    async def update_file(self, filepath: str, new_content: str) -> list[Diagnostic]:
        """Update file content and re-verify."""
        uri = f"file://{Path(filepath).resolve()}"

        # Write to disk (Dafny LSP reads from disk)
        Path(filepath).write_text(new_content)

        await self._notify("textDocument/didChange", {
            "textDocument": {"uri": uri, "version": 2},
            "contentChanges": [{"text": new_content}],
        })

        diagnostics = []
        async for batch in self._collect_diagnostics(uri, timeout=300):
            diagnostics.extend(batch)
        return diagnostics

    # ── Internal protocol methods ──────────────────────────

    async def _send(self, method: str, params: dict) -> dict:
        self._request_id += 1
        msg = {"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": params}
        return await self._write_message(msg)

    async def _notify(self, method: str, params: dict):
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        await self._write_message(msg, expect_response=False)

    async def _write_message(self, msg: dict, expect_response: bool = True) -> dict | None:
        body = json.dumps(msg)
        header = f"Content-Length: {len(body)}\r\n\r\n"
        self._process.stdin.write((header + body).encode())
        await self._process.stdin.drain()
        if expect_response:
            return await self._read_message()
        return None

    async def _read_message(self) -> dict:
        header = await self._process.stdout.readline()
        content_length = int(header.decode().split(":")[1].strip())
        await self._process.stdout.readline()  # empty line
        body = await self._process.stdout.readexactly(content_length)
        return json.loads(body)

    async def _collect_diagnostics(
        self, uri: str, timeout: float = 300
    ) -> AsyncIterator[list[Diagnostic]]:
        """Yield batches of diagnostics until verification ends."""
        deadline = asyncio.get_event_loop().time() + timeout

        while asyncio.get_event_loop().time() < deadline:
            try:
                msg = await asyncio.wait_for(self._read_message(), timeout=10)
            except asyncio.TimeoutError:
                break

            if msg.get("method") == "textDocument/publishDiagnostics":
                if msg["params"]["uri"] == uri:
                    batch = [
                        Diagnostic(
                            file=uri,
                            line=d["range"]["start"]["line"],
                            col=d["range"]["start"]["character"],
                            end_line=d["range"]["end"]["line"],
                            end_col=d["range"]["end"]["character"],
                            severity=Severity(d.get("severity", 1)),
                            message=d["message"],
                        )
                        for d in msg["params"]["diagnostics"]
                    ]
                    yield batch

                    # If no errors remain, verification succeeded
                    if not any(d.severity == Severity.ERROR for d in batch):
                        return
