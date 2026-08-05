"""
QBOM CLI

Beautiful command-line interface for managing quantum experiment traces.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import click
from rich.console import Console

if TYPE_CHECKING:
    from qbom.core.trace import Trace

console = Console()


def _resolve_trace_path(trace_id: str) -> Path | None:
    """Find the file backing a trace id, accepting a unique prefix."""
    from qbom.core.session import Session

    session = Session.get()
    path = session._storage_path / f"{trace_id}.json"
    if path.exists():
        return path

    # Fall back to a partial id. Sorted so the same input always resolves to
    # the same trace, whatever order the filesystem hands the entries back.
    for candidate in sorted(session._storage_path.glob("*.json")):
        if trace_id in candidate.stem:
            return candidate

    return None


def _load_trace(trace_id: str) -> Trace:
    """
    Load a trace or exit non-zero.

    Every command that takes a trace id used to print "Trace not found" and
    return, which left the exit code at 0 and made the failure invisible to any
    script or CI step calling qbom.
    """
    path = _resolve_trace_path(trace_id)
    if path is None:
        raise click.ClickException(f"Trace not found: {trace_id}")

    return _read_trace_file(path)


def _read_trace_file(path: Path) -> Trace:
    """Parse a QBOM file, reporting a damaged one instead of raising."""
    from qbom.core.trace import Trace

    try:
        return Trace.model_validate_json(path.read_text())
    except OSError as exc:
        raise click.ClickException(f"Could not read {path}: {exc}") from exc
    except ValueError as exc:
        raise click.ClickException(
            f"{path} is not a readable QBOM trace. It may be truncated or from an incompatible version.\n{exc}"
        ) from exc


@click.group()
@click.version_option(message="QBOM %(version)s")
def main() -> None:
    """
    QBOM: Quantum Bill of Materials

    Invisible provenance capture for quantum computing experiments.

    https://github.com/csnp/qbom
    """
    pass


@main.command()
@click.option("-n", "--limit", default=10, help="Number of traces to show")
def list(limit: int) -> None:
    """List recent experiment traces."""
    from qbom.cli.display import display_trace_list
    from qbom.core.session import Session

    session = Session.get()
    traces = session.list_traces(limit=limit)

    if not traces:
        console.print("[dim]No traces found. Run a quantum experiment with QBOM imported.[/dim]")
        return

    display_trace_list(traces)


@main.command()
@click.argument("trace_id")
def show(trace_id: str) -> None:
    """Show detailed view of a trace."""
    from qbom.cli.display import display_trace

    display_trace(_load_trace(trace_id))


@main.command()
@click.argument("trace_id")
@click.argument("output", type=click.Path())
@click.option(
    "-f",
    "--format",
    type=click.Choice(["json", "cyclonedx", "spdx", "yaml"]),
    default="json",
    help="Export format (json, cyclonedx, spdx, yaml)",
)
def export(trace_id: str, output: str, format: str) -> None:
    """Export a trace to a file.

    Supported formats:
    - json: Native QBOM format (default)
    - cyclonedx: CycloneDX 1.5 SBOM with QBOM extension
    - spdx: SPDX 2.3 SBOM with QBOM extension
    - yaml: YAML representation
    """
    trace = _load_trace(trace_id)

    try:
        output_path = trace.export(output, format=format)  # type: ignore
    except ImportError as exc:
        # An optional serialiser is missing. Say which and how to get it,
        # rather than ending in a traceback.
        raise click.ClickException(str(exc)) from exc

    console.print(f"[green]Exported to:[/green] {output_path}")


@main.command()
@click.argument("trace_id1")
@click.argument("trace_id2")
def diff(trace_id1: str, trace_id2: str) -> None:
    """Compare two traces side by side."""
    from qbom.cli.display import display_diff

    display_diff(_load_trace(trace_id1), _load_trace(trace_id2))


@main.command()
@click.argument("trace_id")
def paper(trace_id: str) -> None:
    """Generate reproducibility statement for a paper."""
    from qbom.cli.display import generate_paper_statement

    console.print(generate_paper_statement(_load_trace(trace_id)))


@main.command()
@click.argument("path", type=click.Path(exists=True))
def verify(path: str) -> None:
    """Verify integrity of a QBOM file."""
    from qbom.cli.display import display_verification

    display_verification(_read_trace_file(Path(path)), path)


@main.command()
def init() -> None:
    """Initialize QBOM in the current project."""
    console.print("[bold]QBOM Initialization[/bold]\n")
    console.print("Add this to your Python scripts or notebooks:\n")
    console.print("[cyan]import qbom  # That's it![/cyan]\n")
    console.print("Your experiments will be automatically captured.")
    console.print("Traces stored in: [dim]~/.qbom/traces/[/dim]")


@main.command()
@click.argument("trace_id")
def score(trace_id: str) -> None:
    """Show reproducibility score for a trace.

    Computes a 0-100 score indicating how reproducible an experiment is:
    - 90-100: Excellent - Fully reproducible
    - 70-89:  Good - Minor details missing
    - 50-69:  Fair - Some important info missing
    - 25-49:  Poor - Major gaps in documentation
    - 0-24:   Critical - Cannot reproduce
    """
    from rich.panel import Panel
    from rich.table import Table

    from qbom.analysis import compute_score

    trace = _load_trace(trace_id)
    result = compute_score(trace)

    # Display score
    grade_colors = {
        "Excellent": "green",
        "Good": "blue",
        "Fair": "yellow",
        "Poor": "orange1",
        "Critical": "red",
    }
    color = grade_colors.get(result.grade, "white")

    console.print()
    console.print(
        Panel(
            f"[bold {color}]{result.total_score}/{result.max_score}[/bold {color}] ([{color}]{result.grade}[/{color}])",
            title="Reproducibility Score",
            subtitle=trace.id,
        )
    )

    # Component breakdown
    table = Table(title="Score Breakdown", show_header=True)
    table.add_column("Component", style="cyan")
    table.add_column("Category", style="dim")
    table.add_column("Score", justify="right")
    table.add_column("Status")

    status_icons = {"complete": "[green]●[/green]", "partial": "[yellow]◐[/yellow]", "missing": "[red]○[/red]"}

    for component in result.components:
        status_icon = status_icons.get(component.status, "?")
        table.add_row(
            component.name,
            component.category,
            f"{component.earned_points}/{component.max_points}",
            status_icon,
        )

    console.print(table)

    # Recommendations
    if result.recommendations:
        console.print("\n[bold]Recommendations:[/bold]")
        for rec in result.recommendations:
            console.print(f"  • {rec}")

    console.print()


@main.command()
@click.argument("trace_id")
def drift(trace_id: str) -> None:
    """Analyze calibration drift for a trace.

    Shows how hardware calibration may have changed since the experiment ran.
    This helps understand why reproduction attempts might produce different results.
    """
    from rich.panel import Panel
    from rich.table import Table

    from qbom.analysis import analyze_drift

    trace = _load_trace(trace_id)
    result = analyze_drift(trace)

    if result is None:
        console.print("[yellow]No hardware information available for drift analysis.[/yellow]")
        return

    # Display drift analysis
    feasibility_colors = {
        "High": "green",
        "Medium": "yellow",
        "Low": "orange1",
        "Very Low": "red",
    }
    color = feasibility_colors.get(result.reproduction_feasibility, "white")

    console.print()
    console.print(
        Panel(
            f"Drift Score: [bold]{result.overall_drift_score:.0f}/100[/bold]\n"
            f"Reproduction Feasibility: [bold {color}]{result.reproduction_feasibility}[/bold {color}]",
            title="Calibration Drift Analysis",
            subtitle=trace.id,
        )
    )

    # Time information
    if result.time_elapsed:
        days = result.time_elapsed.days
        if days > 0:
            console.print(f"\n[dim]Time since calibration: {days} days[/dim]")
        else:
            hours = result.time_elapsed.seconds // 3600
            console.print(f"\n[dim]Time since calibration: {hours} hours[/dim]")

    # Qubit drift table
    if result.qubit_drift:
        table = Table(title="Qubit Drift", show_header=True)
        table.add_column("Qubit", justify="right")
        table.add_column("T1 Change", justify="right")
        table.add_column("T2 Change", justify="right")
        table.add_column("Readout Change", justify="right")
        table.add_column("Status")

        for qd in result.qubit_drift:
            status = "[red]Drift[/red]" if qd.has_significant_drift else "[green]Stable[/green]"
            table.add_row(
                str(qd.qubit_index),
                f"{qd.t1_change_percent:+.1f}%" if qd.t1_change_percent else "-",
                f"{qd.t2_change_percent:+.1f}%" if qd.t2_change_percent else "-",
                f"{qd.readout_change_percent:+.1f}%" if qd.readout_change_percent else "-",
                status,
            )
        console.print(table)

    # Gate drift table
    if result.gate_drift:
        table = Table(title="Gate Drift", show_header=True)
        table.add_column("Gate")
        table.add_column("Qubits")
        table.add_column("Error Change", justify="right")
        table.add_column("Status")

        for gd in result.gate_drift:
            status = "[red]Drift[/red]" if gd.has_significant_drift else "[green]Stable[/green]"
            table.add_row(
                gd.gate_name,
                str(list(gd.qubits)),
                f"{gd.error_change_percent:+.1f}%" if gd.error_change_percent else "-",
                status,
            )
        console.print(table)

    # Recommendations
    if result.recommendations:
        console.print("\n[bold]Recommendations:[/bold]")
        for rec in result.recommendations:
            console.print(f"  • {rec}")

    console.print()


@main.command()
@click.argument("trace_id")
@click.option(
    "--publication",
    is_flag=True,
    help="Use stricter validation for publication",
)
def validate(trace_id: str, publication: bool) -> None:
    """Validate a trace for completeness.

    Checks that all required information is captured and provides
    guidance on how to fix any issues found.

    Use --publication for stricter checks when preparing for publication.
    """
    from rich.panel import Panel

    from qbom.analysis import ValidationLevel, validate_for_publication, validate_trace

    trace = _load_trace(trace_id)

    if publication:
        result = validate_for_publication(trace)
        title = "Publication Validation"
    else:
        result = validate_trace(trace)
        title = "Trace Validation"

    # Display result
    if result.is_complete:
        status_color = "green"
        status_text = "PASS"
    elif result.is_valid:
        status_color = "yellow"
        status_text = "WARNINGS"
    else:
        status_color = "red"
        status_text = "FAIL"

    console.print()
    console.print(
        Panel(
            f"[bold {status_color}]{status_text}[/bold {status_color}]\n\n{result.summary}",
            title=title,
            subtitle=trace.id,
        )
    )

    # Show issues by category
    if result.issues:
        # Group by category
        categories: dict[str, list] = {}
        for issue in result.issues:
            if issue.category not in categories:
                categories[issue.category] = []
            categories[issue.category].append(issue)

        for category, issues in categories.items():
            console.print(f"\n[bold]{category}:[/bold]")
            for issue in issues:
                level_colors = {
                    ValidationLevel.ERROR: "red",
                    ValidationLevel.WARNING: "yellow",
                    ValidationLevel.INFO: "dim",
                }
                color = level_colors.get(issue.level, "white")
                console.print(f"  [{color}]{issue.icon}[/{color}] {issue.message}")
                console.print(f"    [dim]Fix: {issue.fix}[/dim]")

    # Summary counts
    console.print()
    console.print(
        f"[red]{result.error_count} errors[/red] | "
        f"[yellow]{result.warning_count} warnings[/yellow] | "
        f"[dim]{result.info_count} info[/dim]"
    )
    console.print()


if __name__ == "__main__":
    main()
