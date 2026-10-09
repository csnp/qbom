"""
Tests that a PennyLane QNode call writes the circuit it ran into its trace.

The adapter read the executed tape from `qnode.tape` or `qnode.qtape` after the
call. PennyLane removed both attributes, so on current releases every QNode
call wrote a trace that named a backend and carried a result but held no
circuit: an experiment whose program is unknown. The read failed quietly, so
nothing reported the loss.

The scripts run in a fresh interpreter for the reason given in
test_capture_never_raises.py: the adapter hooks PennyLane at import, and a
framework another test in this process already imported changes what is hooked.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import textwrap

import pytest

PENNYLANE_AVAILABLE = importlib.util.find_spec("pennylane") is not None

pytestmark = pytest.mark.skipif(not PENNYLANE_AVAILABLE, reason="requires pennylane")


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


def written_traces(tmp_path) -> list[dict]:
    """Every trace the script saved to its trace store."""
    store = tmp_path / ".qbom" / "traces"
    return [json.loads(path.read_text()) for path in sorted(store.glob("*.json"))]


# The reproduction from the report, unchanged.
BELL_COUNTS_SCRIPT = """
    import qbom

    import pennylane as qml

    dev = qml.device("default.qubit", wires=2, shots=100)

    @qml.qnode(dev)
    def bell():
        qml.Hadamard(wires=0)
        qml.CNOT(wires=[0, 1])
        return qml.counts()

    counts = bell()

    assert sum(int(v) for v in counts.values()) == 100, f"qnode did not return the caller's result: {counts}"
    print("RAN")
"""


def test_a_qnode_call_writes_the_circuit_it_ran(tmp_path):
    result = run_script(BELL_COUNTS_SCRIPT, tmp_path)

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "RAN" in result.stdout

    traces = written_traces(tmp_path)
    assert len(traces) == 1, f"expected one trace for one QNode call, found {len(traces)}"
    trace = traces[0]

    assert trace["hardware"]["backend"] == "default.qubit"
    assert trace["result"]["counts"]["shots"] == 100
    assert trace["circuits"], "the trace names a backend and a result but holds no circuit"

    (circuit,) = trace["circuits"]
    assert circuit["num_qubits"] == 2
    assert circuit["num_clbits"] == 1
    assert circuit["gates"]["by_name"] == {"hadamard": 1, "cnot": 1}
    assert circuit["gates"]["single_qubit"] == 1
    assert circuit["gates"]["two_qubit"] == 1
    assert circuit["gates"]["total"] == 2


def test_a_qnode_call_does_not_report_a_missing_circuit(tmp_path):
    result = run_script(BELL_COUNTS_SCRIPT, tmp_path)

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "QBOM could not capture" not in result.stderr, f"stderr:\n{result.stderr}"


def test_each_call_records_its_own_circuit(tmp_path):
    """
    A QNode keeps the last tape it built. Reading that after the call could
    attach an earlier call's circuit to a later call's result, so each call
    must record the tape built during that call and no other.
    """
    script = """
        import qbom

        import pennylane as qml

        dev = qml.device("default.qubit", wires=1, shots=50)

        @qml.qnode(dev)
        def rotation(theta):
            qml.RX(theta, wires=0)
            return qml.expval(qml.PauliZ(0))

        rotation(0.1)
        rotation(0.2)
        print("RAN")
    """

    result = run_script(script, tmp_path)

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    traces = written_traces(tmp_path)
    assert len(traces) == 2, f"expected one trace per QNode call, found {len(traces)}"
    assert all(len(trace["circuits"]) == 1 for trace in traces), [trace["circuits"] for trace in traces]

    hashes = {trace["circuits"][0]["hash"] for trace in traces}
    assert len(hashes) == 2, "two calls with different parameters recorded the same circuit"


def test_a_call_that_builds_no_tape_says_so_and_keeps_the_result(tmp_path):
    """
    If a PennyLane release stops building its tape through `QNode.construct`,
    the circuit is lost. That loss is reported once rather than written as a
    trace that looks complete, and the call still returns its result and still
    records its execution.
    """
    script = """
        import qbom

        import pennylane as qml

        # Undo the hook, as a release that built the tape some other way would.
        qml.QNode.construct = qml.QNode.construct.__wrapped__

        dev = qml.device("default.qubit", wires=1, shots=50)

        @qml.qnode(dev)
        def flip():
            qml.PauliX(wires=0)
            return qml.expval(qml.PauliZ(0))

        value = float(flip())
        float(flip())

        assert abs(value + 1.0) < 1e-9, f"qnode did not return the caller's result: {value}"
        print("RAN")
    """

    result = run_script(script, tmp_path)

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "RAN" in result.stdout
    assert result.stderr.count("QBOM could not capture QNode call circuit") == 1, f"stderr:\n{result.stderr}"

    traces = written_traces(tmp_path)
    assert len(traces) == 2
    assert all(trace["circuits"] == [] for trace in traces)
    assert all(trace["result"] is not None for trace in traces)
