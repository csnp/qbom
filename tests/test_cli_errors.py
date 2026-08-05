"""
Tests for how the CLI reports things it cannot do.

Every command taking a trace id used to print "Trace not found" and exit 0, so
no script or CI step could tell a missing trace from a healthy one. YAML export
ended in an uncaught ModuleNotFoundError rather than saying what to install.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from qbom.cli.main import main
from qbom.core.session import Session
from qbom.core.trace import Trace, TraceBuilder

# Every command that resolves a trace id. score was the one reported; the
# others had the same defect, reached the same way.
TRACE_ID_COMMANDS = [
    ["show", "no_such_trace"],
    ["export", "no_such_trace", "out.json"],
    ["paper", "no_such_trace"],
    ["score", "no_such_trace"],
    ["drift", "no_such_trace"],
    ["validate", "no_such_trace"],
    ["diff", "no_such_trace", "also_missing"],
]


@pytest.fixture
def trace_store(tmp_path, monkeypatch):
    """Point the session's storage at an empty directory."""
    store = tmp_path / "traces"
    store.mkdir()
    monkeypatch.setattr(Session.get(), "_storage_path", store)
    return store


@pytest.fixture
def saved_trace(trace_store):
    """One real trace on disk, so success paths stay covered too."""
    trace = TraceBuilder().build()
    (trace_store / f"{trace.id}.json").write_text(trace.to_json())
    return trace


@pytest.mark.parametrize("command", TRACE_ID_COMMANDS, ids=lambda c: c[0])
def test_missing_trace_exits_non_zero(trace_store, command):
    result = CliRunner().invoke(main, command)

    assert result.exit_code != 0, f"`qbom {' '.join(command)}` reported success for a trace that does not exist"
    assert "not found" in result.output.lower()


@pytest.mark.parametrize("command", TRACE_ID_COMMANDS, ids=lambda c: c[0])
def test_present_trace_exits_zero(saved_trace, tmp_path, command):
    """
    The complementary case.

    Without it, a helper that raised unconditionally would pass the test above.
    """
    argv = [command[0]] + [saved_trace.id for _ in command[1:]]
    if command[0] == "export":
        argv = ["export", saved_trace.id, str(tmp_path / "out.json")]

    result = CliRunner().invoke(main, argv)

    assert result.exit_code == 0, result.output


def test_yaml_export_without_pyyaml_names_the_fix(saved_trace, tmp_path, monkeypatch):
    """A missing optional serialiser must be a message, not a traceback."""
    import builtins

    real_import = builtins.__import__

    def refuse_yaml(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("No module named 'yaml'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse_yaml)

    result = CliRunner().invoke(main, ["export", saved_trace.id, str(tmp_path / "out.yaml"), "-f", "yaml"])

    assert result.exit_code != 0
    assert "PyYAML" in result.output
    assert 'pip install "qbom[yaml]"' in result.output
    assert "Traceback" not in result.output


def test_damaged_trace_file_is_reported(trace_store):
    """A truncated file on disk is a message, not a pydantic traceback."""
    (trace_store / "qbom_damaged.json").write_text('{"id": "qbom_damaged", "created_at":')

    result = CliRunner().invoke(main, ["show", "qbom_damaged"])

    assert result.exit_code != 0
    assert "not a readable QBOM trace" in result.output


# Each id here has a real, readable file behind it, so removing the guard makes
# the resolver find something. An id whose target does not exist would pass
# whether or not the guard is there, and would prove nothing.
ESCAPES = [
    ("../outside", lambda store: store.parent / "outside.json"),
    ("sub/nested", lambda store: store / "sub" / "nested.json"),
]


@pytest.mark.parametrize("trace_id,target_for", ESCAPES, ids=[e[0] for e in ESCAPES])
def test_trace_id_cannot_address_a_file_outside_the_store(trace_store, trace_id, target_for):
    """
    A trace id is joined onto the storage path, so it must be one component.

    Without this, `qbom show ../../../etc/hosts` read and tried to parse that
    path.
    """
    target = target_for(trace_store)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(Trace(id="qbom_outside").to_json())

    # Premise: the path this id names is real and loadable, so a resolver that
    # walks there succeeds. If this ever stops holding, the test below silently
    # stops measuring the guard.
    assert target.exists()
    assert Trace.model_validate_json(target.read_text()).id == "qbom_outside"

    result = CliRunner().invoke(main, ["show", trace_id])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


@pytest.mark.parametrize("trace_id", ["", ".", "..", "back\\slash", "nul\x00byte"])
def test_malformed_trace_ids_are_refused(trace_store, trace_id):
    """Shapes that are not a filename component, refused before any lookup."""
    from qbom.cli.main import _resolve_trace_path

    assert _resolve_trace_path(trace_id) is None


def test_ordinary_ids_still_resolve(trace_store):
    """
    The complementary case.

    Both tests above would pass against a resolver that returned None for
    everything.
    """
    from qbom.cli.main import _resolve_trace_path

    trace = Trace(id="qbom_ordinary")
    (trace_store / f"{trace.id}.json").write_text(trace.to_json())

    assert _resolve_trace_path("qbom_ordinary") is not None
    assert _resolve_trace_path("ordinary") is not None  # partial ids keep working


def test_partial_id_resolves_to_the_first_match_in_order(trace_store):
    """
    Two traces sharing a prefix must resolve to the same one on every machine.

    The lookup used to take whatever glob() returned first, which is filesystem
    order. Written out of order on purpose so insertion order and sorted order
    disagree.
    """
    for suffix in ("bbb", "aaa", "ccc"):
        trace = Trace(id=f"qbom_shared_{suffix}")
        (trace_store / f"{trace.id}.json").write_text(trace.to_json())

    from qbom.cli.main import _resolve_trace_path

    resolved = _resolve_trace_path("qbom_shared")

    assert resolved is not None
    assert resolved.stem == "qbom_shared_aaa"
