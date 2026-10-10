"""
qbom drift on a local simulator says drift does not apply.

A trace from aer_simulator, cirq.Simulator or generic_backend_5q records
`hardware.is_simulator` and no calibration, because a simulator has none.
Drift analysis treated that the same as hardware whose calibration went
uncaptured: it reported a drift score of 100/100, "Very Low" reproduction
feasibility, and a prediction that a re-run would likely produce different
results. None of that was measured, and the prediction is false for a seeded
simulator.

The drift score also ran the opposite way to the reproducibility score from
`qbom score` (higher drift is worse, a higher reproducibility score is better)
and nothing on screen said which way the drift number runs, so 100/100 read
as a perfect result while meaning the worst one.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import textwrap
from datetime import datetime, timezone

import pytest
from click.testing import CliRunner

from qbom.analysis.drift import analyze_drift
from qbom.cli.main import main
from qbom.core.models import Calibration, GateProperties, Hardware, QubitProperties
from qbom.core.session import Session
from qbom.core.trace import Trace, TraceBuilder

QISKIT_AVAILABLE = importlib.util.find_spec("qiskit") is not None and importlib.util.find_spec("qiskit_aer") is not None

# The three local simulators the defect was reported against, with the
# provider each adapter records for them.
SIMULATORS = [
    ("Aer (Local)", "aer_simulator"),
    ("Cirq", "cirq.Simulator"),
    ("Unknown", "generic_backend_5q"),
]

# A run on GenericBackendV2, for a fresh interpreter: the adapter patches Qiskit
# when it is imported, and what it records for this backend is what is tested.
GENERIC_BACKEND_RUN = """
    import qbom

    from qiskit import QuantumCircuit, transpile
    from qiskit.providers.fake_provider import GenericBackendV2

    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure_all()

    backend = GenericBackendV2(num_qubits=5, seed=3)
    backend.run(transpile(qc, backend), shots=128).result()
"""


def simulator_trace(provider: str, backend: str) -> Trace:
    """A simulator trace as the adapters write it: no calibration."""
    return (
        TraceBuilder()
        .set_hardware(Hardware(provider=provider, backend=backend, num_qubits=5, is_simulator=True))
        .build()
    )


def hardware_trace(calibration: Calibration | None) -> Trace:
    return (
        TraceBuilder()
        .set_hardware(
            Hardware(
                provider="IBM Quantum",
                backend="ibm_brisbane",
                num_qubits=127,
                qubits_used=[3, 5],
                calibration=calibration,
            )
        )
        .build()
    )


@pytest.fixture
def trace_store(tmp_path, monkeypatch):
    """Point the session's storage at an empty directory."""
    store = tmp_path / "traces"
    store.mkdir()
    monkeypatch.setattr(Session.get(), "_storage_path", store)
    return store


def save(store, trace: Trace) -> str:
    (store / f"{trace.id}.json").write_text(trace.to_json())
    return trace.id


@pytest.mark.parametrize(("provider", "backend"), SIMULATORS, ids=[b for _, b in SIMULATORS])
def test_simulator_without_calibration_is_not_scored_as_drift(provider: str, backend: str) -> None:
    result = analyze_drift(simulator_trace(provider, backend))

    assert result is not None
    assert result.reproduction_feasibility != "Very Low"
    assert result.reproduction_feasibility == "Not applicable"
    assert result.overall_drift_score is None
    assert not result.has_significant_drift
    assert not any("likely produce different results" in rec for rec in result.recommendations)
    assert any("drift does not apply" in rec for rec in result.recommendations)
    assert "100/100" not in result.summary()
    assert "not applicable" in result.summary()


def test_hardware_without_calibration_is_still_reported_as_unassessed() -> None:
    """The simulator case must not swallow hardware that lost its calibration."""
    result = analyze_drift(hardware_trace(calibration=None))

    assert result is not None
    assert result.overall_drift_score is not None
    assert result.reproduction_feasibility != "Not applicable"
    assert "Original calibration not captured - cannot assess drift" in result.recommendations


def test_cli_drift_on_a_simulator_says_drift_does_not_apply(trace_store) -> None:
    trace_id = save(trace_store, simulator_trace("Cirq", "cirq.Simulator"))

    result = CliRunner().invoke(main, ["drift", trace_id])

    assert result.exit_code == 0, result.output
    assert "Drift Score: not applicable" in result.output
    assert "100/100" not in result.output
    assert "Very Low" not in result.output
    assert "likely produce different results" not in result.output


@pytest.mark.skipif(not QISKIT_AVAILABLE, reason="requires qiskit and qiskit-aer")
def test_cli_drift_on_a_generic_backend_run_says_drift_does_not_apply(tmp_path, monkeypatch) -> None:
    """
    The generic_backend_5q case on a trace the Qiskit adapter wrote.

    The traces above are built by hand, so they hold `is_simulator` whether or
    not a run records it. GenericBackendV2 simulates its circuits locally, and
    neither its name nor its options say so. Recorded as hardware, its run was
    scored 100/100 like hardware whose calibration went uncaptured.
    """
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    env.pop("PYTHONHOME", None)

    completed = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(GENERIC_BACKEND_RUN)],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert completed.returncode == 0, f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"

    store = tmp_path / ".qbom" / "traces"
    written = sorted(store.glob("*.json"))
    assert len(written) == 1, f"one run wrote {len(written)} traces: {[p.name for p in written]}"

    hardware = json.loads(written[0].read_text())["hardware"]
    assert hardware["backend"] == "generic_backend_5q", "premise: the trace names the backend the run was given"
    assert hardware.get("calibration") is None, "premise: GenericBackendV2 has no calibration to capture"

    monkeypatch.setattr(Session.get(), "_storage_path", store)
    result = CliRunner().invoke(main, ["drift", written[0].stem])

    assert result.exit_code == 0, result.output
    assert "Drift Score: not applicable" in result.output
    assert "generic_backend_5q is a simulator" in result.output
    assert "100/100" not in result.output
    assert "Very Low" not in result.output
    assert "likely produce different results" not in result.output
    assert hardware["is_simulator"] is True


def test_cli_drift_score_states_its_direction(trace_store) -> None:
    calibration = Calibration(
        timestamp=datetime.now(timezone.utc),
        qubits=[QubitProperties(index=3, t1_us=95.0, t2_us=70.0, readout_error=0.02)],
        gates=[GateProperties(gate="cx", qubits=(3, 5), error=0.0102)],
    )
    trace_id = save(trace_store, hardware_trace(calibration))

    result = CliRunner().invoke(main, ["drift", trace_id])

    assert result.exit_code == 0, result.output
    assert "/100 (higher means more drift)" in result.output
