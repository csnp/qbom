"""Tests for QBOM core models."""

import pytest

from qbom.core.models import (
    Circuit,
    Counts,
    Environment,
    GateCounts,
    Package,
)
from qbom.core.trace import Trace, TraceBuilder


class TestPackage:
    def test_package_str(self):
        pkg = Package(name="qiskit", version="1.0.2")
        assert str(pkg) == "qiskit==1.0.2"

    def test_package_purl(self):
        pkg = Package(name="qiskit", version="1.0.2", purl="pkg:pypi/qiskit@1.0.2")
        assert pkg.purl == "pkg:pypi/qiskit@1.0.2"


class TestEnvironment:
    def test_quantum_sdk_detection(self):
        env = Environment(
            python="3.11.5",
            platform="Linux",
            packages=[
                Package(name="qiskit", version="1.0.2"),
                Package(name="numpy", version="1.24.0"),
            ],
        )
        assert env.quantum_sdk == "qiskit==1.0.2"

    def test_no_quantum_sdk(self):
        env = Environment(
            python="3.11.5",
            platform="Linux",
            packages=[Package(name="numpy", version="1.24.0")],
        )
        assert env.quantum_sdk is None


class TestCircuit:
    def test_circuit_summary(self):
        circuit = Circuit(
            name="Bell State",
            num_qubits=2,
            depth=2,
            gates=GateCounts(single_qubit=1, two_qubit=1, total=2),
            hash="abc123",
        )
        assert "Bell State" in circuit.summary
        assert "2q" in circuit.summary
        assert "depth 2" in circuit.summary


class TestCounts:
    def test_probabilities(self):
        counts = Counts(raw={"00": 500, "11": 500}, shots=1000)
        probs = counts.probabilities
        assert probs["00"] == pytest.approx(0.5)
        assert probs["11"] == pytest.approx(0.5)

    def test_top_results(self):
        counts = Counts(
            raw={"00": 400, "11": 350, "01": 150, "10": 100},
            shots=1000,
        )
        top = counts.top_results
        assert top[0][0] == "00"
        assert top[1][0] == "11"


class TestTrace:
    def test_trace_id_generation(self):
        trace = Trace()
        assert trace.id.startswith("qbom_")
        assert len(trace.id) == 13  # "qbom_" + 8 hex chars

    def test_trace_summary_empty(self):
        trace = Trace()
        assert trace.summary == "Empty trace"

    def test_trace_to_dict(self):
        trace = Trace()
        d = trace.to_dict()
        assert d["qbom_version"] == "1.1"
        assert "id" in d
        assert "created_at" in d


class TestTraceBuilder:
    def test_builder_basic(self):
        builder = TraceBuilder()
        builder.set_metadata(name="Test", tags=["unit-test"])

        trace = builder.build()
        assert trace.metadata.name == "Test"
        assert "unit-test" in trace.metadata.tags

    def test_builder_chaining(self):
        env = Environment(python="3.11.5", platform="Linux")
        circuit = Circuit(
            num_qubits=2,
            depth=2,
            gates=GateCounts(total=2),
            hash="abc123",
        )

        trace = TraceBuilder().set_environment(env).add_circuit(circuit).set_metadata(name="Chained").build()

        assert trace.environment.python == "3.11.5"
        assert len(trace.circuits) == 1
        assert trace.metadata.name == "Chained"
