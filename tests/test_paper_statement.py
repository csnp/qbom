"""
Tests for the reproducibility statement.

This text is written to be pasted into a Methods section, so its grammar is a
correctness property, not a cosmetic one.
"""

from __future__ import annotations

from qbom.cli.display import generate_paper_statement
from qbom.core.models import Environment, Execution, Hardware, Package
from qbom.core.trace import Trace


def _trace(**kwargs) -> Trace:
    return Trace(**kwargs)


def test_software_and_hardware_form_one_sentence():
    """
    "using qiskit==2.5.1. on the aer_simulator simulator" was the shipped text.

    The period left "on the ... simulator" as a fragment.
    """
    trace = _trace(
        environment=Environment(
            python="3.12.0",
            platform="Linux",
            packages=[Package(name="qiskit", version="2.5.1")],
        ),
        hardware=Hardware(provider="Aer (Local)", backend="aer_simulator", num_qubits=32, is_simulator=True),
    )

    statement = generate_paper_statement(trace)

    assert "Experiments were performed using qiskit==2.5.1 on the aer_simulator simulator." in statement
    assert ". on the" not in statement


def test_hardware_without_software_still_starts_a_sentence():
    """The clause has to carry its own subject when the SDK is unknown."""
    trace = _trace(hardware=Hardware(provider="IBM Quantum", backend="ibm_torino", num_qubits=133, is_simulator=False))

    statement = generate_paper_statement(trace)

    assert "Experiments were performed on the IBM Quantum ibm_torino quantum processor (133 qubits)." in statement
    assert not any(line.startswith("on the") for line in statement.splitlines())


def test_later_clauses_stay_separate_sentences():
    trace = _trace(
        environment=Environment(
            python="3.12.0",
            platform="Linux",
            packages=[Package(name="qiskit", version="2.5.1")],
        ),
        execution=Execution(job_id="job-1", shots=4096),
    )

    statement = generate_paper_statement(trace)

    assert "using qiskit==2.5.1. Each experiment used 4,096 shots." in statement


def test_empty_trace_says_so_instead_of_printing_a_lone_period():
    """An empty trace used to render the statement as a single "." character."""
    statement = generate_paper_statement(_trace())

    assert "\n.\n" not in statement
    assert "nothing to state" in statement
    assert "qbom validate" in statement
