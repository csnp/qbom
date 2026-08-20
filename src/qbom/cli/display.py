"""
QBOM Display Utilities

Beautiful terminal output using Rich.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from qbom.core.trace import Trace

console = Console()


def display_trace_list(traces: list[Trace]) -> None:
    """Display a list of traces in a beautiful table."""
    table = Table(
        title="Recent QBOM Traces",
        box=box.ROUNDED,
        header_style="bold cyan",
        title_style="bold",
    )

    table.add_column("ID", style="dim")
    table.add_column("Created", style="dim")
    table.add_column("Backend")
    table.add_column("Circuit")
    table.add_column("Shots", justify="right")

    for trace in traces:
        # Format time
        time_str = trace.created_at.strftime("%Y-%m-%d %H:%M")

        # Backend
        backend = trace.hardware.backend if trace.hardware else "-"

        # Circuit summary
        if trace.circuits:
            c = trace.circuits[0]
            circuit = f"{c.num_qubits}q, d={c.depth}"
        else:
            circuit = "-"

        # Shots
        shots = f"{trace.execution.shots:,}" if trace.execution else "-"

        table.add_row(trace.id, time_str, backend, circuit, shots)

    console.print(table)


def display_trace(trace: Trace) -> None:
    """Display a single trace with full details."""
    # Header
    header = Text()
    header.append("QBOM: ", style="bold cyan")
    header.append(trace.id, style="bold")

    content = []

    # Summary
    content.append(f"[dim]Summary:[/dim] {trace.summary}")
    content.append(f"[dim]Created:[/dim] {trace.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    content.append(f"[dim]Hash:[/dim] {trace.content_hash}")
    content.append("")

    # Environment
    if trace.environment:
        content.append("[bold cyan]ENVIRONMENT[/bold cyan]")
        content.append(f"  Python:  {trace.environment.python}")
        if trace.environment.quantum_sdk:
            content.append(f"  SDK:     {trace.environment.quantum_sdk}")
        for pkg in trace.environment.packages[:5]:
            content.append(f"  {pkg.name}: {pkg.version}")
        content.append("")

    # Circuit
    if trace.circuits:
        content.append("[bold cyan]CIRCUIT[/bold cyan]")
        c = trace.circuits[0]
        content.append(f"  Name:    {c.name or '(unnamed)'}")
        content.append(f"  Qubits:  {c.num_qubits}")
        content.append(f"  Depth:   {c.depth}")
        content.append(f"  Gates:   {c.gates.total} ({c.gates.single_qubit} 1q, {c.gates.two_qubit} 2q)")
        content.append(f"  Hash:    {c.hash}")
        content.append("")

    # Transpilation
    if trace.transpilation:
        t = trace.transpilation
        content.append("[bold cyan]TRANSPILATION[/bold cyan]")
        if t.optimization_level is not None:
            content.append(f"  Optimization: Level {t.optimization_level}")
        if t.layout_method:
            content.append(f"  Layout:   {t.layout_method}")
        if t.routing_method:
            content.append(f"  Routing:  {t.routing_method}")
        if t.final_layout:
            content.append(f"  Qubits:   {t.final_layout.physical_qubits}")
        if t.depth_increase:
            in_depth = t.input_circuit.depth if t.input_circuit else "?"
            out_depth = t.output_circuit.depth if t.output_circuit else "?"
            content.append(f"  Depth:    {in_depth} → {out_depth} ({t.depth_increase:.1f}x)")
        content.append("")

    # Hardware
    if trace.hardware:
        h = trace.hardware
        content.append("[bold cyan]HARDWARE[/bold cyan]")
        content.append(f"  Provider: {h.provider}")
        content.append(f"  Backend:  {h.backend}")
        if h.is_simulator:
            content.append("  Type:     Simulator")
        elif h.num_qubits is None:
            # A backend does not have to report a qubit count. Say so rather
            # than printing "None total".
            content.append(f"  Qubits:   {len(h.qubits_used)} used, total not reported by the backend")
        else:
            content.append(f"  Qubits:   {h.num_qubits} total, {len(h.qubits_used)} used")

        if h.calibration:
            cal = h.calibration
            content.append(f"  Calibration: {cal.timestamp.strftime('%Y-%m-%d %H:%M UTC')}")

            # Show T1/T2 for used qubits
            if h.qubits_used and cal.qubits:
                for qi in h.qubits_used[:3]:  # Show first 3
                    q = cal.qubit(qi)
                    if q and q.t1_us:
                        if q.t2_us:
                            content.append(f"    Qubit {qi}: T1={q.t1_us:.0f}μs, T2={q.t2_us:.0f}μs")
                        else:
                            content.append(f"    Qubit {qi}: T1={q.t1_us:.0f}μs")
        content.append("")

    # Execution
    if trace.execution:
        e = trace.execution
        content.append("[bold cyan]EXECUTION[/bold cyan]")
        if e.job_id:
            content.append(f"  Job ID:  {e.job_id}")
        content.append(f"  Shots:   {e.shots:,}")
        if e.execution_time_seconds:
            content.append(f"  Time:    {e.execution_time_seconds:.1f}s")
        content.append("")

    # Results
    if trace.result:
        r = trace.result
        content.append("[bold cyan]RESULTS[/bold cyan]")

        # Top results
        for bitstring, prob in r.counts.top_results[:5]:
            bar_len = int(prob * 30)
            bar = "█" * bar_len + "░" * (30 - bar_len)
            content.append(f"  |{bitstring}⟩ {bar} {prob * 100:5.1f}%")

        if len(r.counts.raw) > 5:
            content.append(f"  [dim]... and {len(r.counts.raw) - 5} more states[/dim]")
        content.append("")

    panel = Panel(
        "\n".join(content),
        title=header,
        border_style="cyan",
        box=box.ROUNDED,
    )
    console.print(panel)


def display_diff(trace1: Trace, trace2: Trace) -> None:
    """Display side-by-side comparison of two traces."""
    table = Table(
        title="QBOM Comparison",
        box=box.ROUNDED,
        header_style="bold cyan",
    )

    table.add_column("Property", style="dim")
    table.add_column(trace1.id, style="white")
    table.add_column(trace2.id, style="white")
    table.add_column("Match", justify="center")

    def add_row(prop: str, val1: str, val2: str) -> None:
        match = "✓" if val1 == val2 else "✗"
        match_style = "green" if val1 == val2 else "red"
        table.add_row(prop, val1, val2, Text(match, style=match_style))

    # Environment
    if trace1.environment and trace2.environment:
        add_row(
            "Python",
            trace1.environment.python,
            trace2.environment.python,
        )
        add_row(
            "Quantum SDK",
            trace1.environment.quantum_sdk or "-",
            trace2.environment.quantum_sdk or "-",
        )

    # Circuit
    if trace1.circuits and trace2.circuits:
        c1, c2 = trace1.circuits[0], trace2.circuits[0]
        add_row("Circuit qubits", str(c1.num_qubits), str(c2.num_qubits))
        add_row("Circuit depth", str(c1.depth), str(c2.depth))
        add_row("Circuit hash", c1.hash, c2.hash)

    # Hardware
    if trace1.hardware and trace2.hardware:
        add_row("Backend", trace1.hardware.backend, trace2.hardware.backend)
        add_row(
            "Physical qubits",
            str(trace1.hardware.qubits_used),
            str(trace2.hardware.qubits_used),
        )

    # Execution
    if trace1.execution and trace2.execution:
        add_row("Shots", str(trace1.execution.shots), str(trace2.execution.shots))

    console.print(table)

    # Analysis
    if trace1.hardware and trace2.hardware:
        if trace1.hardware.backend != trace2.hardware.backend:
            console.print("\n[yellow]⚠ Different backends may explain result differences[/yellow]")
        elif trace1.hardware.qubits_used != trace2.hardware.qubits_used:
            console.print("\n[yellow]⚠ Different physical qubits may have different error rates[/yellow]")


def generate_paper_statement(trace: Trace) -> str:
    """Generate a reproducibility statement for academic papers."""
    parts = []

    parts.append("[bold]Reproducibility Statement[/bold]\n")
    parts.append("[dim](For Methods section)[/dim]\n")

    sentences = []

    # Software and hardware are one sentence. Joined with a period they read as
    # "using qiskit==2.5.1. on the aer_simulator simulator", and this text is
    # meant to be pasted into a Methods section.
    opening = []
    if trace.environment and trace.environment.quantum_sdk:
        opening.append(f"Experiments were performed using {trace.environment.quantum_sdk}")

    if trace.hardware:
        h = trace.hardware
        if h.is_simulator:
            target = f"the {h.backend} simulator"
        elif h.num_qubits is None:
            # Nothing recorded a qubit count, so the statement does not claim one.
            target = f"the {h.provider} {h.backend} quantum processor"
        else:
            target = f"the {h.provider} {h.backend} quantum processor ({h.num_qubits} qubits)"
        opening.append(f"on {target}" if opening else f"Experiments were performed on {target}")

    if opening:
        sentences.append(" ".join(opening))

    # Transpilation
    if trace.transpilation and trace.transpilation.optimization_level:
        opt_level = trace.transpilation.optimization_level
        sentences.append(f"Circuits were transpiled with optimization level {opt_level}")

    # Execution
    if trace.execution:
        sentences.append(f"Each experiment used {trace.execution.shots:,} shots")

    # Calibration
    if trace.hardware and trace.hardware.calibration:
        cal_time = trace.hardware.calibration.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
        sentences.append(f"Hardware calibration data from {cal_time} was used")

    if sentences:
        statement = ". ".join(sentences) + "."
    else:
        statement = (
            "This trace captured no software, hardware or execution detail, so there "
            "is nothing to state. Import qbom before running your experiment and "
            "check `qbom validate` for what is missing."
        )

    parts.append(statement)
    parts.append("")
    parts.append(f"Complete QBOM trace: [cyan]{trace.id}[/cyan]")
    parts.append(f"Content hash: [dim]{trace.content_hash}[/dim]")

    return "\n".join(parts)


def display_verification(path: Path) -> bool:
    """
    Print what could be established about a QBOM file, and what could not.

    Every line says what was checked and what came of it. A line marked "?" is
    a check that could not run: it establishes nothing and is not counted as a
    pass.

    Returns:
        True when no check failed, so the caller can set the exit code.
    """
    from qbom.core.verification import FAILED, PASSED, verify_file

    report = verify_file(path)

    console.print("[bold]QBOM Verification[/bold]\n")

    markers = {PASSED: ("green", "✓"), FAILED: ("red", "✗")}
    for check in report.checks:
        color, icon = markers.get(check.status, ("yellow", "?"))
        console.print(f"  [{color}]{icon}[/{color}] {check.name}: {check.detail}")

    console.print("")

    if not report.ok:
        failed = ", ".join(check.name for check in report.failures)
        console.print(f"[red bold]VERDICT: verification failed ({failed})[/red bold]")
        return False

    console.print("[green bold]VERDICT: every hash this file records matches the content it carries[/green bold]")

    # What a matching hash does not say. A trace is self-describing, so
    # verification bounds editing after the fact, not what the run did.
    if report.trace is not None and report.trace.circuits:
        console.print(
            "[dim]A circuit hash is taken from the framework's own circuit object, which the trace "
            "does not store, so an individual circuit body is not independently checked.[/dim]"
        )
    if report.unchecked:
        console.print("[dim]Unchecked entries above were not established either way.[/dim]")

    return True
