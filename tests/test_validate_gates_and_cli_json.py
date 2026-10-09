"""
Tests for using validate, score and list from a script or CI step.

validate printed FAIL and exited 0, so nothing could gate on it. The fix text
it printed for a missing QASM called QuantumCircuit.qasm(), which Qiskit 1.0
removed, and assigned to a field of a frozen model, so following it raised.
And none of validate, score or list had a --json mode, so the only way to read
them from a program was to parse box-drawn, wrapped console output.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from qbom.analysis import compute_score, validate_trace
from qbom.cli.main import main
from qbom.core.models import (
    Circuit,
    Counts,
    Environment,
    Execution,
    GateCounts,
    Hardware,
    Package,
    Result,
)
from qbom.core.session import Session
from qbom.core.trace import Metadata, Trace

BELL_QASM = 'OPENQASM 2.0;\ninclude "qelib1.inc";\nqreg q[2];\ncreg c[2];\nh q[0];\ncx q[0],q[1];\n'


@pytest.fixture
def trace_store(tmp_path, monkeypatch):
    """
    An empty trace store at the path the printed fix text writes to.

    HOME points at the temporary directory, so Path.home() in the fix text
    lands in this store and not in the real one.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    store = tmp_path / ".qbom" / "traces"
    store.mkdir(parents=True)
    session = Session.get()
    monkeypatch.setattr(session, "_storage_path", store)
    # list also returns traces held in memory, which other tests may have left.
    monkeypatch.setattr(session, "_traces", [])
    return store


def save(store: Path, trace: Trace) -> Trace:
    (store / f"{trace.id}.json").write_text(trace.to_json())
    return trace


def complete_trace(trace_id: str = "qbom_c0391e7e", *, qasm: str | None = BELL_QASM, result: bool = True) -> Trace:
    """A simulator run with every section validation asks for."""
    outcome = Result(counts=Counts(raw={"00": 512, "11": 512}, shots=1024), hash="deadbeefdeadbeef")
    return Trace(
        id=trace_id,
        environment=Environment(
            python="3.11.5",
            platform="Darwin-arm64",
            packages=[
                Package(name="qiskit", version="2.5.2"),
                Package(name="numpy", version="2.1.0"),
                Package(name="rich", version="13.9.4"),
            ],
        ),
        circuits=[
            Circuit(
                name="bell",
                num_qubits=2,
                num_clbits=2,
                depth=3,
                gates=GateCounts(single_qubit=1, two_qubit=1, total=4, by_name={"h": 1, "cx": 1, "measure": 2}),
                hash="a1b2c3d4e5f60718",
                qasm=qasm,
            )
        ],
        hardware=Hardware(provider="Aer", backend="aer_simulator", is_simulator=True, qubits_used=[0, 1]),
        execution=Execution(job_id="job-1", shots=1024),
        result=outcome if result else None,
        metadata=Metadata(name="bell-state", description="Two qubit Bell state"),
    )


def failing_trace(trace_id: str = "qbom_fa11ed00") -> Trace:
    """No circuit, hardware or environment: validation reports errors."""
    return Trace(id=trace_id)


# ---------------------------------------------------------------------------
# Exit status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("extra", [[], ["--publication"], ["--json"]], ids=["standard", "publication", "json"])
def test_a_fail_verdict_exits_non_zero(trace_store, extra):
    trace = save(trace_store, failing_trace())

    result = CliRunner().invoke(main, ["validate", trace.id, *extra])

    assert result.exit_code == 1, result.output
    assert "FAIL" in result.output


@pytest.mark.parametrize(
    "trace,extra,verdict",
    [
        (complete_trace(), [], "PASS"),
        (complete_trace(result=False), [], "WARNINGS"),
        (complete_trace(qasm=None), ["--publication"], "WARNINGS"),
    ],
    ids=["pass", "warnings", "publication-warnings"],
)
def test_pass_and_warnings_exit_zero(trace_store, trace, extra, verdict):
    """
    The complementary case.

    A command that exited 1 unconditionally would pass the test above.
    """
    save(trace_store, trace)

    result = CliRunner().invoke(main, ["validate", trace.id, *extra])

    assert result.exit_code == 0, result.output
    assert verdict in result.output


# ---------------------------------------------------------------------------
# The printed fix text runs
# ---------------------------------------------------------------------------


def printed_fix_code(output: str, marker: str) -> str:
    """The code a reader would copy from the Fix line printed under `marker`."""
    lines = output.splitlines()
    start = next(i for i, line in enumerate(lines) if marker in line)
    fix_line = lines[start + 1]
    assert fix_line.strip().startswith("Fix:"), fix_line
    match = re.search(r"`([^`]+)`", fix_line)
    assert match, f"no code in the printed fix text: {fix_line}"
    return match.group(1)


@pytest.mark.parametrize(
    "extra,marker",
    [
        ([], "No QASM or JSON representation stored"),
        (["--publication"], "No circuit representation for exact reproduction"),
    ],
    ids=["standard", "publication"],
)
def test_the_printed_qasm_fix_runs_and_clears_the_finding(trace_store, extra, marker):
    """
    Copy the code from the printed fix text, run it, and validate again.

    Runs against the Qiskit the `qiskit` extra installs. The code is read from
    the command's output rather than from the source, so wrapping or markup
    that mangled it on the way to the terminal would fail here too.
    """
    pytest.importorskip("qiskit")
    from qiskit import QuantumCircuit, qasm2

    circuit = QuantumCircuit(2, 2)
    circuit.h(0)
    circuit.cx(0, 1)
    circuit.measure([0, 1], [0, 1])

    trace = save(trace_store, complete_trace(qasm=None))
    before = CliRunner().invoke(main, ["validate", trace.id, *extra])
    assert marker in before.output

    code = printed_fix_code(before.output, marker)
    exec(code, {"trace": trace, "circuit": circuit})

    stored = Trace.model_validate_json((trace_store / f"{trace.id}.json").read_text())
    rebuilt = QuantumCircuit.from_qasm_str(stored.circuits[0].qasm)
    assert qasm2.dumps(rebuilt) == qasm2.dumps(circuit)
    # The copy is the same experiment: same id, same content hash.
    assert stored.id == trace.id
    assert stored.content_hash == trace.content_hash

    after = CliRunner().invoke(main, ["validate", trace.id, *extra])
    assert after.exit_code == 0, after.output
    assert marker not in after.output


# ---------------------------------------------------------------------------
# --json
# ---------------------------------------------------------------------------


def test_validate_json_reports_the_verdict_and_every_issue(trace_store):
    trace = save(trace_store, failing_trace())
    expected = validate_trace(trace)

    result = CliRunner().invoke(main, ["validate", trace.id, "--json"])
    report = json.loads(result.stdout)

    assert result.exit_code == 1
    assert report["traceId"] == trace.id
    assert report["mode"] == "standard"
    assert report["verdict"] == "FAIL"
    assert report["isValid"] is False
    assert report["errorCount"] == expected.error_count
    assert report["warningCount"] == expected.warning_count
    assert report["infoCount"] == expected.info_count
    assert [issue["message"] for issue in report["issues"]] == [issue.message for issue in expected.issues]
    assert all(set(issue) == {"level", "category", "message", "fix"} for issue in report["issues"])
    assert {issue["level"] for issue in report["issues"]} <= {"error", "warning", "info"}


def test_validate_json_on_a_passing_trace(trace_store):
    trace = save(trace_store, complete_trace())

    result = CliRunner().invoke(main, ["validate", trace.id, "--json", "--publication"])
    report = json.loads(result.stdout)

    assert result.exit_code == 0, result.output
    assert report["verdict"] == "PASS"
    assert report["mode"] == "publication"
    assert report["isComplete"] is True


def test_score_json_matches_the_computed_score(trace_store):
    trace = save(trace_store, complete_trace())
    expected = compute_score(trace)

    result = CliRunner().invoke(main, ["score", trace.id, "--json"])
    report = json.loads(result.stdout)

    assert result.exit_code == 0, result.output
    assert report["traceId"] == trace.id
    assert report["totalScore"] == expected.total_score
    assert report["maxScore"] == expected.max_score
    assert report["grade"] == expected.grade
    assert [c["name"] for c in report["components"]] == [c.name for c in expected.components]
    assert sum(c["earnedPoints"] for c in report["components"]) == expected.total_score
    assert report["recommendations"] == expected.recommendations


def test_list_json_lists_every_trace(trace_store):
    save(trace_store, complete_trace("qbom_11111111"))
    save(trace_store, failing_trace("qbom_22222222"))

    result = CliRunner().invoke(main, ["list", "--json"])
    listed = {entry["id"]: entry for entry in json.loads(result.stdout)}

    assert result.exit_code == 0, result.output
    assert set(listed) == {"qbom_11111111", "qbom_22222222"}
    assert listed["qbom_11111111"]["backend"] == "aer_simulator"
    assert listed["qbom_11111111"]["shots"] == 1024
    assert listed["qbom_11111111"]["numQubits"] == 2
    assert listed["qbom_22222222"]["backend"] is None
    # The timestamp says which zone it is in.
    assert listed["qbom_11111111"]["createdAt"].endswith("+00:00")


def test_list_json_with_no_traces_is_an_empty_array(trace_store):
    """Not the human "No traces found" sentence, which would not parse."""
    result = CliRunner().invoke(main, ["list", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == []
