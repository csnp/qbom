"""
Tests for which circuit `qbom diff` compares.

Transpilation rewrites a circuit for the backend it targets: it maps qubits,
substitutes gates for the basis and changes depth. Two runs of one source
circuit at optimization levels 0 and 3 execute different circuits. diff
compared the circuit as submitted, so it reported those two runs as identical
on every row, the circuit hash included.

The circuit values below are from a real capture: one three-qubit circuit
transpiled to the basis rz, sx, x, cx at optimization levels 0 and 3 with
seed_transpiler=7 and run on AerSimulator.
"""

from __future__ import annotations

import re

import pytest
from click.testing import CliRunner

from qbom.cli.main import main
from qbom.core.models import Circuit, Execution, GateCounts, Hardware, Transpilation
from qbom.core.session import Session
from qbom.core.trace import Trace

SOURCE = Circuit(
    name="ghz",
    num_qubits=3,
    num_clbits=3,
    depth=8,
    gates=GateCounts(single_qubit=3, two_qubit=4, total=10, by_name={"cx": 4, "h": 3, "measure": 3}),
    hash="1cff503a9be0a406",
)

TRANSPILED_AT_LEVEL_0 = Circuit(
    name="ghz",
    num_qubits=3,
    num_clbits=3,
    depth=14,
    gates=GateCounts(single_qubit=9, two_qubit=4, total=16, by_name={"rz": 6, "cx": 4, "sx": 3, "measure": 3}),
    hash="68e64e9917d33a7c",
)

TRANSPILED_AT_LEVEL_3 = Circuit(
    name="ghz",
    num_qubits=3,
    num_clbits=3,
    depth=6,
    gates=GateCounts(single_qubit=3, two_qubit=2, total=8, by_name={"measure": 3, "rz": 2, "cx": 2, "sx": 1}),
    hash="c0ccfad4f8df576e",
)

BASIS = ["rz", "sx", "x", "cx"]


def _run(optimization_level: int | None, executed: Circuit | None) -> Trace:
    """A trace of SOURCE, transpiled to `executed` when one is given."""
    transpilation = None
    circuits = [SOURCE]
    if executed is not None:
        transpilation = Transpilation(
            optimization_level=optimization_level,
            basis_gates=BASIS,
            seed=7,
            input_circuit=SOURCE,
            output_circuit=executed,
        )
        circuits = [SOURCE, executed]
    return Trace(
        circuits=circuits,
        transpilation=transpilation,
        hardware=Hardware(provider="Aer (Local)", backend="aer_simulator", is_simulator=True),
        execution=Execution(shots=256),
    )


@pytest.fixture
def trace_store(tmp_path, monkeypatch):
    """Point the session's storage at an empty directory."""
    store = tmp_path / "traces"
    store.mkdir()
    monkeypatch.setattr(Session.get(), "_storage_path", store)
    return store


def _diff(store, first: Trace, second: Trace) -> str:
    for trace in (first, second):
        (store / f"{trace.id}.json").write_text(trace.to_json())
    result = CliRunner().invoke(main, ["diff", first.id, second.id])
    assert result.exit_code == 0, result.output
    return result.output


def _row(output: str, prop: str) -> list[str]:
    """The cells of the table row whose first cell is `prop`."""
    for line in output.splitlines():
        cells = [cell.strip() for cell in re.split(r"[│|]", line)[1:-1]]
        if cells and cells[0] == prop:
            return cells
    raise AssertionError(f"no {prop!r} row in:\n{output}")


def _matches(output: str, prop: str) -> bool:
    match = _row(output, prop)[-1]
    assert match in ("✓", "✗"), match
    return match == "✓"


def test_executed_circuits_that_differ_are_reported_as_different(trace_store):
    """The reported defect: every circuit row matched, the hash included."""
    output = _diff(trace_store, _run(0, TRANSPILED_AT_LEVEL_0), _run(3, TRANSPILED_AT_LEVEL_3))

    assert _row(output, "Circuit hash")[1:3] == [TRANSPILED_AT_LEVEL_0.hash, TRANSPILED_AT_LEVEL_3.hash]
    assert not _matches(output, "Circuit hash")
    assert not _matches(output, "Circuit depth")
    assert not _matches(output, "Circuit gates")
    # The qubit count is the same, and diff still says so.
    assert _matches(output, "Circuit qubits")


def test_diff_says_it_compared_the_transpiled_circuit(trace_store):
    output = _diff(trace_store, _run(0, TRANSPILED_AT_LEVEL_0), _run(3, TRANSPILED_AT_LEVEL_3))

    assert _row(output, "Circuit compared")[1:] == ["transpiled", "transpiled", "✓"]
    text = " ".join(output.split())
    assert "Circuit rows compare the transpiled circuit each trace executed, not the circuit as submitted." in text


def test_the_source_circuit_is_still_shown_as_the_same(trace_store):
    """Same source, different execution: both facts are on the page."""
    output = _diff(trace_store, _run(0, TRANSPILED_AT_LEVEL_0), _run(3, TRANSPILED_AT_LEVEL_3))

    assert _row(output, "Source circuit hash")[1:3] == [SOURCE.hash, SOURCE.hash]
    assert _matches(output, "Source circuit hash")
    assert "transpilation produced different executed circuits" in " ".join(output.split())


def test_identical_executed_circuits_still_match(trace_store):
    output = _diff(trace_store, _run(3, TRANSPILED_AT_LEVEL_3), _run(3, TRANSPILED_AT_LEVEL_3))

    for prop in ("Circuit compared", "Circuit qubits", "Circuit depth", "Circuit gates", "Circuit hash"):
        assert _matches(output, prop), prop
    assert "transpilation produced different executed circuits" not in " ".join(output.split())


def test_without_a_transpiled_circuit_diff_says_it_compared_the_submitted_one(trace_store):
    output = _diff(trace_store, _run(None, None), _run(None, None))

    assert _row(output, "Circuit compared")[1:] == ["as submitted", "as submitted", "✓"]
    assert _row(output, "Circuit hash")[1:3] == [SOURCE.hash, SOURCE.hash]
    text = " ".join(output.split())
    assert "Circuit rows compare the circuit as submitted. Neither trace recorded a transpiled circuit." in text


def test_a_mixed_pair_names_which_trace_was_compared_how(trace_store):
    transpiled, submitted = _run(3, TRANSPILED_AT_LEVEL_3), _run(None, None)
    output = _diff(trace_store, submitted, transpiled)

    assert _row(output, "Circuit compared")[1:] == ["as submitted", "transpiled", "✗"]
    text = " ".join(output.split())
    assert (
        f"Circuit rows compare the transpiled circuit of {transpiled.id} with the circuit as submitted "
        f"of {submitted.id}, which recorded no transpiled circuit."
    ) in text
