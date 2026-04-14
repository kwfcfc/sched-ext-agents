"""
Shared artifact store for inter-agent communication.

All agents read and write structured artifacts through this interface.
Artifacts are files on disk under artifacts/ with metadata tracking.
Git provides versioning; this module provides typed access.
"""

from __future__ import annotations
import json
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class ArtifactKind(Enum):
    DAFNY_SPEC      = "dafny_spec"        # .dfy file (spec)
    DAFNY_IMPL      = "dafny_impl"        # .dfy file (implementation)
    DAFNY_PROOF_LOG = "dafny_proof_log"   # Verification output log
    C_SOURCE        = "c_source"          # .c / .h file
    BPF_OBJECT      = "bpf_object"        # .bpf.o compiled bytecode
    TRACE_JSON      = "trace_json"        # Exported state trace
    TEST_REPORT     = "test_report"       # Test results
    PERF_REPORT     = "perf_report"       # Performance measurements
    MAPPING_DOC     = "mapping_doc"       # Spec↔impl mapping
    COUNTEREXAMPLE  = "counterexample"    # Failed verification witness


@dataclass
class ArtifactMetadata:
    kind: ArtifactKind
    path: str                              # Relative to repo root
    created_by: str                        # Agent name
    created_at: str = ""                   # ISO timestamp
    sha256: str = ""                       # Content hash
    depends_on: list[str] = field(default_factory=list)  # Paths of input artifacts
    tags: dict[str, str] = field(default_factory=dict)
    version: int = 1

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


class ArtifactStore:
    """Typed read/write access to the shared artifact directory."""

    MANIFEST_PATH = Path("artifacts/manifest.json")

    def __init__(self, root: Path = Path(".")):
        self.root = root
        self._manifest: dict[str, ArtifactMetadata] = {}
        self._load_manifest()

    # ── Write ──────────────────────────────────────────────

    def store(
        self,
        kind: ArtifactKind,
        path: str,
        content: str | bytes,
        created_by: str,
        depends_on: list[str] | None = None,
        tags: dict[str, str] | None = None,
    ) -> ArtifactMetadata:
        """Write an artifact to disk and register it in the manifest."""
        full_path = self.root / path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(content, str):
            full_path.write_text(content)
            sha = hashlib.sha256(content.encode()).hexdigest()
        else:
            full_path.write_bytes(content)
            sha = hashlib.sha256(content).hexdigest()

        # Bump version if artifact already exists
        version = 1
        if path in self._manifest:
            version = self._manifest[path].version + 1

        meta = ArtifactMetadata(
            kind=kind,
            path=path,
            created_by=created_by,
            sha256=sha,
            depends_on=depends_on or [],
            tags=tags or {},
            version=version,
        )
        self._manifest[path] = meta
        self._save_manifest()
        return meta

    # ── Read ───────────────────────────────────────────────

    def load(self, path: str) -> tuple[str, ArtifactMetadata]:
        """Read an artifact's content and metadata."""
        if path not in self._manifest:
            raise FileNotFoundError(f"Artifact not in manifest: {path}")
        content = (self.root / path).read_text()
        return content, self._manifest[path]

    def list_by_kind(self, kind: ArtifactKind) -> list[ArtifactMetadata]:
        return [m for m in self._manifest.values() if m.kind == kind]

    def latest_of_kind(self, kind: ArtifactKind) -> ArtifactMetadata | None:
        candidates = self.list_by_kind(kind)
        if not candidates:
            return None
        return max(candidates, key=lambda m: m.created_at)

    def get_dependency_chain(self, path: str) -> list[str]:
        """Walk the dependency graph for a given artifact."""
        visited = []
        stack = [path]
        while stack:
            p = stack.pop()
            if p in visited:
                continue
            visited.append(p)
            if p in self._manifest:
                stack.extend(self._manifest[p].depends_on)
        return visited

    # ── Manifest persistence ───────────────────────────────

    def _load_manifest(self):
        manifest_path = self.root / self.MANIFEST_PATH
        if manifest_path.exists():
            data = json.loads(manifest_path.read_text())
            for path, entry in data.items():
                entry["kind"] = ArtifactKind(entry["kind"])
                self._manifest[path] = ArtifactMetadata(**entry)

    def _save_manifest(self):
        manifest_path = self.root / self.MANIFEST_PATH
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        for path, meta in self._manifest.items():
            d = asdict(meta)
            d["kind"] = meta.kind.value
            data[path] = d
        manifest_path.write_text(json.dumps(data, indent=2))
