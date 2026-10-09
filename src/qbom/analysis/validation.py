"""
QBOM Trace Validation

Validates QBOM traces for completeness and correctness.
Provides clear guidance on what's missing and how to fix it.

This helps researchers ensure their experiments are properly documented
before publication or sharing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qbom.core.trace import Trace


class ValidationLevel(Enum):
    """Severity level of validation issues."""

    ERROR = "error"  # Must fix - blocks reproducibility
    WARNING = "warning"  # Should fix - reduces reproducibility
    INFO = "info"  # Nice to have - improves documentation


@dataclass
class ValidationIssue:
    """A single validation issue found in a trace."""

    level: ValidationLevel
    category: str
    message: str
    fix: str  # How to fix the issue

    @property
    def icon(self) -> str:
        """Terminal icon for the issue level."""
        icons = {
            ValidationLevel.ERROR: "✗",
            ValidationLevel.WARNING: "⚠",
            ValidationLevel.INFO: "ℹ",
        }
        return icons.get(self.level, "?")


# How to add QASM to a trace that was written without it. The code between the
# backticks must run as printed. It used to call QuantumCircuit.qasm(), which
# Qiskit 1.0 removed, and assign to a field of Circuit, which is frozen, so
# following it ended in an error either way.
_STORE_QASM_FIX = (
    "Store the circuit as OpenQASM so it can be rebuilt exactly. A trace is read-only, "
    "so save an updated copy in its place. With Qiskit 1.0 or newer, where trace is this "
    "trace (qbom.current() right after the run) and circuit is the QuantumCircuit you ran: "
    "`from pathlib import Path; from qiskit import qasm2; "
    'first = trace.circuits[0].model_copy(update={"qasm": qasm2.dumps(circuit)}); '
    'trace.model_copy(update={"circuits": [first, *trace.circuits[1:]]})'
    '.export(Path.home() / ".qbom" / "traces" / f"{trace.id}.json")`'
)


@dataclass
class ValidationResult:
    """Complete validation result for a trace."""

    is_valid: bool  # No errors (warnings/info ok)
    is_complete: bool  # No errors or warnings
    issues: list[ValidationIssue]
    summary: str

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.level == ValidationLevel.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.level == ValidationLevel.WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for i in self.issues if i.level == ValidationLevel.INFO)


def validate_trace(trace: Trace) -> ValidationResult:
    """
    Validate a QBOM trace for completeness and correctness.

    Args:
        trace: The trace to validate

    Returns:
        ValidationResult with all issues found and guidance

    Example:
        result = validate_trace(trace)
        if not result.is_valid:
            for issue in result.issues:
                print(f"{issue.icon} {issue.message}")
                print(f"  Fix: {issue.fix}")
    """
    issues: list[ValidationIssue] = []

    # =========================================================================
    # ENVIRONMENT VALIDATION
    # =========================================================================
    if trace.environment is None:
        issues.append(
            ValidationIssue(
                level=ValidationLevel.ERROR,
                category="Environment",
                message="No environment captured",
                fix="Ensure QBOM is imported before running your experiment. "
                "QBOM automatically captures the Python environment.",
            )
        )
    else:
        env = trace.environment

        if not env.python:
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.ERROR,
                    category="Environment",
                    message="Python version not captured",
                    fix="This should be automatic. Check that QBOM initialized correctly.",
                )
            )

        if not env.quantum_sdk:
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.WARNING,
                    category="Environment",
                    message="No quantum SDK detected",
                    fix="Install a quantum SDK (qiskit, cirq, pennylane) before running.",
                )
            )

        if len(env.packages) == 0:
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.WARNING,
                    category="Environment",
                    message="No package versions captured",
                    fix="Package capture should be automatic. Verify QBOM installation.",
                )
            )
        elif len(env.packages) < 3:
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.INFO,
                    category="Environment",
                    message="Few packages captured - environment may be incomplete",
                    fix="Consider capturing more dependencies for better reproducibility.",
                )
            )

    # =========================================================================
    # CIRCUIT VALIDATION
    # =========================================================================
    if not trace.circuits or len(trace.circuits) == 0:
        issues.append(
            ValidationIssue(
                level=ValidationLevel.ERROR,
                category="Circuit",
                message="No circuits captured",
                fix="Ensure your quantum circuit is defined before execution. "
                "QBOM captures circuits during transpilation or execution.",
            )
        )
    else:
        circuit = trace.circuits[0]

        if circuit.num_qubits == 0:
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.ERROR,
                    category="Circuit",
                    message="Circuit has 0 qubits",
                    fix="Your circuit appears empty. Verify circuit construction.",
                )
            )

        if not circuit.hash:
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.WARNING,
                    category="Circuit",
                    message="Circuit hash not computed",
                    fix="Circuit verification requires a hash. Check circuit capture.",
                )
            )

        if not circuit.qasm and not circuit.json_repr:
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.INFO,
                    category="Circuit",
                    message="No QASM or JSON representation stored",
                    fix=_STORE_QASM_FIX,
                )
            )

        if circuit.gates and circuit.gates.total == 0:
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.WARNING,
                    category="Circuit",
                    message="Circuit has no gates",
                    fix="An empty circuit won't produce meaningful results.",
                )
            )

    # =========================================================================
    # TRANSPILATION VALIDATION
    # =========================================================================
    if trace.hardware and not trace.hardware.is_simulator:
        # Transpilation is critical for real hardware
        if trace.transpilation is None:
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.ERROR,
                    category="Transpilation",
                    message="No transpilation captured for hardware execution",
                    fix="Transpilation is critical for reproducibility. "
                    "Use qiskit.transpile() or equivalent before execution.",
                )
            )
        else:
            transp = trace.transpilation

            if transp.optimization_level is None:
                issues.append(
                    ValidationIssue(
                        level=ValidationLevel.WARNING,
                        category="Transpilation",
                        message="Optimization level not recorded",
                        fix="Specify optimization_level in transpile() call.",
                    )
                )

            if not transp.final_layout:
                issues.append(
                    ValidationIssue(
                        level=ValidationLevel.ERROR,
                        category="Transpilation",
                        message="Final qubit layout not captured",
                        fix="The physical qubit mapping is essential for reproduction. "
                        "Ensure transpilation output includes layout information.",
                    )
                )

    # =========================================================================
    # HARDWARE VALIDATION
    # =========================================================================
    if trace.hardware is None:
        issues.append(
            ValidationIssue(
                level=ValidationLevel.ERROR,
                category="Hardware",
                message="No hardware information captured",
                fix="Ensure you execute on a backend. QBOM captures hardware "
                "information during backend.run() or equivalent.",
            )
        )
    else:
        hw = trace.hardware

        if not hw.backend:
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.ERROR,
                    category="Hardware",
                    message="Backend name not captured",
                    fix="Backend identification is required for reproduction.",
                )
            )

        if not hw.is_simulator:
            # Real hardware requires additional information
            if not hw.qubits_used or len(hw.qubits_used) == 0:
                issues.append(
                    ValidationIssue(
                        level=ValidationLevel.ERROR,
                        category="Hardware",
                        message="Physical qubits not recorded",
                        fix="For real hardware, knowing which physical qubits "
                        "were used is essential. Check transpilation output.",
                    )
                )

            if not hw.calibration:
                issues.append(
                    ValidationIssue(
                        level=ValidationLevel.ERROR,
                        category="Hardware",
                        message="No calibration snapshot captured",
                        fix="Calibration data is the most critical piece for "
                        "hardware reproducibility. Hardware properties change "
                        "daily. Without this, reproduction is nearly impossible.",
                    )
                )
            else:
                cal = hw.calibration

                if not cal.timestamp:
                    issues.append(
                        ValidationIssue(
                            level=ValidationLevel.WARNING,
                            category="Hardware",
                            message="Calibration timestamp missing",
                            fix="Record when calibration data was captured.",
                        )
                    )

                if not cal.qubits or len(cal.qubits) == 0:
                    issues.append(
                        ValidationIssue(
                            level=ValidationLevel.WARNING,
                            category="Hardware",
                            message="No qubit properties in calibration",
                            fix="Capture T1, T2, and readout error for used qubits.",
                        )
                    )

                if not cal.gates or len(cal.gates) == 0:
                    issues.append(
                        ValidationIssue(
                            level=ValidationLevel.WARNING,
                            category="Hardware",
                            message="No gate errors in calibration",
                            fix="Capture gate error rates for used gates.",
                        )
                    )

    # =========================================================================
    # EXECUTION VALIDATION
    # =========================================================================
    if trace.execution is None:
        issues.append(
            ValidationIssue(
                level=ValidationLevel.WARNING,
                category="Execution",
                message="No execution parameters captured",
                fix="Execution parameters (shots, timing) help with reproduction.",
            )
        )
    else:
        exe = trace.execution

        if not exe.shots or exe.shots == 0:
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.ERROR,
                    category="Execution",
                    message="Shot count not recorded",
                    fix="The number of shots directly affects result statistics. Specify shots in your run() call.",
                )
            )

        if not exe.job_id:
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.INFO,
                    category="Execution",
                    message="Job ID not captured",
                    fix="Job IDs enable traceability to cloud provider records.",
                )
            )

    # =========================================================================
    # RESULT VALIDATION
    # =========================================================================
    if trace.result is None:
        issues.append(
            ValidationIssue(
                level=ValidationLevel.WARNING,
                category="Results",
                message="No results captured",
                fix="Results allow verification of reproduction attempts. "
                "Wait for job.result() before exporting the trace.",
            )
        )
    else:
        res = trace.result

        if not res.counts or not res.counts.raw:
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.WARNING,
                    category="Results",
                    message="No measurement counts captured",
                    fix="Capture raw counts from job.result().get_counts().",
                )
            )

        if not res.hash:
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.INFO,
                    category="Results",
                    message="Result hash not computed",
                    fix="Result hashes enable tamper detection.",
                )
            )

    # =========================================================================
    # COMPUTE SUMMARY
    # =========================================================================
    error_count = sum(1 for i in issues if i.level == ValidationLevel.ERROR)
    warning_count = sum(1 for i in issues if i.level == ValidationLevel.WARNING)
    info_count = sum(1 for i in issues if i.level == ValidationLevel.INFO)

    is_valid = error_count == 0
    is_complete = error_count == 0 and warning_count == 0

    if is_complete and info_count == 0:
        summary = "Trace is complete and ready for publication"
    elif is_complete:
        summary = f"Trace is valid with {info_count} suggestion(s)"
    elif is_valid:
        summary = f"Trace is valid but has {warning_count} warning(s)"
    else:
        summary = f"Trace has {error_count} error(s) that must be fixed"

    return ValidationResult(
        is_valid=is_valid,
        is_complete=is_complete,
        issues=issues,
        summary=summary,
    )


def validate_for_publication(trace: Trace) -> ValidationResult:
    """
    Stricter validation for traces intended for publication.

    This enforces additional requirements:
    - Must have circuit QASM or JSON representation
    - Must have result counts
    - Must have all metadata fields

    Args:
        trace: The trace to validate

    Returns:
        ValidationResult with publication-specific checks
    """
    result = validate_trace(trace)
    issues = list(result.issues)

    # Additional publication requirements
    if not trace.metadata.name:
        issues.append(
            ValidationIssue(
                level=ValidationLevel.WARNING,
                category="Metadata",
                message="Experiment name not set",
                fix="Add a descriptive name for your experiment.",
            )
        )

    if not trace.metadata.description:
        issues.append(
            ValidationIssue(
                level=ValidationLevel.INFO,
                category="Metadata",
                message="No experiment description",
                fix="Add a description explaining the experiment purpose.",
            )
        )

    if trace.circuits and trace.circuits[0]:
        circuit = trace.circuits[0]
        if not circuit.qasm and not circuit.json_repr:
            # Upgrade from INFO to WARNING for publication
            issues = [i for i in issues if not (i.category == "Circuit" and "QASM" in i.message)]
            issues.append(
                ValidationIssue(
                    level=ValidationLevel.WARNING,
                    category="Circuit",
                    message="No circuit representation for exact reproduction",
                    fix=_STORE_QASM_FIX,
                )
            )

    # Recompute summary
    error_count = sum(1 for i in issues if i.level == ValidationLevel.ERROR)
    warning_count = sum(1 for i in issues if i.level == ValidationLevel.WARNING)

    is_valid = error_count == 0
    is_complete = error_count == 0 and warning_count == 0

    if is_complete:
        summary = "Trace is ready for publication"
    elif is_valid:
        summary = f"Trace has {warning_count} warning(s) to address before publication"
    else:
        summary = f"Trace has {error_count} error(s) that block publication"

    return ValidationResult(
        is_valid=is_valid,
        is_complete=is_complete,
        issues=issues,
        summary=summary,
    )
