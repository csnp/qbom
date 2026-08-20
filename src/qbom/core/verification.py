"""
Checking a QBOM file against the hashes it records.

A trace carries two independent hashes, and they cover different things.

The content hash covers the circuits, the transpilation, the backend, the
qubits used, the shot count, the seed and the recorded result hash. It is a
computed property, so it is recalculated from the loaded trace and compared
against the copy serialised in the file. That catches an edited shot count or
an edited backend name.

The result hash covers the measurement counts. The content hash covers the
result hash but not the counts themselves, so counts can be rewritten without
moving the content hash. Recomputing the result hash from the stored counts is
the only thing that catches that, and neither check substitutes for the other.

Two limits are reported rather than glossed over. A result that is not counts,
an expectation value for instance, is hashed over a value the trace does not
store, so its hash cannot be recomputed and is reported as unchecked rather
than as verified. And a circuit hash is taken from the framework's own circuit
object, which the trace does not carry either, so an individual circuit body is
not independently checked.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from qbom.core.hashing import result_hash
from qbom.core.timeutil import as_utc
from qbom.core.trace import Trace

#: The check established what it names.
PASSED = "passed"
#: The check ran and the file did not satisfy it.
FAILED = "failed"
#: The check could not run, and nothing about it was established.
UNCHECKED = "unchecked"

# Each name says what was compared against what, because each of these checks
# now recomputes a value rather than testing that a field is present.
STRUCTURE = "QBOM document structure"
CONTENT_HASH = "Content hash against trace content"
RESULT_HASH = "Result hash against recorded counts"
TIMESTAMPS = "Execution timestamp order"

# Written by every exporter, on every trace. `id` alone is too common a key to
# identify a document by, and a Trace parses from `{}` because every field has
# a default, so a model parse establishes nothing on its own.
REQUIRED_KEYS = ("qbom_version", "id")


@dataclass(frozen=True)
class Check:
    """One thing verification tried to establish, and what came of it."""

    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class VerificationReport:
    """The outcome of checking one file."""

    checks: tuple[Check, ...]
    trace: Trace | None = None

    @property
    def failures(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if c.status == FAILED)

    @property
    def unchecked(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if c.status == UNCHECKED)

    @property
    def ok(self) -> bool:
        """True when nothing failed. Unchecked entries are not failures."""
        return not self.failures


def _rejected(detail: str) -> VerificationReport:
    """A document that is not a QBOM trace. Nothing further can be checked."""
    return VerificationReport(checks=(Check(STRUCTURE, FAILED, detail),))


def verify_file(path: Path) -> VerificationReport:
    """Check the QBOM file at ``path``. An unreadable file is a failure."""
    try:
        text = path.read_text()
    except OSError as exc:
        return _rejected(f"{path} could not be read: {exc}")

    return verify_document(text)


def verify_document(text: str) -> VerificationReport:
    """Check one QBOM document, given as text."""
    try:
        raw = json.loads(text)
    except ValueError as exc:
        return _rejected(f"not JSON: {exc}")

    if not isinstance(raw, dict):
        return _rejected(f"the top level is a JSON {type(raw).__name__}, and a QBOM trace is an object")

    missing = [key for key in REQUIRED_KEYS if not _non_empty_string(raw.get(key))]
    if missing:
        return _rejected(f"no {' and no '.join(missing)}, so this is not a QBOM trace")

    try:
        trace = Trace.model_validate_json(text)
    except ValueError as exc:
        return _rejected(f"the fields do not parse as a QBOM trace: {exc}")

    checks = [
        Check(STRUCTURE, PASSED, f"QBOM {raw['qbom_version']} trace {raw['id']}"),
        _check_content_hash(raw, trace),
        _check_result_hash(trace),
        _check_timestamps(trace),
    ]
    return VerificationReport(checks=tuple(checks), trace=trace)


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and value != ""


def _check_content_hash(raw: dict[str, Any], trace: Trace) -> Check:
    """
    Compare the content hash the file records against the trace's own.

    A file recording no content hash fails rather than skipping the check.
    Deleting the field is indistinguishable from never having written one, and
    every trace QBOM has written carries it, so an absent value is treated as
    the tampering it would otherwise be a way around.
    """
    stored = raw.get("content_hash")
    recomputed = trace.content_hash

    if not _non_empty_string(stored):
        return Check(
            CONTENT_HASH,
            FAILED,
            f"the file records no content hash, so there is nothing to check {recomputed} against",
        )

    if stored == recomputed:
        return Check(CONTENT_HASH, PASSED, f"matches, {recomputed}")

    return Check(
        CONTENT_HASH,
        FAILED,
        f"the file records {stored}, its content hashes to {recomputed}. "
        "Circuits, transpilation, backend, qubits used, shots, seed or the recorded result hash "
        "changed after this trace was written",
    )


def _check_result_hash(trace: Trace) -> Check:
    """Recompute the result hash from the stored counts and compare."""
    result = trace.result
    if result is None:
        return Check(RESULT_HASH, UNCHECKED, "this trace records no result")

    counts = result.counts.raw
    if not counts:
        return Check(
            RESULT_HASH,
            UNCHECKED,
            f"the recorded hash {result.hash} was taken over a result that is not counts, "
            "which the trace does not store, so it cannot be recomputed here",
        )

    recomputed = result_hash(counts)
    if recomputed == result.hash:
        return Check(RESULT_HASH, PASSED, f"matches, {recomputed} over {len(counts)} outcomes")

    return Check(
        RESULT_HASH,
        FAILED,
        f"the file records {result.hash}, its counts hash to {recomputed}. "
        "The measurement outcomes changed after this trace was written",
    )


def _check_timestamps(trace: Trace) -> Check:
    """
    Check the execution timestamps run forwards.

    Timestamps are not covered by either hash, so this establishes only that
    the recorded times are self-consistent.
    """
    execution = trace.execution
    if execution is None:
        return Check(TIMESTAMPS, UNCHECKED, "this trace records no execution")

    stamps: list[tuple[str, datetime]] = [
        (name, value)
        for name, value in (
            ("submitted_at", execution.submitted_at),
            ("started_at", execution.started_at),
            ("completed_at", execution.completed_at),
        )
        if value is not None
    ]

    if len(stamps) < 2:
        recorded = stamps[0][0] if stamps else "none"
        return Check(TIMESTAMPS, UNCHECKED, f"one timestamp or fewer to order (recorded: {recorded})")

    # as_utc reads an offset-free timestamp as UTC, which is what traces
    # written before offsets were recorded contain. One file can hold both.
    out_of_order = [
        f"{later} is before {earlier}"
        for (earlier, earlier_at), (later, later_at) in zip(stamps, stamps[1:])
        if as_utc(earlier_at) > as_utc(later_at)
    ]

    if out_of_order:
        return Check(TIMESTAMPS, FAILED, ", ".join(out_of_order))

    return Check(TIMESTAMPS, PASSED, "in order, " + " then ".join(name for name, _ in stamps))
