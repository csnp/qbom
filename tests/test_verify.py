"""
Tests for what `qbom verify` establishes.

Verification used to append a literal True for each of four checks and then
print "VERDICT: QBOM appears authentic and complete" when all four were True,
which they always were. A trace whose measurement counts had been replaced
passed. So did `{}` and `{"hello": "world"}`, neither of which is a trace, and
every one of them exited 0, so no CI step could tell a forgery from a real
record.

The two hashes a trace carries cover different things and neither substitutes
for the other, so both cases below are tested against the same file:

- rewriting only the counts does not move the content hash, because the
  content hash covers `result.hash` and not the counts. Only recomputing the
  result hash catches it.
- rewriting the shot count does not move the result hash. Only recomputing the
  content hash catches it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from qbom.adapters import cirq as cirq_adapter
from qbom.adapters import pennylane as pennylane_adapter
from qbom.adapters import qiskit as qiskit_adapter
from qbom.cli.main import main
from qbom.core.hashing import result_hash
from qbom.core.models import (
    Circuit,
    Counts,
    Execution,
    GateCounts,
    Hardware,
    Result,
    Transpilation,
)
from qbom.core.timeutil import utc_now
from qbom.core.trace import Trace, TraceBuilder

# Counts, and the result hash recorded beside them, taken from a Bell state
# trace written to disk by the capture code. The hash is a literal here rather
# than a call to result_hash, so these tests pin the expression instead of
# restating it: a change to the way results are hashed makes traces already on
# disk unverifiable, and has to fail here.
RECORDED_COUNTS = {"11": 2074, "00": 2022}
RECORDED_RESULT_HASH = "2326158e16888826"

# What those counts become when they are replaced with a clean sweep, and the
# hash that replacement actually has.
FORGED_COUNTS = {"00": 4096}
FORGED_RESULT_HASH = "dc0603dc165dd60e"


def _legitimate_trace() -> Trace:
    """A trace built the way an adapter builds one, with consistent hashes."""
    submitted_at = utc_now()

    return (
        TraceBuilder()
        .add_circuit(
            Circuit(
                name="bell",
                num_qubits=2,
                num_clbits=2,
                depth=3,
                gates=GateCounts(single_qubit=1, two_qubit=1, total=4),
                hash="4a4f5f6c1d2e3b7a",
            )
        )
        .set_transpilation(Transpilation(optimization_level=2))
        .set_hardware(
            Hardware(
                provider="Aer (Local)",
                backend="aer_simulator",
                num_qubits=32,
                is_simulator=True,
            )
        )
        .set_execution(
            Execution(
                job_id="a-job-id",
                shots=4096,
                submitted_at=submitted_at,
                completed_at=submitted_at,
            )
        )
        .set_result(
            Result(
                counts=Counts(raw=RECORDED_COUNTS, shots=4096),
                hash=RECORDED_RESULT_HASH,
            )
        )
        .build()
    )


def _write(path: Path, document: object) -> Path:
    path.write_text(json.dumps(document, indent=2))
    return path


@pytest.fixture
def legitimate_file(tmp_path) -> Path:
    """A trace on disk exactly as the exporter writes one."""
    path = tmp_path / "legitimate.qbom.json"
    path.write_text(_legitimate_trace().to_json())
    return path


def _tampered(legitimate_file: Path, edit) -> Path:
    """The legitimate file with one edit applied and every hash left alone."""
    document = json.loads(legitimate_file.read_text())
    edit(document)
    return _write(legitimate_file.parent / "tampered.qbom.json", document)


def verify(path: Path) -> tuple[int, str]:
    """Run `qbom verify`, with the output unwrapped so it can be searched."""
    result = CliRunner().invoke(main, ["verify", str(path)])
    if result.exception is not None and not isinstance(result.exception, SystemExit):
        raise result.exception
    return result.exit_code, " ".join(result.output.split())


# ============================================================================
# The hash function capture and verification share
# ============================================================================


def test_result_hash_reproduces_a_hash_recorded_on_disk():
    """
    The pin on the expression itself.

    The literal is what a real capture wrote next to these counts. Verification
    recomputes the hash of a trace it did not write, so the two have to agree
    byte for byte or every trace already on disk fails verification.
    """
    assert result_hash(RECORDED_COUNTS) == RECORDED_RESULT_HASH


def test_forged_counts_hash_to_something_else():
    """The premise of the forgery test below: the replacement is detectable."""
    assert result_hash(FORGED_COUNTS) == FORGED_RESULT_HASH
    assert FORGED_RESULT_HASH != RECORDED_RESULT_HASH


def test_result_hash_is_insensitive_to_the_order_counts_arrive_in():
    """A dict built in a different order is the same measurement."""
    reversed_order = dict(reversed(list(RECORDED_COUNTS.items())))

    assert list(reversed_order) != list(RECORDED_COUNTS), "premise: the insertion order differs"
    assert result_hash(reversed_order) == RECORDED_RESULT_HASH


@pytest.mark.parametrize(
    "adapter",
    [qiskit_adapter, cirq_adapter, pennylane_adapter],
    ids=lambda module: module.__name__.rsplit(".", 1)[-1],
)
def test_every_adapter_hashes_results_with_the_shared_function(adapter):
    """
    One expression, not one per adapter.

    Each adapter used to carry its own copy. Three copies of the expression a
    verifier has to reproduce are three chances of drift.
    """
    assert adapter.result_hash is result_hash


# ============================================================================
# A real trace
# ============================================================================


def test_a_legitimate_trace_verifies_clean(legitimate_file):
    exit_code, output = verify(legitimate_file)

    assert exit_code == 0, output
    assert "every hash this file records matches" in output
    assert "Content hash against trace content: matches" in output
    assert f"Result hash against recorded counts: matches, {RECORDED_RESULT_HASH}" in output


def test_a_legitimate_trace_reports_no_failed_check(legitimate_file):
    from qbom.core.verification import verify_file

    report = verify_file(legitimate_file)

    assert report.ok
    assert report.failures == ()


# ============================================================================
# Tampering
# ============================================================================


def test_rewritten_counts_are_caught_by_the_result_hash(legitimate_file):
    """
    The forgery the old verify passed: real counts replaced, hashes untouched.
    """
    forged = _tampered(legitimate_file, lambda d: d["result"]["counts"].update({"raw": FORGED_COUNTS}))

    exit_code, output = verify(forged)

    assert exit_code != 0, f"a forged trace reported success:\n{output}"
    assert "verification failed" in output
    assert "Result hash against recorded counts" in output
    assert RECORDED_RESULT_HASH in output and FORGED_RESULT_HASH in output


def test_rewritten_counts_do_not_move_the_content_hash(legitimate_file):
    """
    Why the result hash check cannot be dropped.

    The content hash covers `result.hash`, not the counts, so it still matches
    on the forged file. If this ever fails, the content hash has started
    covering the counts and this test should be re-derived, not deleted.
    """
    forged = _tampered(legitimate_file, lambda d: d["result"]["counts"].update({"raw": FORGED_COUNTS}))

    _, output = verify(forged)

    assert "Content hash against trace content: matches" in output


def test_an_altered_shot_count_is_caught_by_the_content_hash(legitimate_file):
    tampered = _tampered(legitimate_file, lambda d: d["execution"].update({"shots": 999999}))

    exit_code, output = verify(tampered)

    assert exit_code != 0, f"an edited shot count reported success:\n{output}"
    assert "Content hash against trace content" in output
    assert "verification failed" in output


def test_an_altered_shot_count_does_not_move_the_result_hash(legitimate_file):
    """The mirror of the case above: neither check substitutes for the other."""
    tampered = _tampered(legitimate_file, lambda d: d["execution"].update({"shots": 999999}))

    _, output = verify(tampered)

    assert "Result hash against recorded counts: matches" in output


def test_an_altered_backend_name_is_caught(legitimate_file):
    tampered = _tampered(legitimate_file, lambda d: d["hardware"].update({"backend": "ibm_torino"}))

    exit_code, output = verify(tampered)

    assert exit_code != 0, output
    assert "Content hash against trace content" in output


def test_a_file_carrying_no_content_hash_fails(legitimate_file):
    """
    Deleting the field must not be a way past the check.

    An absent content hash is indistinguishable from a removed one, and every
    trace QBOM writes carries it, so there is nothing to fall back to.
    """
    stripped = _tampered(legitimate_file, lambda d: d.pop("content_hash"))

    exit_code, output = verify(stripped)

    assert exit_code != 0, output
    assert "records no content hash" in output


def test_timestamps_that_run_backwards_fail(legitimate_file):
    def reverse_time(document):
        document["execution"]["submitted_at"] = "2030-01-01T00:00:00+00:00"
        document["execution"]["completed_at"] = "2020-01-01T00:00:00+00:00"

    tampered = _tampered(legitimate_file, reverse_time)

    exit_code, output = verify(tampered)

    assert exit_code != 0, output
    assert "completed_at is before submitted_at" in output


# ============================================================================
# Documents that are not traces
# ============================================================================


@pytest.mark.parametrize(
    "document",
    [{}, {"hello": "world"}, {"id": "qbom_1234"}, {"qbom_version": "1.0"}, [], "a string"],
    ids=["empty-object", "unrelated-object", "id-only", "version-only", "array", "string"],
)
def test_a_document_that_is_not_a_trace_is_rejected(tmp_path, document):
    """
    Every field on Trace has a default, so `{}` parses into a Trace and a model
    parse establishes nothing. The check is against the raw JSON.
    """
    path = _write(tmp_path / "not-a-trace.json", document)

    exit_code, output = verify(path)

    assert exit_code != 0, f"a document that is not a QBOM trace reported success:\n{output}"
    assert "verification failed" in output


def test_a_file_that_is_not_json_is_rejected(tmp_path):
    path = tmp_path / "truncated.qbom.json"
    path.write_text('{"qbom_version": "1.0", "id": "qbom_1234"')

    exit_code, output = verify(path)

    assert exit_code != 0, output


def test_a_missing_file_is_rejected(tmp_path):
    exit_code, _ = verify(tmp_path / "absent.qbom.json")

    assert exit_code != 0


# ============================================================================
# What verification cannot establish, stated rather than claimed
# ============================================================================


def test_a_result_that_is_not_counts_is_not_reported_as_verified(tmp_path):
    """
    PennyLane hashes an expectation value over the value itself, which the
    trace does not store. That hash cannot be recomputed here, and saying so is
    the honest outcome. Reporting it as checked would be the old defect in a
    new place.
    """
    trace = (
        TraceBuilder()
        .set_execution(Execution(shots=1000, submitted_at=utc_now(), completed_at=utc_now()))
        .set_result(
            Result(
                counts=Counts(raw={}, shots=1000),
                hash="cadef9fdccdb952f",
                metadata={"type": "expectation_value", "value": "0.7568359375"},
            )
        )
        .build()
    )
    path = tmp_path / "expectation.qbom.json"
    path.write_text(trace.to_json())

    exit_code, output = verify(path)

    assert exit_code == 0, output
    assert "Result hash against recorded counts: matches" not in output
    assert "cannot be recomputed" in output


def test_an_unchecked_entry_is_not_shown_as_a_pass(tmp_path):
    """A check that could not run must not read like one that passed."""
    from qbom.core.verification import PASSED, RESULT_HASH, verify_file

    trace = TraceBuilder().set_execution(Execution(shots=100, completed_at=utc_now())).build()
    path = tmp_path / "no-result.qbom.json"
    path.write_text(trace.to_json())

    report = verify_file(path)
    result_check = next(check for check in report.checks if check.name == RESULT_HASH)

    assert result_check.status != PASSED
    assert report.ok, "a check that could not run is not a failure either"


def test_a_trace_stripped_of_its_identity_is_rejected_even_though_its_hashes_match(tmp_path):
    """
    The structural check has to be tested on a document the OTHER checks accept.

    Removing `qbom_version` and `id` leaves every hash intact, because
    `Trace.content_hash` covers circuits, transpilation, hardware, execution and
    the result hash, and neither identity key is among them. So this document
    passes the content-hash and result-hash checks and is rejected only by the
    structural check.

    The six non-trace documents above cannot establish that: each is rejected by
    the content-hash check as well, so they stay red even with the structural
    check removed entirely.
    """
    document = json.loads(_legitimate_trace().to_json())
    del document["qbom_version"]
    del document["id"]
    path = _write(tmp_path / "anonymous.qbom.json", document)

    exit_code, output = verify(path)

    assert exit_code != 0, f"a document with no QBOM identity was accepted:\n{output}"
    assert "not a QBOM trace" in output


def test_the_identity_check_is_what_rejects_it_and_the_hash_checks_still_agree(tmp_path):
    """
    Guard the test above: it is only meaningful while the hashes really do match.

    If a future change brought `id` or `qbom_version` inside the content hash,
    the test above would still pass, but for the wrong reason, and the
    structural check would go untested again without anything saying so.
    """
    from qbom.core.trace import Trace

    document = json.loads(_legitimate_trace().to_json())
    stored_content_hash = document["content_hash"]
    del document["qbom_version"]
    del document["id"]

    trace = Trace.model_validate(document)

    assert trace.content_hash == stored_content_hash, (
        "removing the identity keys changed the content hash, so the test above "
        "is no longer isolating the structural check"
    )
    assert result_hash(trace.result.counts.raw) == trace.result.hash


def test_a_result_hash_that_cannot_be_recomputed_is_not_reported_as_a_match(tmp_path):
    """
    The honesty limit, pinned at the level a reader sees.

    A pennylane expectation value carries a hash taken over the result object,
    which the trace does not store. Reporting that as verified would claim an
    integrity guarantee that was never checked.
    """
    from qbom.core.verification import PASSED, RESULT_HASH, UNCHECKED, verify_file

    trace = (
        TraceBuilder()
        .set_execution(Execution(shots=1000, completed_at=utc_now()))
        .set_result(Result(counts=Counts(raw={}, shots=1000), hash="a1b2c3d4e5f60718"))
        .build()
    )
    path = tmp_path / "expectation.qbom.json"
    path.write_text(trace.to_json())

    report = verify_file(path)
    check = next(c for c in report.checks if c.name == RESULT_HASH)

    assert check.status == UNCHECKED
    assert check.status != PASSED

    exit_code, output = verify(path)
    assert exit_code == 0, output
    assert "cannot be recomputed" in output
    assert f"matches, {trace.result.hash}" not in output


def test_a_clean_verdict_says_when_something_could_not_be_checked(tmp_path):
    """
    A verdict that cannot distinguish "checked and matched" from "could not be
    checked" is the same false assurance this whole command was fixed for.
    """
    trace = (
        TraceBuilder()
        .set_execution(Execution(shots=1000, completed_at=utc_now()))
        .set_result(Result(counts=Counts(raw={}, shots=1000), hash="a1b2c3d4e5f60718"))
        .build()
    )
    path = tmp_path / "partial.qbom.json"
    path.write_text(trace.to_json())

    exit_code, output = verify(path)

    assert exit_code == 0, output
    assert "not established" in output, "a clean verdict carrying an unchecked entry must say so:\n" + output


def test_the_result_hash_comparison_is_over_the_whole_digest(tmp_path):
    """
    A prefix comparison would accept a forgery that happens to share a few
    leading hex characters. Pin the full digest by forging counts whose hash
    collides with the recorded one on its first characters.
    """
    from qbom.core.verification import FAILED, RESULT_HASH, verify_file

    recorded = RECORDED_RESULT_HASH
    collision = None
    for n in range(200000):
        candidate = {"00": n}
        if result_hash(candidate)[:1] == recorded[:1] and result_hash(candidate) != recorded:
            collision = candidate
            break

    assert collision is not None, "no shared-prefix counts found to build the case on"

    document = json.loads(_legitimate_trace().to_json())
    document["result"]["counts"]["raw"] = collision
    document["result"]["counts"]["shots"] = sum(collision.values())
    path = _write(tmp_path / "prefix-collision.qbom.json", document)

    report = verify_file(path)
    check = next(c for c in report.checks if c.name == RESULT_HASH)

    assert check.status == FAILED, (
        f"counts hashing to {result_hash(collision)} were accepted against "
        f"recorded {recorded}, so the comparison is not over the whole digest"
    )
