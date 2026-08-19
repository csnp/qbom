"""
QBOM Core Data Models

Framework-agnostic models for capturing quantum experiment provenance.
Designed to be beautiful, immutable, and serializable.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, computed_field

from qbom.core.timeutil import as_utc, utc_now


class QBOMModel(BaseModel):
    """Base model with sensible defaults."""

    model_config = {
        "frozen": True,  # Immutable
        "extra": "allow",  # Future-proof
        "json_encoders": {datetime: lambda v: v.isoformat()},
    }


# ============================================================================
# Environment
# ============================================================================


class Package(QBOMModel):
    """A software package dependency."""

    name: str
    version: str
    purl: str | None = None  # Package URL (CycloneDX format)

    def __str__(self) -> str:
        return f"{self.name}=={self.version}"


class Environment(QBOMModel):
    """Complete software environment snapshot."""

    python: str = Field(description="Python version")
    platform: str = Field(description="OS and architecture")
    packages: list[Package] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=utc_now)

    @computed_field
    @property
    def quantum_sdk(self) -> str | None:
        """Primary quantum SDK detected."""
        sdk_priority = ["qiskit", "cirq", "pennylane", "braket"]
        for sdk in sdk_priority:
            for pkg in self.packages:
                if pkg.name.startswith(sdk):
                    return f"{pkg.name}=={pkg.version}"
        return None


# ============================================================================
# Circuit
# ============================================================================


class GateCounts(QBOMModel):
    """Gate count summary."""

    single_qubit: int = 0
    two_qubit: int = 0
    total: int = 0
    by_name: dict[str, int] = Field(default_factory=dict)


class Circuit(QBOMModel):
    """Quantum circuit representation (framework-agnostic)."""

    name: str | None = None
    num_qubits: int
    num_clbits: int = 0
    depth: int
    gates: GateCounts
    hash: str = Field(description="Content-addressable hash of circuit")

    # Optional detailed representations
    qasm: str | None = Field(default=None, description="OpenQASM representation")
    json_repr: dict[str, Any] | None = Field(default=None, description="Native JSON format")

    @computed_field
    @property
    def summary(self) -> str:
        """Human-readable circuit summary."""
        name = self.name or "circuit"
        return f"{name} ({self.num_qubits}q, depth {self.depth}, {self.gates.total} gates)"


# ============================================================================
# Transpilation
# ============================================================================


class QubitMapping(QBOMModel):
    """Logical to physical qubit mapping."""

    logical_to_physical: dict[int, int]

    @computed_field
    @property
    def physical_qubits(self) -> list[int]:
        """List of physical qubits used."""
        return sorted(self.logical_to_physical.values())


class Transpilation(QBOMModel):
    """Complete transpilation record."""

    # Settings
    optimization_level: int | None = None
    basis_gates: list[str] | None = None
    seed: int | None = None

    # Methods
    layout_method: str | None = None
    routing_method: str | None = None

    # Mappings
    initial_layout: QubitMapping | None = None
    final_layout: QubitMapping | None = None

    # Before/after
    input_circuit: Circuit | None = None
    output_circuit: Circuit | None = None

    @computed_field
    @property
    def depth_increase(self) -> float | None:
        """How much transpilation increased circuit depth."""
        if self.input_circuit and self.output_circuit:
            if self.input_circuit.depth > 0:
                return self.output_circuit.depth / self.input_circuit.depth
        return None


# ============================================================================
# Hardware
# ============================================================================


class QubitProperties(QBOMModel):
    """Properties of a single physical qubit."""

    index: int
    t1_us: float | None = Field(default=None, description="T1 relaxation time in microseconds")
    t2_us: float | None = Field(default=None, description="T2 coherence time in microseconds")
    readout_error: float | None = None
    frequency_ghz: float | None = None


class GateProperties(QBOMModel):
    """Properties of a gate on specific qubits."""

    gate: str
    qubits: tuple[int, ...]
    error: float | None = None
    duration_ns: float | None = None


class Calibration(QBOMModel):
    """Hardware calibration snapshot at time of execution."""

    timestamp: datetime
    qubits: list[QubitProperties] = Field(default_factory=list)
    gates: list[GateProperties] = Field(default_factory=list)

    def qubit(self, index: int) -> QubitProperties | None:
        """Get properties for a specific qubit."""
        for q in self.qubits:
            if q.index == index:
                return q
        return None

    def gate_error(self, gate: str, qubits: tuple[int, ...]) -> float | None:
        """Get error rate for a specific gate on specific qubits."""
        for g in self.gates:
            if g.gate == gate and g.qubits == qubits:
                return g.error
        return None


class Hardware(QBOMModel):
    """Hardware backend information."""

    provider: str = Field(description="Provider name (e.g., 'IBM Quantum', 'Google', 'AWS')")
    backend: str = Field(description="Backend name")
    num_qubits: int
    qubits_used: list[int] = Field(default_factory=list)
    is_simulator: bool = False
    calibration: Calibration | None = None

    @computed_field
    @property
    def summary(self) -> str:
        """Human-readable hardware summary."""
        sim = " (simulator)" if self.is_simulator else ""
        return f"{self.backend}{sim}"


# ============================================================================
# Execution
# ============================================================================


class ErrorMitigation(QBOMModel):
    """Error mitigation configuration."""

    method: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class Execution(QBOMModel):
    """Execution parameters and timing."""

    job_id: str | None = None
    shots: int
    seed: int | None = None
    error_mitigation: ErrorMitigation | None = None

    submitted_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @computed_field
    @property
    def queue_time_seconds(self) -> float | None:
        """Time spent waiting in queue."""
        if self.submitted_at and self.started_at:
            # Read as UTC first: one value may come from a trace written
            # before timestamps carried an offset.
            return (as_utc(self.started_at) - as_utc(self.submitted_at)).total_seconds()
        return None

    @computed_field
    @property
    def execution_time_seconds(self) -> float | None:
        """Actual execution time."""
        if self.started_at and self.completed_at:
            return (as_utc(self.completed_at) - as_utc(self.started_at)).total_seconds()
        return None


# ============================================================================
# Result
# ============================================================================


class Counts(QBOMModel):
    """Measurement result counts."""

    raw: dict[str, int]
    shots: int

    @computed_field
    @property
    def probabilities(self) -> dict[str, float]:
        """Convert counts to probabilities."""
        return {k: v / self.shots for k, v in self.raw.items()}

    @computed_field
    @property
    def top_results(self) -> list[tuple[str, float]]:
        """Top 5 results by probability."""
        probs = sorted(self.probabilities.items(), key=lambda x: -x[1])
        return probs[:5]


class Result(QBOMModel):
    """Execution results."""

    counts: Counts
    memory: list[str] | None = Field(default=None, description="Shot-by-shot results if available")
    metadata: dict[str, Any] = Field(default_factory=dict)
    hash: str = Field(description="Hash of raw results for verification")

    # Mitigated results (if error mitigation was applied)
    mitigated_counts: Counts | None = None
