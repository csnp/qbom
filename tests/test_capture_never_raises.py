"""
Tests that provenance capture cannot fail the program it is capturing.

QBOM runs inside calls the user made for their own reasons. Capture that does
not happen costs a trace. An exception escaping a capture wrapper costs the
experiment, which is the thing the user is actually here for.

`import qbom` used to be able to abort a script one line later.
`_capture_backend` built `Hardware(num_qubits=backend.num_qubits, ...)` with no
guard, and `BackendV2.num_qubits` is legitimately None for an unbounded
simulator, so `transpile(circuit, BasicSimulator())` ended in a pydantic
ValidationError raised out of Qiskit's own function. Removing the `import qbom`
line made the same script pass.

Both halves are covered here: the model accepts a backend that reports no qubit
count, and every wrapper degrades to "not captured" when anything inside the
capture raises. The subprocess tests exist because the failure being reproduced
is a script that stops running, and because import order matters once any test
in this process has imported a framework.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import textwrap
import warnings

import pytest

from qbom.adapters.base import capture_guard
from qbom.cli.display import console, display_trace, generate_paper_statement
from qbom.core.models import Execution, Hardware
from qbom.core.trace import TraceBuilder

QISKIT_AVAILABLE = importlib.util.find_spec("qiskit") is not None and importlib.util.find_spec("qiskit_aer") is not None
CIRQ_AVAILABLE = importlib.util.find_spec("cirq") is not None
PENNYLANE_AVAILABLE = importlib.util.find_spec("pennylane") is not None


def run_script(script: str, tmp_path) -> subprocess.CompletedProcess:
    """Run a script in a fresh interpreter with its own trace store."""
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    env.pop("PYTHONHOME", None)

    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


# ============================================================================
# A backend that reports no qubit count
# ============================================================================


def test_hardware_accepts_a_backend_that_reports_no_qubit_count():
    hardware = Hardware(
        provider="Unknown",
        backend="basic_simulator",
        num_qubits=None,
        is_simulator=True,
    )

    assert hardware.num_qubits is None


def test_a_missing_qubit_count_is_not_printed_as_a_null():
    """
    The field was loosened, so the two places that read it have to stay right.
    """
    trace = (
        TraceBuilder()
        .set_hardware(
            Hardware(
                provider="IBM Quantum",
                backend="ibm_torino",
                num_qubits=None,
                qubits_used=[0, 1],
                is_simulator=False,
            )
        )
        .set_execution(Execution(shots=1024))
        .build()
    )

    with console.capture() as captured:
        display_trace(trace)
    shown = captured.get()

    assert "None" not in shown, shown
    assert "None" not in generate_paper_statement(trace)


NO_QUBIT_COUNT_SCRIPT = """
    import qbom  # the line that used to abort the script three lines later

    from qiskit import QuantumCircuit, transpile
    from qiskit.providers.basic_provider import BasicSimulator

    backend = BasicSimulator()
    assert backend.num_qubits is None, (
        "premise: this test needs a backend that reports no qubit count"
    )

    transpiled = transpile(QuantumCircuit(2), backend, optimization_level=2)

    assert transpiled.num_qubits == 2, "transpile did not return the caller's circuit"
    print("TRANSPILED")
"""


@pytest.mark.skipif(not QISKIT_AVAILABLE, reason="requires qiskit")
def test_transpile_against_an_unbounded_simulator_still_returns(tmp_path):
    result = run_script(NO_QUBIT_COUNT_SCRIPT, tmp_path)

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "TRANSPILED" in result.stdout


# ============================================================================
# Anything raised inside capture, in any adapter
# ============================================================================


QISKIT_CAPTURE_RAISES_SCRIPT = """
    import qbom

    from qiskit import QuantumCircuit, transpile
    from qiskit_aer import AerSimulator

    import qbom.adapters.qiskit as adapter

    def explode(*args, **kwargs):
        raise RuntimeError("capture is broken")

    adapter._circuit_to_model = explode

    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure([0, 1], [0, 1])

    simulator = AerSimulator()
    transpiled = transpile(qc, simulator, optimization_level=1)
    counts = simulator.run(transpiled, shots=128).result().get_counts()

    assert transpiled.num_qubits == 2, "transpile did not return the caller's circuit"
    assert sum(counts.values()) == 128, "run did not return the caller's counts"
    print("RAN")
"""


CIRQ_CAPTURE_RAISES_SCRIPT = """
    import qbom

    import cirq

    import qbom.adapters.cirq as adapter

    def explode(*args, **kwargs):
        raise RuntimeError("capture is broken")

    adapter._circuit_to_model = explode

    q0, q1 = cirq.LineQubit.range(2)
    circuit = cirq.Circuit(cirq.H(q0), cirq.CNOT(q0, q1), cirq.measure(q0, q1, key="m"))

    result = cirq.Simulator().run(circuit, repetitions=64)

    assert len(result.measurements["m"]) == 64, "run did not return the caller's result"
    print("RAN")
"""


PENNYLANE_CAPTURE_RAISES_SCRIPT = """
    import qbom

    import pennylane as qml

    import qbom.adapters.pennylane as adapter

    def explode(*args, **kwargs):
        raise RuntimeError("capture is broken")

    adapter._extract_device_info = explode

    device = qml.device("default.qubit", wires=2)

    @qml.qnode(device)
    def circuit():
        qml.Hadamard(wires=0)
        qml.CNOT(wires=[0, 1])
        return qml.expval(qml.PauliZ(0))

    value = float(circuit())

    assert abs(value) < 1e-9, f"qnode did not return the caller's result: {value}"
    print("RAN")
"""


@pytest.mark.parametrize(
    ("script", "available", "framework"),
    [
        (QISKIT_CAPTURE_RAISES_SCRIPT, QISKIT_AVAILABLE, "qiskit"),
        (CIRQ_CAPTURE_RAISES_SCRIPT, CIRQ_AVAILABLE, "cirq"),
        (PENNYLANE_CAPTURE_RAISES_SCRIPT, PENNYLANE_AVAILABLE, "pennylane"),
    ],
    ids=["qiskit", "cirq", "pennylane"],
)
def test_capture_that_raises_does_not_reach_the_caller(tmp_path, script, available, framework):
    """
    Forced failure inside capture, in each adapter that wraps a user call.

    The reported defect was one unguarded line in the Qiskit adapter. Every
    adapter does capture work inside a wrapper around a call the user made, so
    every one of them is checked here rather than the single line that was
    reported.
    """
    if not available:
        pytest.skip(f"requires {framework}")

    result = run_script(script, tmp_path)

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "RAN" in result.stdout


@pytest.mark.parametrize(
    ("script", "available", "framework"),
    [
        (QISKIT_CAPTURE_RAISES_SCRIPT, QISKIT_AVAILABLE, "qiskit"),
        (CIRQ_CAPTURE_RAISES_SCRIPT, CIRQ_AVAILABLE, "cirq"),
        (PENNYLANE_CAPTURE_RAISES_SCRIPT, PENNYLANE_AVAILABLE, "pennylane"),
    ],
    ids=["qiskit", "cirq", "pennylane"],
)
def test_capture_that_fails_says_so_once(tmp_path, script, available, framework):
    """
    Degrading silently would leave a run that captured nothing looking like a
    run with nothing to capture. One report, not one per call.
    """
    if not available:
        pytest.skip(f"requires {framework}")

    result = run_script(script, tmp_path)

    assert "QBOM could not capture" in result.stderr, f"stderr:\n{result.stderr}"


def test_the_guard_reports_a_stage_once(monkeypatch):
    """The report is per stage, not per call: a wrapper is on a hot path."""
    import qbom.adapters.base as base

    monkeypatch.setattr(base, "_WARNED_STAGES", set())

    with pytest.warns(RuntimeWarning, match="QBOM could not capture"):
        with capture_guard("probe", "probe stage"):
            raise RuntimeError("capture is broken")

    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        with capture_guard("probe", "probe stage"):
            raise RuntimeError("capture is broken")

    assert recorded == [], "the same stage reported itself twice"


def test_the_guard_lets_a_keyboard_interrupt_through(monkeypatch):
    """Swallowing Ctrl-C would make a running experiment impossible to stop."""
    import qbom.adapters.base as base

    monkeypatch.setattr(base, "_WARNED_STAGES", set())

    with pytest.raises(KeyboardInterrupt):
        with capture_guard("probe", "probe stage"):
            raise KeyboardInterrupt


def test_reporting_a_capture_failure_cannot_itself_abort_the_caller():
    """
    The guard reports a failed capture through warnings.warn, and under an
    error-promoting filter warnings.warn raises. Raising there would abort the
    user's call from inside the guard that exists to prevent exactly that.
    """
    import warnings

    from qbom.adapters.base import _WARNED_STAGES, capture_guard

    _WARNED_STAGES.discard("testframework.reporting-must-not-raise")

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)

        with capture_guard("testframework", "reporting-must-not-raise"):
            raise ValueError("capture failed")

    # Reaching here is the assertion: the guard swallowed both the capture
    # failure and the error-promoted warning about it.


def test_a_trace_whose_backend_reports_no_qubit_count_can_be_read_back(tmp_path):
    """
    The round trip, not the construction, is where this field breaks.

    `Trace.to_json()` serialises with exclude_none=True, so a null qubit count
    is dropped from the file. If the field is nullable but still required, the
    trace QBOM has just written cannot be loaded again: the first fix for the
    BasicSimulator crash produced exactly that, turning a crash into a file that
    could never be read.

    Constructing Hardware(num_qubits=None) in memory passes either way, which is
    why this has to go through disk.
    """
    from qbom.core.models import Execution, Hardware
    from qbom.core.timeutil import utc_now
    from qbom.core.trace import Trace, TraceBuilder

    trace = (
        TraceBuilder()
        .set_hardware(Hardware(provider="Unknown", backend="basic_simulator", num_qubits=None))
        .set_execution(Execution(shots=128, completed_at=utc_now()))
        .build()
    )

    path = tmp_path / "no-qubit-count.qbom.json"
    written = trace.to_json()
    path.write_text(written)

    assert "num_qubits" not in json.loads(written).get("hardware", {}), (
        "premise failed: the field survived serialisation, so this test no "
        "longer exercises the reload path it exists for"
    )

    reloaded = Trace.model_validate_json(path.read_text())

    assert reloaded.hardware is not None
    assert reloaded.hardware.num_qubits is None
    assert reloaded.hardware.backend == "basic_simulator"


@pytest.mark.skipif(importlib.util.find_spec("cirq") is None, reason="requires cirq")
def test_cirq_simulate_is_not_broken_by_the_wrapper(tmp_path):
    """
    A wrapper that restates a framework's signature also restates its defaults,
    and they drift. This one declared `qubit_order=None` and forwarded it
    positionally, while cirq's own default is QubitOrder.DEFAULT, so a plain
    simulate(circuit) died inside the user's call with
    "Don't know how to interpret <None> as a Basis".

    Run in a subprocess: the adapter patches cirq at import time, and the
    default it forwards is decided then.
    """
    script = textwrap.dedent(
        """
        import qbom, cirq
        q = cirq.LineQubit.range(2)
        c = cirq.Circuit(cirq.H(q[0]), cirq.CNOT(q[0], q[1]))
        positional = cirq.Simulator().simulate(c)
        keyword = cirq.Simulator().simulate(program=c)
        ordered = cirq.Simulator().simulate(c, qubit_order=[q[1], q[0]])
        assert positional is not None and keyword is not None and ordered is not None
        print("SIMULATE_SURVIVED", len(qbom.current().circuits))
        """
    )
    path = tmp_path / "simulate.py"
    path.write_text(script)

    env = dict(os.environ, HOME=str(tmp_path))
    completed = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, env=env)

    assert completed.returncode == 0, f"cirq simulate did not survive the wrapper:\n{completed.stderr}"
    assert "SIMULATE_SURVIVED" in completed.stdout
