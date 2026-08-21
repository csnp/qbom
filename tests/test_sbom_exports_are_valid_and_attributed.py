"""The SBOM exports validate against the standards they claim, and say what made them.

Two defects sat behind these tests.

The exports named the wrong producer. `creationInfo.creators` read
`Tool: qbom-1.0` and the CycloneDX property `qbom:version` read `1.0`, because
both took `Trace.qbom_version`, which is the version of the trace FORMAT. The
version of the tool is the version of the package. So every provenance document
QBOM wrote attributed itself to a release that does not exist.

And the CycloneDX document failed the schema it declares in its own `$schema`
field: a root `extensions` key the 1.5 schema forbids, a `serialNumber` that was
not a UUID, and `metadata.component.description` set to null on any trace with
no description.

The schemas are the official ones, vendored under `tests/schemas/` so these
tests need no network. The CycloneDX schema refers to the JSON Signature Format
schema, which is vendored alongside it and resolved from disk.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft7Validator
from referencing import Registry, Resource

import qbom
from qbom.core.models import (
    Calibration,
    Circuit,
    Counts,
    Environment,
    Execution,
    GateCounts,
    GateProperties,
    Hardware,
    Package,
    QubitProperties,
    Result,
    Transpilation,
)
from qbom.core.timeutil import utc_now
from qbom.core.trace import Metadata, Trace

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
CYCLONEDX_SCHEMA = "cyclonedx-bom-1.5.schema.json"
SPDX_SCHEMA = "spdx-2.3.schema.json"
JSF_SCHEMA = "cyclonedx-jsf-0.82.schema.json"


# ============================================================================
# Schema validation against the vendored official schemas
# ============================================================================


def _registry() -> Registry:
    """Every vendored schema, keyed by the `$id` it declares.

    `cyclonedx-bom-1.5.schema.json` refers to `jsf-0.82.schema.json#/definitions/signature`
    relative to its own `$id`. Registering each schema under its `$id` resolves
    that from the vendored copy instead of fetching it.
    """
    registry: Registry = Registry()
    for name in (CYCLONEDX_SCHEMA, JSF_SCHEMA, SPDX_SCHEMA):
        contents = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
        registry = registry.with_resource(contents["$id"], Resource.from_contents(contents))
    return registry


def schema_errors(document: dict[str, Any], schema_file: str) -> list[str]:
    """Every validation error the official schema reports, as readable lines."""
    schema = json.loads((SCHEMA_DIR / schema_file).read_text(encoding="utf-8"))
    validator = Draft7Validator(schema, registry=_registry())
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(document), key=str)
    ]


def null_paths(value: Any, path: str = "") -> list[str]:
    """Paths of every null in the document.

    The CycloneDX 1.5 schema declares no nullable field, so any null is a value
    sitting where a typed one is required.
    """
    if value is None:
        return [path or "<root>"]
    if isinstance(value, dict):
        return [p for key, item in value.items() for p in null_paths(item, f"{path}/{key}")]
    if isinstance(value, list):
        return [p for index, item in enumerate(value) for p in null_paths(item, f"{path}/{index}")]
    return []


# ============================================================================
# Traces to export
# ============================================================================


def populated_trace(trace_id: str = "qbom_906738fe") -> Trace:
    """A trace with every section captured, as a real run produces."""
    return Trace(
        id=trace_id,
        environment=Environment(
            python="3.11.5",
            platform="Darwin-arm64",
            packages=[
                Package(name="qiskit", version="1.0.2"),
                Package(name="numpy", version="1.26.4"),
            ],
        ),
        circuits=[
            Circuit(
                name="bell_state",
                num_qubits=2,
                num_clbits=2,
                depth=3,
                gates=GateCounts(single_qubit=1, two_qubit=1, total=4, by_name={"h": 1, "cx": 1, "measure": 2}),
                hash="a1b2c3d4e5f60718",
            )
        ],
        transpilation=Transpilation(optimization_level=3, basis_gates=["rz", "sx", "x", "cx"]),
        hardware=Hardware(
            provider="IBM Quantum",
            backend="ibm_brisbane",
            num_qubits=127,
            qubits_used=[12, 15],
            calibration=Calibration(
                timestamp=utc_now(),
                qubits=[QubitProperties(index=12, readout_error=0.018)],
                gates=[GateProperties(gate="cx", qubits=(12, 15), error=0.0082)],
            ),
        ),
        execution=Execution(job_id="cq8x7k2j9f", shots=4096),
        result=Result(counts=Counts(raw={"00": 2012, "11": 1993}, shots=4096), hash="deadbeefdeadbeef"),
        metadata=Metadata(
            name="bell-state-experiment",
            description="Two qubit Bell state",
            authors=["A Researcher"],
            paper="https://doi.org/10.1000/example",
        ),
    )


def bare_trace(trace_id: str = "qbom_00000001") -> Trace:
    """A trace that captured nothing, which is where the null fields appeared."""
    return Trace(id=trace_id)


@pytest.fixture(params=["populated", "bare"])
def trace(request: pytest.FixtureRequest) -> Trace:
    return populated_trace() if request.param == "populated" else bare_trace()


def exported(trace: Trace, tmp_path: Path, format: str) -> dict[str, Any]:
    """Export through the public API, the way the CLI does, and read it back.

    Callers pass a distinct directory per export when they need two documents
    side by side, so create it rather than requiring every caller to remember.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = trace.export(tmp_path / f"trace.{format}.json", format=format)
    return json.loads(path.read_text(encoding="utf-8"))


# ============================================================================
# The documents are valid against the standards they declare
# ============================================================================


def test_the_cyclonedx_export_validates_against_the_official_1_5_schema(trace: Trace, tmp_path: Path) -> None:
    errors = schema_errors(exported(trace, tmp_path, "cyclonedx"), CYCLONEDX_SCHEMA)
    assert errors == []


def test_the_spdx_export_validates_against_the_official_2_3_schema(trace: Trace, tmp_path: Path) -> None:
    errors = schema_errors(exported(trace, tmp_path, "spdx"), SPDX_SCHEMA)
    assert errors == []


def test_no_field_is_exported_as_null(trace: Trace, tmp_path: Path) -> None:
    """A key with nothing to say is omitted, not emitted as null.

    `metadata.component.description` was the one that failed, on any trace with
    no description. The check covers the whole document because the next field
    added would otherwise reintroduce it unseen.
    """
    for format in ("cyclonedx", "spdx"):
        assert null_paths(exported(trace, tmp_path, format)) == [], format


# ============================================================================
# The documents say which tool produced them
# ============================================================================


def test_the_spdx_tool_creator_carries_the_package_version(trace: Trace, tmp_path: Path) -> None:
    """Asserted against `qbom.__version__`, so the next bump cannot rot it."""
    document = exported(trace, tmp_path, "spdx")
    creators = document["creationInfo"]["creators"]
    tools = [creator for creator in creators if creator.startswith("Tool:")]
    assert tools == [f"Tool: qbom-{qbom.__version__}"]


def test_the_cyclonedx_tools_record_carries_the_package_version(trace: Trace, tmp_path: Path) -> None:
    document = exported(trace, tmp_path, "cyclonedx")
    tools = document["metadata"]["tools"]["components"]
    assert [(tool["name"], tool["version"]) for tool in tools] == [("qbom", qbom.__version__)]


def test_the_trace_format_version_is_kept_apart_from_the_tool_version(trace: Trace, tmp_path: Path) -> None:
    """Both numbers are worth emitting. Neither may be read as the other.

    `qbom:version` carried the trace format version next to nothing that carried
    the tool version, so a reader had one number and two meanings for it.
    """
    document = exported(trace, tmp_path, "cyclonedx")
    properties = {item["name"]: item["value"] for item in document["metadata"]["properties"]}

    assert properties["qbom:trace-format-version"] == trace.qbom_version
    assert "qbom:version" not in properties
    assert document["metadata"]["tools"]["components"][0]["version"] == qbom.__version__


# ============================================================================
# The serial number is a UUID, and the same one for the same trace
# ============================================================================


def test_the_serial_number_is_a_stable_uuid_urn(tmp_path: Path) -> None:
    """Same trace, same serial number. Different trace, different serial number.

    A provenance document that changes identity on every export cannot be
    compared against an earlier copy of itself, which is most of what it is for.
    The pattern comes from the official schema rather than being restated here.
    """
    schema = json.loads((SCHEMA_DIR / CYCLONEDX_SCHEMA).read_text(encoding="utf-8"))
    pattern = schema["properties"]["serialNumber"]["pattern"]

    trace = populated_trace()
    first = exported(trace, tmp_path / "first", "cyclonedx")["serialNumber"]
    second = exported(trace, tmp_path / "second", "cyclonedx")["serialNumber"]
    other = exported(populated_trace("qbom_ffffffff"), tmp_path / "other", "cyclonedx")["serialNumber"]

    import re

    assert re.match(pattern, first), first
    uuid.UUID(first.removeprefix("urn:uuid:"))
    assert first == second
    assert first != other


# ============================================================================
# What ties the SBOM back to its trace
# ============================================================================


def test_the_sbom_identifies_the_trace_it_came_from(trace: Trace, tmp_path: Path) -> None:
    """The whole-trace copy is gone, so the identifiers have to survive on their own."""
    document = exported(trace, tmp_path, "cyclonedx")
    properties = {item["name"]: item["value"] for item in document["metadata"]["properties"]}

    assert properties["qbom:trace-id"] == trace.id
    assert properties["qbom:content-hash"] == trace.content_hash


def test_the_cyclonedx_export_does_not_embed_the_whole_trace(tmp_path: Path) -> None:
    """A bill of materials is not a container for the record it was made from.

    The root `extensions` key held `Trace.to_dict()` in full, including every
    captured package, every gate count and every measurement outcome. CycloneDX
    1.5 forbids that key at the root, and the trace is exported on its own by
    the same command without `-f`.
    """
    trace = populated_trace()
    path = trace.export(tmp_path / "trace.cdx.json", format="cyclonedx")
    text = path.read_text(encoding="utf-8")
    document = json.loads(text)

    assert "extensions" not in document
    assert "counts" not in text
    assert "qasm" not in text
