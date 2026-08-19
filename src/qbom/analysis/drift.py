"""
QBOM Calibration Drift Analysis

Analyzes how hardware calibration has changed since an experiment ran.
This is critical because quantum hardware degrades and recalibrates daily.

Key insight: Even if you run the exact same circuit on the same backend,
results WILL differ if calibration has changed.

This module helps researchers:
1. Understand WHY their reproduction attempt differs
2. Decide if hardware drift explains the difference
3. Find better qubits for re-running experiments
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from qbom.core.timeutil import as_utc, utc_now

if TYPE_CHECKING:
    from qbom.core.models import Calibration
    from qbom.core.trace import Trace


@dataclass
class QubitDrift:
    """Drift analysis for a single qubit."""

    qubit_index: int

    # T1 relaxation time
    t1_original: float | None
    t1_current: float | None
    t1_change_percent: float | None

    # T2 coherence time
    t2_original: float | None
    t2_current: float | None
    t2_change_percent: float | None

    # Readout error
    readout_original: float | None
    readout_current: float | None
    readout_change_percent: float | None

    @property
    def has_significant_drift(self) -> bool:
        """True if any metric changed by >10%."""
        for change in [self.t1_change_percent, self.t2_change_percent, self.readout_change_percent]:
            if change is not None and abs(change) > 10:
                return True
        return False

    @property
    def drift_summary(self) -> str:
        """Human-readable drift summary."""
        if not self.has_significant_drift:
            return "Stable"

        changes = []
        if self.t1_change_percent and abs(self.t1_change_percent) > 10:
            direction = "↑" if self.t1_change_percent > 0 else "↓"
            changes.append(f"T1 {direction}{abs(self.t1_change_percent):.0f}%")
        if self.t2_change_percent and abs(self.t2_change_percent) > 10:
            direction = "↑" if self.t2_change_percent > 0 else "↓"
            changes.append(f"T2 {direction}{abs(self.t2_change_percent):.0f}%")
        if self.readout_change_percent and abs(self.readout_change_percent) > 10:
            direction = "↑" if self.readout_change_percent > 0 else "↓"
            changes.append(f"Readout {direction}{abs(self.readout_change_percent):.0f}%")

        return ", ".join(changes) if changes else "Minor changes"


@dataclass
class GateDrift:
    """Drift analysis for a gate."""

    gate_name: str
    qubits: tuple[int, ...]

    error_original: float | None
    error_current: float | None
    error_change_percent: float | None

    @property
    def has_significant_drift(self) -> bool:
        """True if error changed by >15%."""
        if self.error_change_percent is not None:
            return abs(self.error_change_percent) > 15
        return False


@dataclass
class DriftAnalysis:
    """
    Complete calibration drift analysis.

    Compares original experiment calibration to current (or provided) calibration.
    """

    # Time information
    original_calibration_time: datetime | None
    current_calibration_time: datetime | None
    time_elapsed: timedelta | None

    # Drift details
    qubit_drift: list[QubitDrift]
    gate_drift: list[GateDrift]

    # Summary metrics
    overall_drift_score: float  # 0-100, higher = more drift
    reproduction_feasibility: str  # "High", "Medium", "Low", "Very Low"

    # Recommendations
    recommendations: list[str]
    better_qubits: list[int] | None  # Suggested qubits if available

    @property
    def has_significant_drift(self) -> bool:
        """True if overall drift is concerning."""
        return self.overall_drift_score > 20

    def summary(self) -> str:
        """Human-readable summary."""
        if self.time_elapsed:
            days = self.time_elapsed.days
            time_str = f"{days} days" if days > 0 else f"{self.time_elapsed.seconds // 3600} hours"
        else:
            time_str = "unknown time"

        return (
            f"Drift Score: {self.overall_drift_score:.0f}/100 | "
            f"Elapsed: {time_str} | "
            f"Reproduction: {self.reproduction_feasibility}"
        )


def analyze_drift(
    trace: Trace,
    current_calibration: Calibration | None = None,
) -> DriftAnalysis | None:
    """
    Analyze calibration drift for a trace.

    Args:
        trace: The QBOM trace to analyze
        current_calibration: Current calibration data. If None, analysis
                            is limited to showing what WAS captured.

    Returns:
        DriftAnalysis if hardware info available, None otherwise.
    """
    if not trace.hardware:
        return None

    hw = trace.hardware
    original_cal = hw.calibration

    if not original_cal:
        # No original calibration - can only provide recommendations
        return DriftAnalysis(
            original_calibration_time=None,
            current_calibration_time=current_calibration.timestamp if current_calibration else None,
            time_elapsed=None,
            qubit_drift=[],
            gate_drift=[],
            overall_drift_score=100,  # Maximum uncertainty
            reproduction_feasibility="Very Low",
            recommendations=[
                "Original calibration not captured - cannot assess drift",
                "Re-running this experiment will likely produce different results",
                "Consider this a new experiment rather than a reproduction",
            ],
            better_qubits=None,
        )

    # If no current calibration provided, show what we have
    if not current_calibration:
        # as_utc reads a stored timestamp as UTC. Traces written before
        # timestamps carried an offset store a naive value, and subtracting
        # one of those from the current time would otherwise raise.
        age = utc_now() - as_utc(original_cal.timestamp)
        days_old = age.days

        if days_old > 7:
            feasibility = "Very Low"
            drift_score = 80
        elif days_old > 1:
            feasibility = "Low"
            drift_score = 50
        else:
            feasibility = "Medium"
            drift_score = 25

        return DriftAnalysis(
            original_calibration_time=original_cal.timestamp,
            current_calibration_time=None,
            time_elapsed=age,
            qubit_drift=[],
            gate_drift=[],
            overall_drift_score=drift_score,
            reproduction_feasibility=feasibility,
            recommendations=[
                f"Calibration is {days_old} days old",
                "Fetch current calibration from backend to compare",
                "Hardware properties change daily - expect some variation",
            ],
            better_qubits=None,
        )

    # Full comparison
    # The original comes from a trace file and the current one is usually
    # fetched from the backend now, so the two can differ in kind.
    time_elapsed = as_utc(current_calibration.timestamp) - as_utc(original_cal.timestamp)

    # Analyze qubit drift
    qubit_drift = []
    for orig_q in original_cal.qubits:
        # Find matching current qubit
        curr_q = None
        for q in current_calibration.qubits:
            if q.index == orig_q.index:
                curr_q = q
                break

        if curr_q:
            # Calculate changes
            t1_change = None
            if orig_q.t1_us and curr_q.t1_us:
                t1_change = ((curr_q.t1_us - orig_q.t1_us) / orig_q.t1_us) * 100

            t2_change = None
            if orig_q.t2_us and curr_q.t2_us:
                t2_change = ((curr_q.t2_us - orig_q.t2_us) / orig_q.t2_us) * 100

            readout_change = None
            if orig_q.readout_error and curr_q.readout_error:
                readout_change = ((curr_q.readout_error - orig_q.readout_error) / orig_q.readout_error) * 100

            qubit_drift.append(
                QubitDrift(
                    qubit_index=orig_q.index,
                    t1_original=orig_q.t1_us,
                    t1_current=curr_q.t1_us,
                    t1_change_percent=t1_change,
                    t2_original=orig_q.t2_us,
                    t2_current=curr_q.t2_us,
                    t2_change_percent=t2_change,
                    readout_original=orig_q.readout_error,
                    readout_current=curr_q.readout_error,
                    readout_change_percent=readout_change,
                )
            )

    # Analyze gate drift
    gate_drift = []
    for orig_g in original_cal.gates:
        # Find matching current gate
        for curr_g in current_calibration.gates:
            if curr_g.gate == orig_g.gate and curr_g.qubits == orig_g.qubits:
                error_change = None
                if orig_g.error and curr_g.error:
                    error_change = ((curr_g.error - orig_g.error) / orig_g.error) * 100

                gate_drift.append(
                    GateDrift(
                        gate_name=orig_g.gate,
                        qubits=orig_g.qubits,
                        error_original=orig_g.error,
                        error_current=curr_g.error,
                        error_change_percent=error_change,
                    )
                )
                break

    # Calculate overall drift score
    drift_scores = []
    for qd in qubit_drift:
        for change in [qd.t1_change_percent, qd.t2_change_percent, qd.readout_change_percent]:
            if change is not None:
                drift_scores.append(min(abs(change), 100))

    for gd in gate_drift:
        if gd.error_change_percent is not None:
            drift_scores.append(min(abs(gd.error_change_percent), 100))

    if drift_scores:
        overall_drift = sum(drift_scores) / len(drift_scores)
    else:
        overall_drift = 50  # Unknown

    # Determine feasibility
    if overall_drift < 10:
        feasibility = "High"
    elif overall_drift < 25:
        feasibility = "Medium"
    elif overall_drift < 50:
        feasibility = "Low"
    else:
        feasibility = "Very Low"

    # Generate recommendations
    recommendations = []

    significant_qubit_drift = [qd for qd in qubit_drift if qd.has_significant_drift]
    if significant_qubit_drift:
        affected = [str(qd.qubit_index) for qd in significant_qubit_drift]
        recommendations.append(f"Significant drift on qubits: {', '.join(affected)}")

    significant_gate_drift = [gd for gd in gate_drift if gd.has_significant_drift]
    if significant_gate_drift:
        gates = [f"{gd.gate_name}{list(gd.qubits)}" for gd in significant_gate_drift]
        recommendations.append(f"Gate errors changed significantly: {', '.join(gates)}")

    if time_elapsed.days > 1:
        recommendations.append(f"Calibration is {time_elapsed.days} days old - expect variation")

    if feasibility in ["Low", "Very Low"]:
        recommendations.append("Consider re-running as a new experiment rather than reproduction")

    return DriftAnalysis(
        original_calibration_time=original_cal.timestamp,
        current_calibration_time=current_calibration.timestamp,
        time_elapsed=time_elapsed,
        qubit_drift=qubit_drift,
        gate_drift=gate_drift,
        overall_drift_score=overall_drift,
        reproduction_feasibility=feasibility,
        recommendations=recommendations,
        better_qubits=None,  # Would need full backend info to compute
    )


def explain_result_difference(
    trace1: Trace,
    trace2: Trace,
) -> list[str]:
    """
    Explain why two experiments might have different results.

    This is the "why is my reproduction different?" question.
    """
    explanations = []

    # Check backend differences
    if trace1.hardware and trace2.hardware:
        if trace1.hardware.backend != trace2.hardware.backend:
            explanations.append(f"Different backends: {trace1.hardware.backend} vs {trace2.hardware.backend}")

        if trace1.hardware.qubits_used != trace2.hardware.qubits_used:
            explanations.append(
                f"Different physical qubits: {trace1.hardware.qubits_used} vs {trace2.hardware.qubits_used}"
            )

        # Calibration time difference
        if trace1.hardware.calibration and trace2.hardware.calibration:
            # Either trace may predate offsets being written, so read both as UTC.
            time_diff = abs(
                (
                    as_utc(trace2.hardware.calibration.timestamp) - as_utc(trace1.hardware.calibration.timestamp)
                ).total_seconds()
            )
            if time_diff > 86400:  # More than 1 day
                days = time_diff / 86400
                explanations.append(f"Calibrations are {days:.1f} days apart - hardware drift likely")

    # Check transpilation differences
    if trace1.transpilation and trace2.transpilation:
        if trace1.transpilation.optimization_level != trace2.transpilation.optimization_level:
            lvl1 = trace1.transpilation.optimization_level
            lvl2 = trace2.transpilation.optimization_level
            explanations.append(f"Different optimization levels: {lvl1} vs {lvl2}")

        if trace1.transpilation.final_layout != trace2.transpilation.final_layout:
            explanations.append("Different qubit mappings after transpilation")

    # Check execution differences
    if trace1.execution and trace2.execution:
        if trace1.execution.shots != trace2.execution.shots:
            explanations.append(f"Different shot counts: {trace1.execution.shots} vs {trace2.execution.shots}")

    # Check circuit differences
    if trace1.circuits and trace2.circuits:
        if trace1.circuits[0].hash != trace2.circuits[0].hash:
            explanations.append("Circuit definitions differ - not the same experiment")

    if not explanations:
        explanations.append("No obvious differences found - variation may be due to quantum noise")

    return explanations
