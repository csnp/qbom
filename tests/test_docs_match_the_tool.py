"""
Every command, option, import and attribute the documentation shows must exist.

A reader copies these. The docs said a trace id could be a path to a trace
file, showed `qbom list --tag benchmark`, and documented `calculate_score` and
`validate_trace(trace, publication=True)` in qbom.analysis. None of those exist,
so each one ended in an error rather than a result, and nothing else in the
suite noticed: to every other test the docs are prose.

This walks the reader-facing docs, pulls out each cited `qbom` invocation, each
qbom import, each `trace.<attribute>` chain and each name in the API reference,
and checks it against the real CLI and package. The qbom.analysis snippets are
run, not just parsed. A change to the CLI or the API that leaves a doc behind
fails here rather than in a reader's terminal.
"""

from __future__ import annotations

import importlib
import inspect
import re
import shlex
import types
import typing
from dataclasses import dataclass
from pathlib import Path

import click
import pytest

import qbom
from qbom.cli.main import main
from qbom.core import models
from qbom.core import trace as trace_module
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
from qbom.core.session import Session
from qbom.core.timeutil import utc_now
from qbom.core.trace import Trace

REPO_ROOT = Path(__file__).resolve().parents[1]

# The docs a reader follows. CHANGELOG.md is left out because it names removed
# and broken forms on purpose, to say they were removed or broken.
# docs/plans and docs/proposals record designs, some never built, so a command
# named there is not a claim that it exists.
DOCS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "CONTRIBUTING.md",
    *sorted((REPO_ROOT / "docs").glob("*.md")),
    *sorted((REPO_ROOT / "docs" / "testing").glob("*.md")),
]

FENCE = re.compile(r"^```([^\n]*)\n(.*?)^```", re.MULTILINE | re.DOTALL)
INLINE_INVOCATION = re.compile(r"`(qbom [^`\n]+)`")
# A shell prompt, or a prompt inside a comment ("# $ qbom paper ..."), before a command.
PROMPT = re.compile(r"^\s*(?:#\s*)?(?:\$\s+)?")
# <trace-id>, <id1>, <file>: a placeholder the reader fills in.
PLACEHOLDER = re.compile(r"<([A-Za-z0-9_-]+)>")
# [OPTIONS], [ARGS]...: optional parts of a synopsis.
OPTIONAL_GROUP = re.compile(r"^\[[^\]]*\](?:\.\.\.)?$")
SHELL_OPERATOR_CHARS = set("();<>|&")


@dataclass(frozen=True)
class Citation:
    where: str
    text: str


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _where(source: Path, line: int) -> str:
    return f"{source.relative_to(REPO_ROOT)}:{line}"


def _fenced_blocks() -> list[tuple[Path, int, str, str]]:
    """(source, first line, language, body) for every fenced code block."""
    blocks = []
    for source in DOCS:
        text = source.read_text()
        for block in FENCE.finditer(text):
            blocks.append((source, _line_of(text, block.start(2)), block.group(1).strip().lower(), block.group(2)))
    return blocks


def _invocations() -> list[tuple[Citation, bool]]:
    """
    Every `qbom ...` command the docs show, and whether it is a full invocation.

    A command on its own line in a code block is one a reader runs, so it must
    parse completely. A command named inline in prose may be a reference to the
    command ("`qbom diff` compares..."), so its arguments may be left out, but
    the command and every option it names must still exist.
    """
    found: list[tuple[Citation, bool]] = []
    for source, first_line, _language, body in _fenced_blocks():
        for offset, line in enumerate(body.splitlines()):
            command = PROMPT.sub("", line, count=1)
            if command.startswith("qbom "):
                found.append((Citation(_where(source, first_line + offset), command), True))

    for source in DOCS:
        text = source.read_text()
        # Blank the fenced blocks, keeping their newlines so line numbers hold.
        prose = FENCE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
        for match in INLINE_INVOCATION.finditer(prose):
            found.append((Citation(_where(source, _line_of(prose, match.start())), match.group(1)), False))
    return found


def _argv(command: str) -> list[str]:
    """The arguments a shell would hand qbom, without comments, pipes or redirects."""
    # In the summary listings a run of spaces separates a command from its
    # description ("qbom list          List recent traces").
    command = re.split(r"\s{2,}", command.strip(), maxsplit=1)[0]
    lexer = shlex.shlex(PLACEHOLDER.sub(r"\1", command), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    argv: list[str] = []
    for token in lexer:
        if set(token) <= SHELL_OPERATOR_CHARS:
            break
        if not OPTIONAL_GROUP.match(token):
            argv.append(token)
    assert argv[:1] == ["qbom"], f"not a qbom command: {command!r}"
    return argv[1:]


def _parse(argv: list[str], *, full: bool) -> click.Context | None:
    """
    Resolve argv against the real CLI without running anything.

    Returns the command's context, or None when the line asks only for
    --version or --help. Raises click's own error when click would refuse it.
    """
    root = click.Context(main, info_name="qbom")
    if argv[:1] == ["COMMAND"]:
        # The generic synopsis, `qbom [OPTIONS] COMMAND [ARGS]...`.
        return None
    if not argv or argv[0].startswith("-"):
        try:
            main.make_context("qbom", argv)
        except click.exceptions.Exit:
            return None
        raise AssertionError(f"`qbom {' '.join(argv)}` names no command")

    command = main.get_command(root, argv[0])
    if command is None:
        raise click.UsageError(f"No such command '{argv[0]}'.")
    try:
        return command.make_context(argv[0], argv[1:], parent=root)
    except click.exceptions.Exit:
        return None
    except click.MissingParameter:
        if full:
            raise
        return None
    except click.BadParameter as exc:
        # `qbom verify FILE` checks that FILE exists. The file is the reader's
        # own, so its absence here says nothing about the docs.
        param_type = getattr(exc.param, "type", None)
        if isinstance(param_type, click.Path) and param_type.exists:
            return None
        raise


INVOCATIONS = _invocations()


@pytest.mark.parametrize("citation,full", INVOCATIONS, ids=[f"{c.where} {c.text}" for c, _ in INVOCATIONS])
def test_documented_invocation_parses(citation, full):
    try:
        ctx = _parse(_argv(citation.text), full=full)
    except click.ClickException as exc:
        pytest.fail(f"{citation.where}: `{citation.text}` is refused by the CLI: {exc.format_message()}")

    if ctx is None:
        return
    # A trace id is joined onto the trace store as one filename component, so a
    # path is never accepted where an id is. Only `qbom verify` reads a file.
    for name, value in ctx.params.items():
        if name.startswith("trace_id") and isinstance(value, str):
            assert "/" not in value and not value.endswith(".json"), (
                f"{citation.where}: `{citation.text}` passes the file {value!r} where the CLI takes a trace id"
            )


def test_invocation_scan_found_the_commands():
    """Guard the premise: a scan that finds nothing passes vacuously."""
    commands = {_argv(c.text)[0] for c, _ in INVOCATIONS if _argv(c.text)}
    assert set(main.commands) <= commands, f"docs never show {sorted(set(main.commands) - commands)}"


# ---------------------------------------------------------------------------
# Installation and environment
# ---------------------------------------------------------------------------

PIP_INSTALL = re.compile(r"pip install ([^`\n]*)")
# qbom, "qbom[yaml]", qbom==0.1.1: a requirement pip would look up on an index.
INDEX_REQUIREMENT = re.compile(r"^qbom(?:\[[\w,]+\])?(?:[<>=!~].*)?$")
ENVIRONMENT_VARIABLE = re.compile(r"\bQBOM_[A-Z][A-Z0-9_]*\b")


def _doc_lines() -> list[tuple[str, str]]:
    return [
        (_where(source, number), line)
        for source in DOCS
        for number, line in enumerate(source.read_text().splitlines(), start=1)
    ]


def test_docs_install_qbom_from_the_checkout():
    """
    qbom is not published on a package index, so `pip install qbom` fails.

    Every install the docs show is an editable install from a clone, and a
    single line that sends a reader to an index is a dead end.
    """
    from_index = []
    for where, line in _doc_lines():
        for match in PIP_INSTALL.finditer(line):
            try:
                tokens = shlex.split(match.group(1), comments=True)
            except ValueError:
                tokens = match.group(1).split()
            from_index += [f"{where}: {line.strip()}" for token in tokens if INDEX_REQUIREMENT.match(token)]
    assert not from_index, "docs install qbom from a package index:\n" + "\n".join(from_index)


def test_documented_environment_variables_are_read():
    source = "\n".join(path.read_text() for path in sorted((REPO_ROOT / "src").rglob("*.py")))
    unread = [
        f"{where}: {name}"
        for where, line in _doc_lines()
        for name in ENVIRONMENT_VARIABLE.findall(line)
        if name not in source
    ]
    assert not unread, "docs name environment variables qbom never reads:\n" + "\n".join(unread)


# ---------------------------------------------------------------------------
# Python snippets
# ---------------------------------------------------------------------------

IMPORT_FROM = re.compile(r"^\s*from (qbom(?:\.\w+)*) import ([^\n#(]+)", re.MULTILINE)
IMPORT_MODULE = re.compile(r"^\s*import (qbom(?:\.\w+)*)\s*$", re.MULTILINE)
# trace.hardware.backend, {trace.id}; not "trace.json" or my_trace.json.
TRACE_CHAIN = re.compile(r"(?<![\w\"'/.-])trace((?:\.[A-Za-z_]\w*)+)")


def _python_blocks() -> list[Citation]:
    return [
        Citation(_where(source, first_line), body)
        for source, first_line, language, body in _fenced_blocks()
        if language in ("python", "py")
    ]


PYTHON_BLOCKS = _python_blocks()


def _imports() -> list[tuple[Citation, str, str | None]]:
    found = []
    for block in PYTHON_BLOCKS:
        for match in IMPORT_FROM.finditer(block.text):
            for name in match.group(2).split(","):
                found.append((block, match.group(1), name.split(" as ")[0].strip()))
        for match in IMPORT_MODULE.finditer(block.text):
            found.append((block, match.group(1), None))
    return found


IMPORTS = _imports()


@pytest.mark.parametrize(
    "block,module,name", IMPORTS, ids=[f"{b.where} {m}.{n}" if n else f"{b.where} {m}" for b, m, n in IMPORTS]
)
def test_documented_import_resolves(block, module, name):
    loaded = importlib.import_module(module)
    if name is None or hasattr(loaded, name):
        return
    try:
        importlib.import_module(f"{module}.{name}")
    except ModuleNotFoundError:
        pytest.fail(f"{block.where}: `from {module} import {name}` fails, {module} has no {name}")


def _unwrap(annotation: object) -> type | None:
    """X | None to X. Anything that is not a plain class ends the walk."""
    if typing.get_origin(annotation) in (typing.Union, types.UnionType):
        members = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(members) == 1:
            annotation = members[0]
    if typing.get_origin(annotation) is None and isinstance(annotation, type):
        return annotation
    return None


def _attribute_type(owner: type, name: str) -> type | None:
    """
    The type of owner.name, or None when it cannot be followed further.

    Raises AttributeError when owner has no such attribute.
    """
    fields = getattr(owner, "model_fields", {})
    computed = getattr(owner, "model_computed_fields", {})
    if name in fields:
        return _unwrap(fields[name].annotation)
    if name in computed:
        return _unwrap(computed[name].return_type)
    attribute = inspect.getattr_static(owner, name)
    if isinstance(attribute, property) and attribute.fget is not None:
        try:
            return _unwrap(typing.get_type_hints(attribute.fget).get("return"))
        except NameError:
            return None
    return None


def _trace_chains() -> list[tuple[Citation, str]]:
    return [(block, f"trace{match.group(1)}") for block in PYTHON_BLOCKS for match in TRACE_CHAIN.finditer(block.text)]


TRACE_CHAINS = _trace_chains()


@pytest.mark.parametrize("block,chain", TRACE_CHAINS, ids=[f"{b.where} {c}" for b, c in TRACE_CHAINS])
def test_documented_trace_attribute_exists(block, chain):
    owner: type | None = Trace
    walked = "trace"
    for name in chain.split(".")[1:]:
        if owner is None:
            return
        try:
            owner = _attribute_type(owner, name)
        except AttributeError:
            pytest.fail(f"{block.where}: `{chain}` does not exist, {walked} has no attribute {name!r}")
        walked = f"{walked}.{name}"


def test_python_scans_found_something():
    assert any(module == "qbom.analysis" for _, module, _ in IMPORTS)
    assert len(TRACE_CHAINS) >= 10, f"expected the docs to read many trace attributes, found {len(TRACE_CHAINS)}"


# ---------------------------------------------------------------------------
# The API reference
# ---------------------------------------------------------------------------

API_DOC = REPO_ROOT / "docs" / "API.md"
SECTION = re.compile(r"^## (Module|Class): ([\w.]+)")
CALLABLE_HEADING = re.compile(r"^#{3,4} ([\w.]+)\(\)")
PROPERTY_ROW = re.compile(r"^\| `(\w+)` \|")
# What the dotted headings ("trace.export()", "session.list_traces()") are called on.
RECEIVERS = {"qbom": qbom, "trace": Trace, "session": Session, "Session": Session}


def _api_reference_names() -> list[tuple[str, object, str]]:
    """(where, owner, name) for every function, method and property API.md documents."""
    found = []
    owner: object = None
    for number, line in enumerate(API_DOC.read_text().splitlines(), start=1):
        where = _where(API_DOC, number)
        if section := SECTION.match(line):
            kind, name = section.groups()
            if kind == "Module":
                owner = importlib.import_module(name)
            else:
                owner = getattr(models, name, None) or getattr(trace_module, name)
        elif heading := CALLABLE_HEADING.match(line):
            *receiver, name = heading.group(1).split(".")
            found.append((where, RECEIVERS[receiver[-1]] if receiver else owner, name))
        elif (row := PROPERTY_ROW.match(line)) and isinstance(owner, type):
            found.append((where, owner, row.group(1)))
    return found


API_NAMES = _api_reference_names()


@pytest.mark.parametrize("where,owner,name", API_NAMES, ids=[f"{w} {n}" for w, _, n in API_NAMES])
def test_api_reference_name_exists(where, owner, name):
    label = getattr(owner, "__name__", repr(owner))
    if isinstance(owner, type):
        try:
            _attribute_type(owner, name)
        except AttributeError:
            pytest.fail(f"{where}: API.md documents {label}.{name}, which does not exist")
    else:
        assert hasattr(owner, name), f"{where}: API.md documents {label}.{name}(), which does not exist"


def test_api_reference_scan_covers_analysis():
    analysis = importlib.import_module("qbom.analysis")
    assert {name for _, owner, name in API_NAMES if owner is analysis} >= {"compute_score", "analyze_drift"}


# ---------------------------------------------------------------------------
# The qbom.analysis snippets, run as written
# ---------------------------------------------------------------------------


def _captured_trace() -> Trace:
    """A trace with every section filled, including a calibration to drift from."""
    circuit = Circuit(num_qubits=2, depth=3, gates=GateCounts(single_qubit=1, two_qubit=1, total=2), hash="c0")
    return Trace(
        environment=Environment(python="3.11.0", platform="test", packages=[Package(name="qiskit", version="1.0.0")]),
        circuits=[circuit],
        transpilation=Transpilation(
            optimization_level=2, seed=7, basis_gates=["cx", "rz"], input_circuit=circuit, output_circuit=circuit
        ),
        hardware=Hardware(
            provider="IBM Quantum",
            backend="ibm_test",
            num_qubits=2,
            qubits_used=[0, 1],
            calibration=Calibration(
                timestamp=utc_now(),
                qubits=[QubitProperties(index=0, t1_us=100.0, t2_us=80.0, readout_error=0.01)],
                gates=[GateProperties(gate="cx", qubits=(0, 1), error=0.01, duration_ns=300.0)],
            ),
        ),
        execution=Execution(shots=1024, job_id="job-1", submitted_at=utc_now(), completed_at=utc_now()),
        result=Result(counts=Counts(raw={"00": 512, "11": 512}, shots=1024), hash="r0"),
    )


ANALYSIS_SNIPPETS = [block for block in PYTHON_BLOCKS if "from qbom.analysis import" in block.text]
TRACES = {"captured": _captured_trace, "empty": Trace}


@pytest.mark.parametrize("kind", sorted(TRACES))
@pytest.mark.parametrize("block", ANALYSIS_SNIPPETS, ids=[b.where for b in ANALYSIS_SNIPPETS])
def test_analysis_snippet_runs(block, kind, monkeypatch, capsys):
    """
    Run each snippet against a full trace and an empty one.

    The snippets either take `trace` as given or call qbom.current(), so both
    are supplied. The empty trace has no hardware, which is the case
    analyze_drift answers with None; a snippet that reads through that None
    fails a reader whose trace recorded none.
    """
    trace = TRACES[kind]()
    monkeypatch.setattr(qbom, "current", lambda: trace)
    try:
        exec(compile(block.text, block.where, "exec"), {"qbom": qbom, "trace": trace})
    except Exception as exc:  # any error is the finding
        pytest.fail(f"{block.where} fails as written on a {kind} trace: {type(exc).__name__}: {exc}")
    capsys.readouterr()


def test_analysis_snippets_were_found():
    sources = {block.where.split(":")[0] for block in ANALYSIS_SNIPPETS}
    assert sources >= {"docs/API.md", "docs/USAGE.md"}, sources
