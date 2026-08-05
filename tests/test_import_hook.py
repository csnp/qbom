"""
Tests for the import hook that makes import order irrelevant.

QBOM's premise is "add one import and your experiment is captured". That only
holds if a framework imported *after* qbom still gets its adapter installed,
which is the job of QBOMImportFinder. Before 2026-08, the finder implemented
find_module/load_module, an API Python 3.12 removed, so it sat in sys.meta_path
and was never consulted. The documented import order captured nothing and
exited 0.

The tests below drive real imports through sys.meta_path rather than asserting
anything about the finder's shape, so they fail on that code.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from qbom.core.session import QBOMImportFinder, Session

PROBE = "qbom_probe_framework"

QISKIT_AVAILABLE = importlib.util.find_spec("qiskit") is not None and importlib.util.find_spec("qiskit_aer") is not None


@pytest.fixture
def probe_package(tmp_path, monkeypatch):
    """
    A throwaway package that stands in for a quantum framework.

    It has a submodule imported from its own __init__, which is what makes the
    "fires once, after __init__ completes" assertions below meaningful: the
    real AerBackend hook depends on both properties.
    """
    package = tmp_path / PROBE
    package.mkdir()
    (package / "__init__.py").write_text("from qbom_probe_framework import backends\n\nMARKER = 'executed'\n")
    (package / "backends.py").write_text("class ProbeBackend:\n    pass\n")

    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()

    yield PROBE

    for name in [n for n in sys.modules if n == PROBE or n.startswith(f"{PROBE}.")]:
        del sys.modules[name]
    importlib.invalidate_caches()


@pytest.fixture
def installed_finder(monkeypatch):
    """
    Install a finder on sys.meta_path and record the adapter reinstalls it drives.

    The observable is Session._reinstall_adapter_for, which is what the finder
    exists to call and what both the old and the new finder reach for. Probing
    that rather than any internal of the current implementation is what lets
    these tests go red against the pre-2026-08 code instead of erroring out on
    a missing patch target.
    """
    calls: list[tuple[str, object]] = []

    def record(self: Session, framework: str) -> None:
        # Record the module's state at notification time, not afterwards: the
        # adapter can only hook classes that already exist.
        module = sys.modules.get(PROBE)
        calls.append((framework, getattr(module, "MARKER", None)))

    monkeypatch.setattr(Session, "_reinstall_adapter_for", record)

    installed: list[QBOMImportFinder] = []

    def install(watched: dict[str, str]) -> list[tuple[str, object]]:
        monkeypatch.setattr(QBOMImportFinder, "WATCHED_MODULES", watched)
        finder = QBOMImportFinder()
        sys.meta_path.insert(0, finder)
        installed.append(finder)
        return calls

    try:
        yield install
    finally:
        for finder in installed:
            if finder in sys.meta_path:
                sys.meta_path.remove(finder)


class TestImportFinder:
    def test_framework_imported_after_qbom_is_detected(self, probe_package, installed_finder):
        """The headline defect: a late import must reach the adapter."""
        calls = installed_finder({PROBE: "probe"})

        module = importlib.import_module(probe_package)

        assert calls == [("probe", "executed")], (
            f"expected exactly one notification, raised after the package finished executing; got {calls!r}"
        )
        assert module.MARKER == "executed", "the finder must not change what the import produces"
        assert module.backends.ProbeBackend is not None

    def test_unwatched_module_is_left_alone(self, probe_package, installed_finder):
        """Absence case: nothing fires for a module QBOM does not watch."""
        calls = installed_finder({"some_other_framework": "other"})

        module = importlib.import_module(probe_package)

        assert calls == []
        assert module.MARKER == "executed"

    def test_real_loader_is_restored_on_the_module(self, probe_package, installed_finder):
        """
        The proxy must not outlive the import.

        Code that inspects __loader__ (inspect.getsource, pkgutil, isinstance
        checks against SourceFileLoader) has to see what it would see without
        QBOM installed.
        """
        calls = installed_finder({PROBE: "probe"})

        module = importlib.import_module(probe_package)

        # Assert the premise: without this the loader assertions below would
        # hold trivially on code where the hook never runs at all.
        assert calls, "the import did not go through the QBOM loader"
        assert type(module.__loader__).__name__ != "_QBOMLoader"
        assert module.__spec__.loader is module.__loader__

    def test_finder_is_installed_by_importing_qbom(self):
        """Wiring guard: the hook has to be on sys.meta_path to do anything."""
        finders = [f for f in sys.meta_path if isinstance(f, QBOMImportFinder)]
        assert finders, "importing qbom must install a QBOMImportFinder"
        # find_spec is the only entry point Python 3.12+ calls.
        assert all(hasattr(f, "find_spec") for f in finders)


EXAMPLES = sorted((Path(__file__).resolve().parents[1] / "examples").glob("*.py"))

FRAMEWORK_IMPORT = re.compile(r"^\s*(?:import|from)\s+(qiskit|qiskit_aer|cirq|pennylane)\b", re.MULTILINE)
QBOM_IMPORT = re.compile(r"^\s*import\s+qbom\b", re.MULTILINE)


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda p: p.name)
def test_example_imports_qbom_before_its_framework(example):
    """
    The examples demonstrate the order that used to capture nothing.

    An import sorter reorders `import qbom` below the framework import, which
    silently converts each example into the order that always worked. Running
    them would then prove nothing about the defect they exist to cover.
    `ruff --fix` did exactly this once; hence per-file-ignores in pyproject.toml
    and this test.
    """
    source = example.read_text()

    qbom_at = QBOM_IMPORT.search(source)
    framework_at = FRAMEWORK_IMPORT.search(source)

    assert qbom_at, f"{example.name} does not import qbom"
    assert framework_at, f"{example.name} imports no quantum framework"
    assert qbom_at.start() < framework_at.start(), (
        f"{example.name} imports {framework_at.group(1)} before qbom, so it "
        "no longer demonstrates the case the import hook exists for"
    )


DOCUMENTED_ORDER_SCRIPT = textwrap.dedent(
    """
    import qbom  # first, exactly as README.md and the qramm.org guide instruct

    from qiskit import QuantumCircuit
    from qiskit_aer import AerSimulator

    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure([0, 1], [0, 1])

    job = AerSimulator().run(qc, shots=128)
    job.result().get_counts()

    trace = qbom.current()
    assert trace.circuits, "no circuit captured"
    assert trace.hardware is not None, "no hardware captured"
    assert trace.result is not None, "no result captured"
    print("CAPTURED")
    """
)


@pytest.mark.skipif(not QISKIT_AVAILABLE, reason="requires qiskit and qiskit-aer")
def test_documented_import_order_captures_a_trace(tmp_path):
    """
    End to end, in a fresh interpreter, in the order the docs tell people to use.

    A subprocess is not optional here: once any test in this process has
    imported qiskit, "qbom first" can no longer be reproduced in-process.
    """
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    env.pop("PYTHONHOME", None)

    result = subprocess.run(
        [sys.executable, "-c", DOCUMENTED_ORDER_SCRIPT],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "CAPTURED" in result.stdout
    assert list((tmp_path / ".qbom" / "traces").glob("*.json")), "no trace was written to disk"
