"""
QBOM Trace - The complete record of a quantum experiment.

A Trace is the atomic unit of QBOM. It captures everything needed
to understand and reproduce a quantum experiment.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field

from qbom.core.models import (
    Circuit,
    Environment,
    Execution,
    Hardware,
    Result,
    Transpilation,
)


def _generate_id() -> str:
    """Generate a short, memorable trace ID."""
    import secrets

    return f"qbom_{secrets.token_hex(4)}"


class Metadata(BaseModel):
    """User-provided metadata for a trace."""

    model_config = {"frozen": True, "extra": "allow"}

    name: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    authors: list[str] = Field(default_factory=list)
    paper: str | None = Field(default=None, description="DOI or URL of related paper")
    experiment_id: str | None = Field(default=None, description="User's experiment identifier")


class Trace(BaseModel):
    """
    Complete QBOM trace of a quantum experiment.

    A Trace is immutable after creation. It captures:
    - Environment: Software versions, platform
    - Circuit(s): The quantum program(s) executed
    - Transpilation: How circuits were transformed for hardware
    - Hardware: Backend and calibration snapshot
    - Execution: Job parameters and timing
    - Result: Measurement outcomes

    Example:
        trace = qbom.current()
        print(trace.summary)
        trace.export("experiment.qbom.json")
    """

    model_config = {
        "frozen": True,
        "extra": "allow",
        "json_encoders": {datetime: lambda v: v.isoformat()},
    }

    # Identity
    id: str = Field(default_factory=_generate_id)
    qbom_version: str = "1.0"
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Core components
    environment: Environment | None = None
    circuits: list[Circuit] = Field(default_factory=list)
    transpilation: Transpilation | None = None
    hardware: Hardware | None = None
    execution: Execution | None = None
    result: Result | None = None

    # User metadata
    metadata: Metadata = Field(default_factory=Metadata)

    # Lineage
    parent_id: str | None = Field(default=None, description="ID of parent trace if this is derived")

    @computed_field
    @property
    def summary(self) -> str:
        """Human-readable one-line summary."""
        parts = []

        if self.circuits:
            c = self.circuits[0]
            if len(self.circuits) > 1:
                parts.append(f"{len(self.circuits)} circuits")
            else:
                parts.append(f"{c.num_qubits}q circuit")

        if self.hardware:
            parts.append(f"on {self.hardware.backend}")

        if self.execution:
            parts.append(f"{self.execution.shots:,} shots")

        return " | ".join(parts) if parts else "Empty trace"

    @computed_field
    @property
    def content_hash(self) -> str:
        """
        Content-addressable hash of the trace.

        This hash uniquely identifies the experiment based on its content,
        enabling verification that results haven't been tampered with.
        """
        # Hash the core scientific content (not metadata or timestamps)
        content = {
            "circuits": [c.hash for c in self.circuits],
            "transpilation": self.transpilation.model_dump() if self.transpilation else None,
            "hardware": {
                "backend": self.hardware.backend if self.hardware else None,
                "qubits_used": self.hardware.qubits_used if self.hardware else None,
            },
            "execution": {
                "shots": self.execution.shots if self.execution else None,
                "seed": self.execution.seed if self.execution else None,
            },
            "result_hash": self.result.hash if self.result else None,
        }
        serialized = json.dumps(content, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()[:16]

    # ========================================================================
    # Export Methods
    # ========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert trace to dictionary."""
        return self.model_dump(mode="json", exclude_none=True)

    def to_json(self, indent: int = 2) -> str:
        """Convert trace to JSON string."""
        return self.model_dump_json(indent=indent, exclude_none=True)

    def export(
        self,
        path: str | Path,
        format: Literal["json", "cyclonedx", "spdx", "yaml"] = "json",
    ) -> Path:
        """
        Export trace to file.

        Args:
            path: Output file path
            format: Export format (json, cyclonedx, spdx, yaml)

        Returns:
            Path to exported file

        Supported Formats:
            - json: Native QBOM format (default)
            - cyclonedx: CycloneDX 1.5 SBOM with QBOM extension
            - spdx: SPDX 2.3 SBOM with QBOM extension
            - yaml: YAML representation of native format
        """
        path = Path(path)

        if format == "json":
            path.write_text(self.to_json())
        elif format == "cyclonedx":
            path.write_text(self._to_cyclonedx())
        elif format == "spdx":
            path.write_text(self._to_spdx())
        elif format == "yaml":
            try:
                import yaml
            except ImportError as exc:
                raise ImportError(
                    'YAML export needs PyYAML, which is not installed. Install it with: pip install "qbom[yaml]"'
                ) from exc

            path.write_text(yaml.dump(self.to_dict(), default_flow_style=False))
        else:
            raise ValueError(f"Unknown format: {format}")

        return path

    def _to_cyclonedx(self) -> str:
        """Export as CycloneDX SBOM with QBOM extension."""
        sbom = {
            "$schema": "http://cyclonedx.org/schema/bom-1.5.schema.json",
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "version": 1,
            "serialNumber": f"urn:uuid:{self.id}",
            "metadata": {
                "timestamp": self.created_at.isoformat(),
                "component": {
                    "type": "application",
                    "name": self.metadata.name or "quantum-experiment",
                    "version": self.id,
                    "description": self.metadata.description,
                },
                "properties": [
                    {"name": "qbom:version", "value": self.qbom_version},
                    {"name": "qbom:content-hash", "value": self.content_hash},
                ],
            },
            "components": self._generate_cyclonedx_components(),
            "externalReferences": [],
        }

        # Add paper reference if available
        if self.metadata.paper:
            sbom["externalReferences"].append({"type": "documentation", "url": self.metadata.paper})

        # Embed full QBOM as extension
        sbom["extensions"] = {"qbom": self.to_dict()}

        return json.dumps(sbom, indent=2, default=str)

    def _generate_cyclonedx_components(self) -> list[dict]:
        """Generate CycloneDX components from environment."""
        components = []
        if self.environment:
            for pkg in self.environment.packages:
                components.append(
                    {
                        "type": "library",
                        "name": pkg.name,
                        "version": pkg.version,
                        "purl": pkg.purl or f"pkg:pypi/{pkg.name}@{pkg.version}",
                    }
                )
        return components

    def _to_spdx(self) -> str:
        """
        Export as SPDX 2.3 SBOM with QBOM extension.

        SPDX (Software Package Data Exchange) is an open standard for
        communicating software bill of materials information.
        """

        # Generate SPDX document namespace
        doc_namespace = f"https://qbom.csnp.org/spdx/{self.id}"

        spdx = {
            "spdxVersion": "SPDX-2.3",
            "dataLicense": "CC0-1.0",
            "SPDXID": "SPDXRef-DOCUMENT",
            "name": self.metadata.name or f"qbom-trace-{self.id}",
            "documentNamespace": doc_namespace,
            "creationInfo": {
                "created": self.created_at.isoformat(),
                "creators": [
                    "Tool: qbom-" + self.qbom_version,
                    *[f"Person: {author}" for author in self.metadata.authors],
                ],
                "licenseListVersion": "3.19",
            },
            "packages": self._generate_spdx_packages(),
            "relationships": self._generate_spdx_relationships(),
            "annotations": self._generate_spdx_annotations(),
        }

        # Add external document references if paper is available
        if self.metadata.paper:
            spdx["externalDocumentRefs"] = [
                {
                    "externalDocumentId": "DocumentRef-paper",
                    "spdxDocument": self.metadata.paper,
                    "checksum": {
                        "algorithm": "SHA256",
                        "checksumValue": "0" * 64,  # Placeholder
                    },
                }
            ]

        return json.dumps(spdx, indent=2, default=str)

    def _generate_spdx_packages(self) -> list[dict]:
        """Generate SPDX packages from environment and experiment."""
        packages = []

        # Main experiment package
        main_pkg = {
            "SPDXID": "SPDXRef-QuantumExperiment",
            "name": self.metadata.name or "quantum-experiment",
            "versionInfo": self.id,
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
            "supplier": "NOASSERTION",
            "originator": "NOASSERTION",
            "licenseConcluded": "NOASSERTION",
            "licenseDeclared": "NOASSERTION",
            "copyrightText": "NOASSERTION",
            "comment": self.metadata.description or "Quantum computing experiment",
            "externalRefs": [
                {
                    "referenceCategory": "OTHER",
                    "referenceType": "qbom",
                    "referenceLocator": f"qbom:{self.id}",
                    "comment": f"QBOM content hash: {self.content_hash}",
                }
            ],
        }

        # Add hardware info if available
        if self.hardware:
            main_pkg["comment"] += f" | Backend: {self.hardware.backend}"
            if self.hardware.calibration:
                main_pkg["comment"] += f" | Calibration: {self.hardware.calibration.timestamp.isoformat()}"

        packages.append(main_pkg)

        # Add environment packages
        if self.environment:
            for idx, pkg in enumerate(self.environment.packages):
                spdx_pkg = {
                    "SPDXID": f"SPDXRef-Package-{idx}",
                    "name": pkg.name,
                    "versionInfo": pkg.version,
                    "downloadLocation": "NOASSERTION",
                    "filesAnalyzed": False,
                    "supplier": "NOASSERTION",
                    "originator": "NOASSERTION",
                    "licenseConcluded": "NOASSERTION",
                    "licenseDeclared": "NOASSERTION",
                    "copyrightText": "NOASSERTION",
                    "externalRefs": [
                        {
                            "referenceCategory": "PACKAGE-MANAGER",
                            "referenceType": "purl",
                            "referenceLocator": pkg.purl or f"pkg:pypi/{pkg.name}@{pkg.version}",
                        }
                    ],
                }
                packages.append(spdx_pkg)

        return packages

    def _generate_spdx_relationships(self) -> list[dict]:
        """Generate SPDX relationships between packages."""
        relationships = [
            {
                "spdxElementId": "SPDXRef-DOCUMENT",
                "relatedSpdxElement": "SPDXRef-QuantumExperiment",
                "relationshipType": "DESCRIBES",
            }
        ]

        # Add dependencies
        if self.environment:
            for idx, _ in enumerate(self.environment.packages):
                relationships.append(
                    {
                        "spdxElementId": "SPDXRef-QuantumExperiment",
                        "relatedSpdxElement": f"SPDXRef-Package-{idx}",
                        "relationshipType": "DEPENDS_ON",
                    }
                )

        return relationships

    def _generate_spdx_annotations(self) -> list[dict]:
        """Generate SPDX annotations with QBOM data."""
        annotations = []

        # Embed QBOM trace as annotation (SPDX extension mechanism)
        qbom_annotation = {
            "annotationDate": self.created_at.isoformat(),
            "annotationType": "OTHER",
            "annotator": "Tool: qbom",
            "comment": json.dumps(
                {
                    "qbom_version": self.qbom_version,
                    "trace_id": self.id,
                    "content_hash": self.content_hash,
                    "summary": self.summary,
                    # Include key reproducibility data
                    "circuits": len(self.circuits),
                    "hardware": {
                        "backend": self.hardware.backend if self.hardware else None,
                        "qubits_used": self.hardware.qubits_used if self.hardware else None,
                        "is_simulator": self.hardware.is_simulator if self.hardware else None,
                    },
                    "execution": {
                        "shots": self.execution.shots if self.execution else None,
                    },
                    # Full QBOM data reference
                    "full_qbom": self.to_dict(),
                },
                default=str,
            ),
        }
        annotations.append(qbom_annotation)

        return annotations

    # ========================================================================
    # Display Methods
    # ========================================================================

    def show(self) -> None:
        """Display trace in terminal with rich formatting."""
        from qbom.cli.display import display_trace

        display_trace(self)

    def _repr_html_(self) -> str:
        """Jupyter notebook HTML representation."""
        from qbom.notebook.display import trace_to_html

        return trace_to_html(self)

    def __str__(self) -> str:
        return f"Trace({self.id}: {self.summary})"

    def __repr__(self) -> str:
        return f"Trace(id={self.id!r}, summary={self.summary!r})"


# ============================================================================
# Trace Builder (for mutable construction)
# ============================================================================


class TraceBuilder:
    """
    Mutable builder for constructing Traces.

    Used internally by adapters to accumulate data before
    creating an immutable Trace.
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {
            "circuits": [],
            "metadata": Metadata(),
        }

    def set_environment(self, env: Environment) -> TraceBuilder:
        self._data["environment"] = env
        return self

    def add_circuit(self, circuit: Circuit) -> TraceBuilder:
        self._data["circuits"].append(circuit)
        return self

    def set_transpilation(self, transpilation: Transpilation) -> TraceBuilder:
        self._data["transpilation"] = transpilation
        return self

    def set_hardware(self, hardware: Hardware) -> TraceBuilder:
        self._data["hardware"] = hardware
        return self

    def set_execution(self, execution: Execution) -> TraceBuilder:
        self._data["execution"] = execution
        return self

    def set_result(self, result: Result) -> TraceBuilder:
        self._data["result"] = result
        return self

    def set_metadata(
        self,
        name: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> TraceBuilder:
        self._data["metadata"] = Metadata(
            name=name,
            description=description,
            tags=tags or [],
        )
        return self

    def build(self) -> Trace:
        """Build immutable Trace from accumulated data."""
        return Trace(**self._data)
