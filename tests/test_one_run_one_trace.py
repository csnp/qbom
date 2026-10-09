"""
Tests that one framework run writes one trace, and that it is the one shown.

A single cirq.Simulator().run() used to write two traces. The Cirq adapter's
install() imports cirq_google, a package QBOM's import hook watches, so the hook
asked for a Cirq adapter again while the first was still installing and not yet
registered. A second adapter was built and wrapped Simulator.run on top of the
first. The inner wrapper finalized a trace holding the circuit twice; the outer
wrapper then finalized a second, empty one, and qbom.current() returned that.
Every documented Cirq walkthrough ended by showing "Empty trace".

Capture is silent, so a capture that went wrong and one with nothing to capture
look alike. These tests therefore assert on what was captured, not on the
absence of an exception.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import subprocess
import sys
import textwrap
import types

import pytest

from qbom.adapters.base import Adapter
from qbom.core.session import QBOMImportFinder, Session

CIRQ_AVAILABLE = importlib.util.find_spec("cirq") is not None

FRAMEWORK = "qbom_probe_reentrant"
SIBLING = "qbom_probe_reentrant_sibling"
ADAPTER_MODULE = "qbom_probe_reentrant_adapter"


class _ReentrantAdapter(Adapter):
    """
    Stands in for an adapter whose install() imports a package QBOM watches.

    That is what the Cirq adapter does with cirq_google. Every install() that
    gets as far as hooking is recorded, because a second one is a second
    wrapper around the same function.
    """

    name = FRAMEWORK
    hooked: list[_ReentrantAdapter] = []

    def install(self) -> None:
        if self._installed:
            return
        importlib.import_module(SIBLING)
        type(self).hooked.append(self)
        self._installed = True

    def uninstall(self) -> None:
        self._installed = False


@pytest.fixture
def reentrant_framework(tmp_path, monkeypatch):
    """A watched sibling package, an adapter that imports it, and a fresh session."""
    (tmp_path / f"{SIBLING}.py").write_text("MARKER = 'executed'\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()

    adapter_module = types.ModuleType(ADAPTER_MODULE)
    adapter_module.ReentrantAdapter = _ReentrantAdapter  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, ADAPTER_MODULE, adapter_module)
    monkeypatch.setitem(Session.ADAPTER_MAP, FRAMEWORK, (ADAPTER_MODULE, "ReentrantAdapter"))
    monkeypatch.setattr(QBOMImportFinder, "WATCHED_MODULES", {SIBLING: FRAMEWORK})
    _ReentrantAdapter.hooked = []

    session = Session()
    finder = QBOMImportFinder(session)
    sys.meta_path.insert(0, finder)

    try:
        yield session
    finally:
        if finder in sys.meta_path:
            sys.meta_path.remove(finder)
        sys.modules.pop(SIBLING, None)
        importlib.invalidate_caches()


def test_an_install_that_imports_a_watched_package_installs_one_adapter(reentrant_framework):
    session = reentrant_framework

    session._install_adapter_for(FRAMEWORK)

    # Assert the premise: without the import going through the hook, the
    # counts below would hold on code that never re-enters at all.
    assert SIBLING in sys.modules, "the adapter's import did not run"

    installed = [adapter for adapter in session._adapters if adapter.name == FRAMEWORK]
    assert len(installed) == 1, f"expected one adapter for {FRAMEWORK}, got {len(installed)}"
    assert len(_ReentrantAdapter.hooked) == 1, (
        f"the framework was hooked {len(_ReentrantAdapter.hooked)} times; each extra hook is a "
        "second wrapper around the same call, and a second trace per run"
    )


def test_a_reinstall_that_imports_a_watched_package_hooks_once(reentrant_framework):
    """
    The same re-entry through _reinstall_adapter_for, the path the import hook takes
    when a framework is imported after qbom.
    """
    session = reentrant_framework

    session._reinstall_adapter_for(FRAMEWORK)

    assert SIBLING in sys.modules, "the adapter's import did not run"
    assert len([a for a in session._adapters if a.name == FRAMEWORK]) == 1
    assert len(_ReentrantAdapter.hooked) == 1


CIRQ_RUN_SCRIPT = """
    import json
    import qbom, cirq

    q = cirq.LineQubit.range(2)
    c = cirq.Circuit(cirq.H(q[0]), cirq.CNOT(q[0], q[1]), cirq.measure(*q))
    cirq.Simulator().run(c, repetitions=100)

    trace = qbom.current()
    print(json.dumps({
        "id": trace.id,
        "circuits": len(trace.circuits),
        "shots": trace.execution.shots if trace.execution else None,
        "summary": trace.summary,
    }))
"""


@pytest.mark.skipif(not CIRQ_AVAILABLE, reason="requires cirq")
def test_a_cirq_run_writes_one_trace_and_current_returns_it(tmp_path):
    """
    The walkthrough from the issue, end to end, in a fresh interpreter.

    A subprocess is required: the adapter patches cirq when it is imported, and
    the defect lives in the order of those imports.
    """
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    env.pop("PYTHONHOME", None)

    completed = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(CIRQ_RUN_SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert completed.returncode == 0, f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    shown = json.loads(completed.stdout.strip().splitlines()[-1])

    assert shown["circuits"] > 0, f"qbom.current() returned a trace with no circuits: {shown['summary']!r}"
    assert shown["shots"] == 100

    written = sorted((tmp_path / ".qbom" / "traces").glob("*.json"))
    assert len(written) == 1, f"one run wrote {len(written)} traces: {[p.name for p in written]}"

    on_disk = json.loads(written[0].read_text())
    assert on_disk["id"] == shown["id"], "qbom.current() is not the trace that was written for the run"
    assert len(on_disk["circuits"]) == 1, f"the run's circuit was recorded {len(on_disk['circuits'])} times"
