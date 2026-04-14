"""
Shared pytest fixtures for the verified-sched-ext test suite.
"""

import json
import pytest
from pathlib import Path


@pytest.fixture
def mock_tasks():
    """Load predefined task sets for unit tests."""
    path = Path("tests/fixtures/mock_tasks.json")
    if path.exists():
        return json.loads(path.read_text())
    return [
        {"pid": 1, "vruntime": 0, "weight": 1024, "state": "Runnable"},
        {"pid": 2, "vruntime": 100, "weight": 1024, "state": "Runnable"},
        {"pid": 3, "vruntime": 50, "weight": 512, "state": "Runnable"},
    ]


@pytest.fixture
def cpu_topology():
    """Load CPU topology for multi-CPU tests."""
    path = Path("tests/fixtures/cpu_topologies.json")
    if path.exists():
        return json.loads(path.read_text())
    return {
        "num_cpus": 4,
        "numa_nodes": [[0, 1], [2, 3]],
        "llc_groups": [[0, 1], [2, 3]],
    }


@pytest.fixture
def trace_dir():
    """Path to trace fixture files."""
    d = Path("tests/traces/fixtures")
    d.mkdir(parents=True, exist_ok=True)
    return d
