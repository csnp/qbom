"""
Tests that a trace names the backend the caller passed to run().

GenericBackendV2 and the fake device backends do not simulate anything
themselves. Their run() hands the circuits to an AerSimulator they hold
internally. QBOM wrapped only BackendV2.run and AerBackend.run, and every
concrete backend overrides run(), so the caller's backend was never seen and
the inner delegate was recorded instead: a run on generic_backend_5q produced
a trace saying "Aer (Local)", "aer_simulator", 32 qubits. Worse, a calibration
captured correctly at transpile time was then replaced by the delegate's,
which has none.

The scripts run in a fresh interpreter because the hooks are process-wide and
the order of `import qbom` against the framework import is part of what is
being tested.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import textwrap

import pytest

QISKIT_AVAILABLE = importlib.util.find_spec("qiskit") is not None and importlib.util.find_spec("qiskit_aer") is not None

pytestmark = pytest.mark.skipif(not QISKIT_AVAILABLE, reason="requires qiskit and qiskit-aer")


def run_script(script: str, tmp_path) -> dict:
    """Run a script in a fresh interpreter and return the JSON it printed last."""
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    env.pop("PYTHONHOME", None)

    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    lines = [line for line in result.stdout.splitlines() if line.startswith("QBOM ")]
    assert lines, f"script printed no result\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    return json.loads(lines[-1][len("QBOM ") :])


# Shared by the scripts below: a circuit, and a report of what was recorded.
PRELUDE = """
    import json

    import qbom

    from qiskit import QuantumCircuit, transpile
    from qiskit.providers.fake_provider import GenericBackendV2

    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure_all()

    def report(passed, **extra):
        session = qbom.Session.get()
        hardware = qbom.current().hardware
        calibration = hardware.calibration if hardware else None
        print("QBOM " + json.dumps({
            "passed": {"backend": passed.name, "numQubits": passed.num_qubits},
            "recorded": None if hardware is None else {
                "provider": hardware.provider,
                "backend": hardware.backend,
                "numQubits": hardware.num_qubits,
            },
            "calibrationT1": None if calibration is None else [q.t1_us for q in calibration.qubits],
            "traces": len(session._traces),
            **extra,
        }))
"""

# A delegating backend that reports a calibration, standing in for a fake
# device backend such as FakeBrisbane without needing qiskit-ibm-runtime. It
# inherits GenericBackendV2.run, which hands the circuits to an AerSimulator.
CALIBRATED_BACKEND = """
    from datetime import datetime, timezone

    class Properties:
        last_update_date = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        gates = []

        def t1(self, qubit):
            return (100 + qubit) * 1e-6

        def t2(self, qubit):
            return (80 + qubit) * 1e-6

        def readout_error(self, qubit):
            return 0.01 * (qubit + 1)

        def frequency(self, qubit):
            return (5.0 + qubit / 10) * 1e9

    class CalibratedBackend(GenericBackendV2):
        def __init__(self, *args, readable=None, **kwargs):
            super().__init__(*args, **kwargs)
            self.reads = 0
            self.readable = readable

        def properties(self):
            self.reads += 1
            if self.readable is not None and self.reads > self.readable:
                return None
            return Properties()
"""

EXPECTED_T1 = [100.0, 101.0, 102.0, 103.0, 104.0]


def test_run_records_the_backend_the_caller_passed(tmp_path):
    # The reproduction from the report, unchanged.
    out = run_script(
        PRELUDE
        + """
    backend = GenericBackendV2(num_qubits=5, seed=42)
    tqc = transpile(qc, backend, optimization_level=2)
    counts = backend.run(tqc, shots=1024).result().get_counts()
    assert sum(counts.values()) == 1024

    report(backend)
""",
        tmp_path,
    )

    assert out["recorded"]["backend"] == out["passed"]["backend"] == "generic_backend_5q"
    assert out["recorded"]["numQubits"] == out["passed"]["numQubits"] == 5
    assert out["recorded"]["provider"] != "Aer (Local)"


def test_run_without_transpile_records_the_backend_the_caller_passed(tmp_path):
    # No transpile stage to fall back on: run() alone has to name the backend.
    out = run_script(
        PRELUDE
        + """
    backend = GenericBackendV2(num_qubits=5, seed=7)
    backend.run(transpile(qc, basis_gates=["cx", "rz", "sx", "x"]), shots=256).result()

    report(backend)
""",
        tmp_path,
    )

    assert out["recorded"]["backend"] == "generic_backend_5q"
    assert out["recorded"]["numQubits"] == 5


def test_one_run_through_a_delegate_is_one_trace(tmp_path):
    out = run_script(
        PRELUDE
        + """
    backend = GenericBackendV2(num_qubits=5, seed=42)
    backend.run(transpile(qc, backend), shots=128).result()

    report(backend)
""",
        tmp_path,
    )

    assert out["traces"] == 1


def test_calibration_captured_at_transpile_survives_the_run(tmp_path):
    out = run_script(
        PRELUDE
        + CALIBRATED_BACKEND
        + """
    backend = CalibratedBackend(num_qubits=5, seed=42)
    tqc = transpile(qc, backend, optimization_level=2)
    backend.run(tqc, shots=512).result()

    report(backend)
""",
        tmp_path,
    )

    assert out["recorded"]["backend"] == "generic_backend_5q"
    assert out["calibrationT1"] == pytest.approx(EXPECTED_T1)


def test_calibration_is_kept_when_the_run_cannot_read_it_again(tmp_path):
    # The backend answers properties() once, at transpile, and not at run.
    out = run_script(
        PRELUDE
        + CALIBRATED_BACKEND
        + """
    backend = CalibratedBackend(num_qubits=5, seed=42, readable=1)
    tqc = transpile(qc, backend, optimization_level=2)
    backend.run(tqc, shots=512).result()

    report(backend, reads=backend.reads)
""",
        tmp_path,
    )

    assert out["reads"] >= 2, "premise: run() must have read the calibration a second time"
    assert out["recorded"]["backend"] == "generic_backend_5q"
    assert out["calibrationT1"] == pytest.approx(EXPECTED_T1)


def test_a_calibration_is_not_carried_to_a_different_backend(tmp_path):
    # Same name, different object. The calibration read from the transpile
    # target must not be attributed to the backend the circuit actually ran on.
    out = run_script(
        PRELUDE
        + CALIBRATED_BACKEND
        + """
    target = CalibratedBackend(num_qubits=5, seed=42)
    tqc = transpile(qc, target, optimization_level=2)

    other = GenericBackendV2(num_qubits=5, seed=3)
    other.run(tqc, shots=128).result()

    report(other)
""",
        tmp_path,
    )

    assert out["recorded"]["backend"] == "generic_backend_5q"
    assert out["calibrationT1"] is None


def test_a_direct_aer_run_is_still_recorded_as_aer(tmp_path):
    out = run_script(
        PRELUDE
        + """
    from qiskit_aer import AerSimulator

    backend = AerSimulator()
    backend.run(transpile(qc, backend), shots=128).result()

    report(backend)
""",
        tmp_path,
    )

    assert out["recorded"]["backend"] == "aer_simulator"
    assert out["recorded"]["provider"] == "Aer (Local)"
    assert out["traces"] == 1


def test_uninstall_removes_the_run_hooks_and_install_restores_them(tmp_path):
    out = run_script(
        PRELUDE
        + """
    from qiskit.providers import BackendV2

    from qbom.adapters.qiskit import QiskitAdapter

    def hooked(cls):
        return getattr(cls.__dict__.get("run"), "_qbom_wrapped", False)

    adapter = QiskitAdapter._get_instance()
    before = hooked(GenericBackendV2)

    adapter.uninstall()
    class DefinedWhileUninstalled(GenericBackendV2):
        def run(self, run_input, **options):
            return super().run(run_input, **options)
    after_uninstall = [
        hooked(GenericBackendV2),
        hooked(DefinedWhileUninstalled),
        "__init_subclass__" in BackendV2.__dict__,
    ]

    adapter.install()
    after_install = [hooked(GenericBackendV2), hooked(DefinedWhileUninstalled)]

    backend = DefinedWhileUninstalled(num_qubits=5, seed=1)
    backend.run(transpile(qc, backend), shots=64).result()

    report(backend, before=before, afterUninstall=after_uninstall, afterInstall=after_install)
""",
        tmp_path,
    )

    assert out["before"] is True
    assert out["afterUninstall"] == [False, False, False]
    assert out["afterInstall"] == [True, True]
    assert out["recorded"]["backend"] == "generic_backend_5q"
    assert out["traces"] == 1
