"""
Tests that the software environment and the metadata are inside the content hash.

The content hash used to cover the circuits, the transpilation, the backend,
the qubits used, the shots, the seed and the result hash, and nothing else. A
trace whose Python version and package versions had been rewritten verified
clean, and the forged versions flowed into the CycloneDX and SPDX exports
beside the unchanged hash. The environment is the part of the record a
reproduction depends on most, so the bill of materials the tool is named for
was the one section `qbom verify` could not vouch for.

Traces now record format 1.1, whose hash covers both sections. Traces written
in format 1.0 carry hashes taken without them, so each trace is checked against
the content its own recorded format hashed. The fixture below is a trace a
qbom 0.1.x capture wrote to disk from a real Qiskit run, unedited.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from qbom.cli.main import main
from qbom.core.hashing import result_hash
from qbom.core.models import (
    Circuit,
    Counts,
    Environment,
    Execution,
    GateCounts,
    Hardware,
    Package,
    Result,
    Transpilation,
)
from qbom.core.timeutil import utc_now
from qbom.core.trace import HASHED_CONTENT, TRACE_FORMAT, Metadata, Trace
from qbom.core.verification import CONTENT_HASH, FAILED, PASSED, verify_document

LEGACY_FIXTURE = Path(__file__).parent / "fixtures" / "trace_written_by_0_1_x.json"

COUNTS = {"00": 2022, "11": 2074}


def _new_trace() -> Trace:
    """A trace carrying every environment and metadata field, as this release writes it."""
    submitted_at = utc_now()
    return Trace(
        environment=Environment(
            python="3.12.4",
            platform="macOS-15.1-arm64-arm-64bit",
            packages=[
                Package(name="qiskit", version="1.2.4", purl="pkg:pypi/qiskit@1.2.4"),
                Package(name="numpy", version="2.1.2", purl="pkg:pypi/numpy@2.1.2"),
            ],
        ),
        circuits=[
            Circuit(
                name="bell",
                num_qubits=2,
                num_clbits=2,
                depth=3,
                gates=GateCounts(single_qubit=1, two_qubit=1, total=4),
                hash="4a4f5f6c1d2e3b7a",
            )
        ],
        transpilation=Transpilation(optimization_level=2, seed=7),
        hardware=Hardware(provider="Aer (Local)", backend="aer_simulator", num_qubits=32, is_simulator=True),
        execution=Execution(shots=4096, submitted_at=submitted_at, completed_at=submitted_at),
        result=Result(counts=Counts(raw=COUNTS, shots=4096), hash=result_hash(COUNTS)),
        metadata=Metadata(
            name="bell-state",
            description="Bell state on the local simulator",
            tags=["bell", "demo"],
            authors=["A. Researcher"],
            paper="https://doi.org/10.0000/example",
            experiment_id="exp-001",
        ),
    )


def _content_check(document: dict[str, Any]):
    report = verify_document(json.dumps(document))
    return report, next(check for check in report.checks if check.name == CONTENT_HASH)


def _set_package_field(field: str, value: str) -> Callable[[dict], None]:
    def edit(document: dict) -> None:
        document["environment"]["packages"][0][field] = value

    return edit


def _set(section: str, field: str, value: Any) -> Callable[[dict], None]:
    def edit(document: dict) -> None:
        document[section][field] = value

    return edit


ENVIRONMENT_EDITS = {
    "python version": _set("environment", "python", "2.7.18"),
    "platform": _set("environment", "platform", "Linux-5.15-x86_64"),
    "capture time": _set("environment", "timestamp", "2020-01-01T00:00:00Z"),
    "package version": _set_package_field("version", "0.19.0"),
    "package name": _set_package_field("name", "qiskit-terra"),
    "package purl": _set_package_field("purl", "pkg:pypi/qiskit@0.19.0"),
    "package added": lambda d: d["environment"]["packages"].append(
        {"name": "scipy", "version": "1.14.1", "purl": "pkg:pypi/scipy@1.14.1"}
    ),
    "package removed": lambda d: d["environment"]["packages"].pop(),
    "environment removed": lambda d: d.pop("environment"),
}

METADATA_EDITS = {
    "name": _set("metadata", "name", "another-experiment"),
    "description": _set("metadata", "description", "Something else"),
    "tags": _set("metadata", "tags", ["bell"]),
    "authors": _set("metadata", "authors", ["Someone Else"]),
    "paper": _set("metadata", "paper", "https://doi.org/10.0000/other"),
    "experiment id": _set("metadata", "experiment_id", "exp-999"),
    "metadata removed": lambda d: d.pop("metadata"),
}


# ============================================================================
# A trace this release writes
# ============================================================================


def test_a_new_trace_records_the_format_that_hashes_the_environment_and_metadata():
    trace = _new_trace()

    assert trace.qbom_version == TRACE_FORMAT
    assert json.loads(trace.to_json())["qbom_version"] == TRACE_FORMAT
    assert "environment" in HASHED_CONTENT[TRACE_FORMAT]
    assert "metadata" in HASHED_CONTENT[TRACE_FORMAT]


def test_a_new_trace_verifies_clean_after_a_round_trip_through_disk():
    document = json.loads(_new_trace().to_json())

    report, check = _content_check(document)

    assert check.status == PASSED, check.detail
    assert check.detail == f"matches, {document['content_hash']}"
    assert report.ok, [c.detail for c in report.failures]


@pytest.mark.parametrize("edit", ENVIRONMENT_EDITS.values(), ids=ENVIRONMENT_EDITS.keys())
def test_editing_the_environment_of_a_new_trace_fails_verification(edit):
    original = json.loads(_new_trace().to_json())
    document = copy.deepcopy(original)
    edit(document)
    assert document != original, "premise: the edit must change the document"

    report, check = _content_check(document)

    assert check.status == FAILED, f"an edited environment verified clean: {check.detail}"
    assert not report.ok


@pytest.mark.parametrize("edit", METADATA_EDITS.values(), ids=METADATA_EDITS.keys())
def test_editing_the_metadata_of_a_new_trace_fails_verification(edit):
    original = json.loads(_new_trace().to_json())
    document = copy.deepcopy(original)
    edit(document)
    assert document != original, "premise: the edit must change the document"

    report, check = _content_check(document)

    assert check.status == FAILED, f"edited metadata verified clean: {check.detail}"
    assert not report.ok


def test_the_forged_package_list_from_the_report_fails_on_the_command_line(tmp_path):
    """The reproduction from the report, end to end: exit 1, and the content hash named."""
    document = json.loads(_new_trace().to_json())
    document["environment"]["python"] = "2.7.18"
    document["environment"]["packages"][0]["version"] = "0.19.0"
    path = tmp_path / "forged.qbom.json"
    path.write_text(json.dumps(document))

    result = CliRunner().invoke(main, ["verify", str(path)])
    output = " ".join(result.output.split())

    assert result.exit_code == 1, output
    assert f"verification failed ({CONTENT_HASH})" in output


def test_relabelling_a_new_trace_as_format_1_0_does_not_put_the_environment_back_outside():
    """The format is read from the file, so the downgrade has to be an edit the hash catches."""
    document = json.loads(_new_trace().to_json())
    document["qbom_version"] = "1.0"
    document["environment"]["packages"][0]["version"] = "0.19.0"

    _, check = _content_check(document)

    assert check.status == FAILED, check.detail


def test_a_trace_format_this_release_does_not_know_fails_rather_than_skipping_the_check():
    """
    Otherwise a format number would stand in for the check.

    Changing the format to one the reader cannot hash would leave the hash
    uncompared, and a forged environment would pass beside it.
    """
    document = json.loads(_new_trace().to_json())
    document["qbom_version"] = "9.9"
    document["environment"]["python"] = "2.7.18"

    report, check = _content_check(document)

    assert check.status == FAILED
    assert "trace format 9.9" in check.detail
    assert not report.ok


# ============================================================================
# A trace written in format 1.0, by qbom 0.1.x
# ============================================================================


def test_the_fixture_is_an_unedited_format_1_0_trace():
    """Guard the tests below: they are only meaningful on a 1.0 trace with an environment."""
    raw = json.loads(LEGACY_FIXTURE.read_text())

    assert raw["qbom_version"] == "1.0"
    assert raw["environment"]["packages"], "premise: the fixture records a package list"
    assert raw["content_hash"] == "fce1733fa9b3355d"


def test_a_trace_written_by_0_1_x_still_verifies():
    report, check = _content_check(json.loads(LEGACY_FIXTURE.read_text()))

    assert check.status == PASSED, check.detail
    assert report.ok, [c.detail for c in report.failures]


def test_a_trace_written_by_0_1_x_says_its_environment_and_metadata_are_not_checked():
    """A clean result on a 1.0 trace must not imply the environment was checked."""
    _, check = _content_check(json.loads(LEGACY_FIXTURE.read_text()))

    assert "hashed without the environment and the metadata" in check.detail
    assert "not checked" in check.detail


def test_a_trace_written_by_0_1_x_still_fails_when_what_it_hashed_is_edited():
    """The 1.0 shape is a fixed second form, not a way around the check."""
    document = json.loads(LEGACY_FIXTURE.read_text())
    assert document["execution"]["shots"] != 1, "premise: the edit must change the value"
    document["execution"]["shots"] = 1

    report, check = _content_check(document)

    assert check.status == FAILED, check.detail
    assert not report.ok


def test_a_trace_written_by_0_1_x_verifies_on_the_command_line():
    result = CliRunner().invoke(main, ["verify", str(LEGACY_FIXTURE)])
    output = " ".join(result.output.split())

    assert result.exit_code == 0, output
    assert "Format 1.0 traces were hashed without the environment and the metadata" in output
