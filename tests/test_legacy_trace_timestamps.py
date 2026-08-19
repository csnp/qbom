"""Traces written before timestamps carried a UTC offset must still be readable.

Every trace exported by earlier releases stored naive timestamps, for example
"2026-03-01T12:00:00" with nothing after the seconds. Those values were always
UTC, the format just did not say so. Now that QBOM stamps new traces with
timezone-aware UTC, anything that compares a stored timestamp against the
current time has to read a naive value as UTC, or the comparison raises
TypeError on every trace a user already has on disk.

LEGACY_TRACE_JSON below is a real export produced by the release that wrote
naive timestamps, not a hand-written approximation.

Two wrong normalisations have to be ruled out, and each needs its own kind of
test.

Reading a stored naive value as LOCAL time instead of as UTC is invisible when
the machine running the tests already sits in UTC, because there the two
readings are the same operation. GitHub Actions runners default to UTC, so a
test that only fails outside UTC never fails anywhere that matters. The tests
below that can tell the two apart therefore set the local zone themselves, via
the forced_local_timezone fixture, and run under several zones including UTC.
Their assertions hold in every one of those zones, and in whatever zone the
machine was in before the fixture ran.

Discarding an offset instead of converting it, so that 14:00+02:00 wrongly
becomes 14:00 UTC rather than 12:00 UTC, is invisible whenever every aware
value in a test is already UTC. The tests below therefore build aware values
with real non-zero offsets and assert the converted instant.

Both kinds of test need an exact expected value. "Does not raise", ">= 0" and
"is truthy" all hold just as well for a normalisation that is wrong by days,
so the clock is frozen or the compared instants are pinned, and the assertion
is on the exact number that follows.
"""

from __future__ import annotations

import os
import time
import warnings
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest

from qbom.analysis import drift as drift_module
from qbom.analysis.drift import analyze_drift, explain_result_difference
from qbom.core.models import (
    Calibration,
    Circuit,
    Counts,
    Execution,
    GateCounts,
    GateProperties,
    Hardware,
    QubitProperties,
    Result,
)
from qbom.core.timeutil import as_utc, utc_now
from qbom.core.trace import Trace

LEGACY_TRACE_JSON = """
{
  "id": "qbom_legacy1",
  "qbom_version": "1.0",
  "created_at": "2026-03-01T12:00:00",
  "circuits": [
    {
      "name": "bell",
      "num_qubits": 2,
      "num_clbits": 2,
      "depth": 2,
      "gates": {"single_qubit": 1, "two_qubit": 1, "total": 2, "by_name": {}},
      "hash": "abc123"
    }
  ],
  "hardware": {
    "provider": "IBM Quantum",
    "backend": "ibm_brisbane",
    "num_qubits": 127,
    "qubits_used": [3, 5],
    "is_simulator": false,
    "calibration": {
      "timestamp": "2026-03-01T12:00:00",
      "qubits": [{"index": 3, "t1_us": 110.5, "t2_us": 90.25, "readout_error": 0.012}],
      "gates": [{"gate": "cx", "qubits": [3, 5], "error": 0.0071}]
    }
  },
  "execution": {
    "job_id": "job1",
    "shots": 1024,
    "submitted_at": "2026-03-01T12:00:00",
    "started_at": "2026-03-01T12:00:30",
    "completed_at": "2026-03-01T12:01:35"
  },
  "result": {
    "counts": {"raw": {"00": 512, "11": 512}, "shots": 1024},
    "metadata": {},
    "hash": "res123"
  },
  "metadata": {"tags": [], "authors": []}
}
"""

# The naive value the legacy trace stores for its calibration, and the instant
# that value means. Every expected number below is derived from this instant.
LEGACY_CALIBRATION_STORED = datetime(2026, 3, 1, 12, 0, 0)
LEGACY_CALIBRATION_INSTANT = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)

# A fixed "current time", so the age of the legacy calibration is one exact
# number rather than whatever the wall clock makes it.
FROZEN_NOW = datetime(2026, 3, 11, 12, 0, 0, tzinfo=timezone.utc)
FROZEN_AGE = timedelta(days=10)

# Local zones the timestamp tests run under. These are POSIX TZ strings rather
# than zone names, so they do not depend on a timezone database being
# installed, and none of them observes daylight saving, so the offset each one
# gives is the same all year. UTC is included on purpose: it is where CI runs,
# and a test that does not hold there is not protecting anything.
LOCAL_ZONES = (
    "UTC0",  # UTC
    "XXX8",  # UTC-08:00
    "XXX-5:45",  # UTC+05:45
    "XXX11",  # UTC-11:00
)


@pytest.fixture(params=LOCAL_ZONES)
def forced_local_timezone(request: pytest.FixtureRequest) -> Iterator[str]:
    """Run the test body under a known local zone, then restore the old one.

    A test that reads a stored naive timestamp cannot show the difference
    between reading it as UTC and reading it as local time unless it controls
    what local time is. Setting the zone here rather than in the environment
    around pytest means the assertions hold whatever zone the machine is in.
    """
    # tzset exists on every platform this is tested and released on. The guard
    # is only for Windows, which has no way to change the zone in-process.
    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset is needed to set the local zone for this test")

    previous = os.environ.get("TZ")
    os.environ["TZ"] = request.param
    time.tzset()
    try:
        yield request.param
    finally:
        if previous is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous
        time.tzset()


def load_legacy_trace() -> Trace:
    """Read the old export the same way the CLI reads a trace file."""
    return Trace.model_validate_json(LEGACY_TRACE_JSON)


def build_current_calibration(offset_days: int = 0) -> Calibration:
    """A calibration fetched now, so its timestamp is timezone-aware."""
    return Calibration(
        timestamp=datetime.now(timezone.utc) - timedelta(days=offset_days),
        qubits=[QubitProperties(index=3, t1_us=95.0, t2_us=70.0, readout_error=0.02)],
        gates=[GateProperties(gate="cx", qubits=(3, 5), error=0.0102)],
    )


def build_calibration_at(timestamp: datetime) -> Calibration:
    """A calibration whose timestamp is pinned, so drift maths has one answer."""
    return Calibration(
        timestamp=timestamp,
        qubits=[QubitProperties(index=3, t1_us=95.0, t2_us=70.0, readout_error=0.02)],
        gates=[GateProperties(gate="cx", qubits=(3, 5), error=0.0102)],
    )


def build_trace_with_calibration(calibration: Calibration) -> Trace:
    """A trace identical to the legacy one apart from its calibration time."""
    circuit = Circuit(
        name="bell",
        num_qubits=2,
        num_clbits=2,
        depth=2,
        gates=GateCounts(single_qubit=1, two_qubit=1, total=2),
        hash="abc123",
    )
    return Trace(
        id="qbom_pinned1",
        circuits=[circuit],
        hardware=Hardware(
            provider="IBM Quantum",
            backend="ibm_brisbane",
            num_qubits=127,
            qubits_used=[3, 5],
            calibration=calibration,
        ),
        result=Result(counts=Counts(raw={"00": 512, "11": 512}, shots=1024), hash="res123"),
    )


def build_current_trace() -> Trace:
    """A trace captured now, so every timestamp it holds is timezone-aware."""
    circuit = Circuit(
        name="bell",
        num_qubits=2,
        num_clbits=2,
        depth=2,
        gates=GateCounts(single_qubit=1, two_qubit=1, total=2),
        hash="abc123",
    )
    now = datetime.now(timezone.utc)
    return Trace(
        id="qbom_current1",
        circuits=[circuit],
        hardware=Hardware(
            provider="IBM Quantum",
            backend="ibm_brisbane",
            num_qubits=127,
            qubits_used=[3, 5],
            calibration=build_current_calibration(),
        ),
        execution=Execution(
            job_id="job2",
            shots=1024,
            submitted_at=now,
            started_at=now + timedelta(seconds=30),
            completed_at=now + timedelta(seconds=95),
        ),
        result=Result(counts=Counts(raw={"00": 512, "11": 512}, shots=1024), hash="res123"),
    )


# ============================================================================
# Reading a trace that is already on disk
# ============================================================================


def test_legacy_export_deserialises_with_naive_timestamps() -> None:
    """The stored value is left exactly as written, with no offset attached.

    This pins the decision not to rewrite what a user's trace file contains.
    If this starts failing, timestamps are being coerced during validation and
    a round-tripped trace no longer matches the file it came from.
    """
    trace = load_legacy_trace()

    assert trace.created_at.tzinfo is None
    assert trace.hardware is not None
    assert trace.hardware.calibration is not None
    assert trace.hardware.calibration.timestamp.tzinfo is None
    assert trace.hardware.calibration.timestamp == LEGACY_CALIBRATION_STORED


def test_analyze_drift_reads_a_trace_written_before_offsets() -> None:
    """qbom drift on an existing trace file must not raise.

    analyze_drift subtracts the stored calibration timestamp from the current
    time. The stored value has no offset and the current time does, so the
    subtraction fails unless the stored value is read as UTC first.

    This test only shows that the call completes and that the stored value is
    handed back untouched. What the normalisation actually computed is pinned
    by the frozen-clock test below, not here.
    """
    trace = load_legacy_trace()

    result = analyze_drift(trace)

    assert result is not None
    assert result.time_elapsed is not None
    assert result.time_elapsed.days >= 0
    assert result.original_calibration_time == LEGACY_CALIBRATION_STORED
    assert result.reproduction_feasibility in {"High", "Medium", "Low", "Very Low"}
    assert result.summary()


def test_drift_age_of_a_legacy_calibration_is_an_exact_span(
    monkeypatch: pytest.MonkeyPatch,
    forced_local_timezone: str,
) -> None:
    """The age qbom drift reports is one exact number, not merely non-negative.

    The clock is frozen at 2026-03-11T12:00Z and the trace stores
    2026-03-01T12:00:00, which means 2026-03-01T12:00Z. The age is therefore
    exactly ten days, and every field drift derives from the age follows from
    that. Reading the stored value as local time shifts it by the local offset
    and the span stops being ten days; adding any constant to it does the same.
    """
    monkeypatch.setattr(drift_module, "utc_now", lambda: FROZEN_NOW)
    trace = load_legacy_trace()

    result = analyze_drift(trace)

    assert result is not None
    assert result.time_elapsed == FROZEN_AGE
    assert result.reproduction_feasibility == "Very Low"
    assert result.overall_drift_score == 80
    assert "Calibration is 10 days old" in result.recommendations


def test_analyze_drift_compares_a_legacy_trace_to_a_current_calibration() -> None:
    """The full comparison path subtracts two stored timestamps.

    The original comes from a file with no offset and the current one is
    fetched from the backend now, so the two differ in kind.
    """
    trace = load_legacy_trace()

    result = analyze_drift(trace, current_calibration=build_current_calibration())

    assert result is not None
    assert result.time_elapsed is not None
    assert result.time_elapsed.total_seconds() > 0
    assert len(result.qubit_drift) == 1
    assert len(result.gate_drift) == 1
    assert result.overall_drift_score > 0


def test_drift_against_an_offset_calibration_is_an_exact_span(forced_local_timezone: str) -> None:
    """Both branches of the normalisation meet in one subtraction.

    The original is the legacy naive 2026-03-01T12:00:00, meaning
    2026-03-01T12:00Z. The current calibration is 2026-03-03T14:00+02:00,
    which is the instant 2026-03-03T12:00Z. The elapsed span is therefore
    exactly two days.

    Discarding the +02:00 offset instead of converting it reads the current
    calibration as 14:00Z and gives two days and two hours. Reading the stored
    naive value as local time moves it by the local offset. Neither is two
    days, in any zone.
    """
    trace = load_legacy_trace()
    current = build_calibration_at(datetime(2026, 3, 3, 14, 0, 0, tzinfo=timezone(timedelta(hours=2))))

    result = analyze_drift(trace, current_calibration=current)

    assert result is not None
    assert result.time_elapsed == timedelta(days=2)
    assert result.original_calibration_time == LEGACY_CALIBRATION_STORED


def test_explain_result_difference_across_a_legacy_and_a_current_trace() -> None:
    """Comparing an old trace with a new one subtracts two calibration times."""
    explanations = explain_result_difference(load_legacy_trace(), build_current_trace())

    assert isinstance(explanations, list)
    assert any("days apart" in line for line in explanations)


def test_explain_result_difference_reports_an_exact_gap(forced_local_timezone: str) -> None:
    """The reported gap is the gap between the two instants.

    2026-03-04T14:00+02:00 is the instant 2026-03-04T12:00Z, exactly three
    days after the legacy calibration at 2026-03-01T12:00Z. Discarding the
    offset would report 3.1 days, and reading the stored value as local time
    would report something else again.
    """
    newer = build_trace_with_calibration(
        build_calibration_at(datetime(2026, 3, 4, 14, 0, 0, tzinfo=timezone(timedelta(hours=2))))
    )

    explanations = explain_result_difference(load_legacy_trace(), newer)

    assert "Calibrations are 3.0 days apart - hardware drift likely" in explanations


def test_explain_result_difference_stays_below_the_one_day_threshold(forced_local_timezone: str) -> None:
    """A gap under a day is not reported as drift.

    2026-03-02T13:59+02:00 is the instant 2026-03-02T11:59Z, which is 23 hours
    and 59 minutes after the legacy calibration, just inside the one-day
    threshold. Discarding the offset reads it as 13:59Z, puts the gap at 25
    hours and 59 minutes, and produces a drift line that should not be there.
    """
    newer = build_trace_with_calibration(
        build_calibration_at(datetime(2026, 3, 2, 13, 59, 0, tzinfo=timezone(timedelta(hours=2))))
    )

    explanations = explain_result_difference(load_legacy_trace(), newer)

    assert not any("days apart" in line for line in explanations)


def test_execution_timing_survives_mixed_timestamp_kinds() -> None:
    """Queue and execution durations subtract two stored timestamps.

    A trace assembled from a job submitted before an upgrade and completed
    after it holds one value of each kind.
    """
    naive = datetime(2026, 3, 1, 12, 0, 0)
    aware = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)

    execution = Execution(
        shots=1024,
        submitted_at=naive,
        started_at=aware + timedelta(seconds=30),
        completed_at=aware + timedelta(seconds=95),
    )

    assert execution.queue_time_seconds == 30.0
    assert execution.execution_time_seconds == 65.0


def test_execution_timing_converts_offsets_rather_than_discarding_them(
    forced_local_timezone: str,
) -> None:
    """The computed durations are exact across three different offsets.

    A backend can report a timestamp in its own zone, so the values a trace
    holds are not all UTC and not all naive. Here 14:00+02:00, naive 12:30 and
    07:40-05:00 are the instants 12:00Z, 12:30Z and 12:40Z, so the queue took
    exactly 1800 seconds and the run exactly 600.

    Discarding an offset makes the queue time negative. Reading the naive
    value as local time moves the boundary between the two durations.
    """
    submitted = datetime(2026, 3, 1, 14, 0, 0, tzinfo=timezone(timedelta(hours=2)))
    started = datetime(2026, 3, 1, 12, 30, 0)
    completed = datetime(2026, 3, 1, 7, 40, 0, tzinfo=timezone(timedelta(hours=-5)))

    execution = Execution(shots=1024, submitted_at=submitted, started_at=started, completed_at=completed)

    assert execution.queue_time_seconds == 1800.0
    assert execution.execution_time_seconds == 600.0


# ============================================================================
# Normalising a single value
# ============================================================================


def test_as_utc_reads_a_naive_value_as_utc(forced_local_timezone: str) -> None:
    """A stored value with no offset means UTC, whatever zone the reader is in.

    The expected instant is the same in every zone, which is the whole point:
    the local zone must not enter the answer.
    """
    assert as_utc(LEGACY_CALIBRATION_STORED) == LEGACY_CALIBRATION_INSTANT
    assert as_utc(LEGACY_CALIBRATION_STORED).utcoffset() == timedelta(0)


def test_as_utc_converts_an_offset_rather_than_discarding_it() -> None:
    """14:00+02:00 is 12:00 UTC, not 14:00 UTC."""
    value = datetime(2026, 3, 1, 14, 0, 0, tzinfo=timezone(timedelta(hours=2)))

    converted = as_utc(value)

    assert converted == datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert converted.utcoffset() == timedelta(0)
    assert converted.hour == 12


def test_as_utc_converts_a_negative_offset() -> None:
    """07:40-05:00 is 12:40 UTC, so the offset is added, not subtracted."""
    value = datetime(2026, 3, 1, 7, 40, 0, tzinfo=timezone(timedelta(hours=-5)))

    converted = as_utc(value)

    assert converted == datetime(2026, 3, 1, 12, 40, 0, tzinfo=timezone.utc)
    assert converted.hour == 12
    assert converted.minute == 40


# ============================================================================
# Timestamps that cannot be represented in UTC
# ============================================================================
#
# Applying an offset to a value within one offset of datetime.min or
# datetime.max moves it outside the range a datetime can hold, and astimezone
# raises OverflowError. Measured with a -12:00 offset: converting fails from
# datetime.max down to 11 hours before it, and succeeds from 12 hours before
# it onwards. The code this replaced subtracted such timestamps without
# converting them and did not raise, so a file holding one used to be
# readable. The computed fields on Execution are reached by qbom show and by
# every qbom export format, not only by qbom drift, so raising here would take
# out the whole file rather than one command.


def test_as_utc_returns_an_unconvertible_late_value_unchanged() -> None:
    """A value too close to datetime.max to convert is handed back as it is."""
    value = datetime(9999, 12, 31, 23, 59, 59, tzinfo=timezone(timedelta(hours=-12)))

    converted = as_utc(value)

    assert converted == value
    assert converted.utcoffset() == timedelta(hours=-12)


def test_as_utc_returns_an_unconvertible_early_value_unchanged() -> None:
    """The same holds at the other end of the range."""
    value = datetime(1, 1, 1, 0, 0, 0, tzinfo=timezone(timedelta(hours=12)))

    converted = as_utc(value)

    assert converted == value
    assert converted.utcoffset() == timedelta(hours=12)


def test_as_utc_still_converts_at_the_last_representable_instant() -> None:
    """The fallback is only for values that genuinely cannot be converted.

    Twelve hours before datetime.max with a -12:00 offset lands exactly on
    datetime.max in UTC, so it converts. If this returned the value unchanged,
    the fallback would have grown into a rule for every aware timestamp.
    """
    value = datetime(9999, 12, 31, 11, 59, 59, tzinfo=timezone(timedelta(hours=-12)))

    converted = as_utc(value)

    assert converted == datetime(9999, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    assert converted.utcoffset() == timedelta(0)


def test_execution_timing_on_unconvertible_timestamps_still_reports() -> None:
    """qbom show and qbom export must not fail on such a file.

    All three timestamps sit inside the unconvertible window, so each one is
    returned as it is. They share an offset, so the durations between them are
    unaffected and stay exact.
    """
    far_future = timezone(timedelta(hours=-12))
    execution = Execution(
        shots=1024,
        submitted_at=datetime(9999, 12, 31, 23, 57, 59, tzinfo=far_future),
        started_at=datetime(9999, 12, 31, 23, 58, 59, tzinfo=far_future),
        completed_at=datetime(9999, 12, 31, 23, 59, 59, tzinfo=far_future),
    )

    assert execution.queue_time_seconds == 60.0
    assert execution.execution_time_seconds == 60.0

    dumped = execution.model_dump()
    assert dumped["queue_time_seconds"] == 60.0
    assert dumped["execution_time_seconds"] == 60.0


# ============================================================================
# New traces carry timezone-aware UTC
# ============================================================================


def test_utc_now_is_stamped_in_utc_not_in_the_local_zone() -> None:
    """The stamp carries UTC itself, not whatever zone the machine is in.

    This is an identity check rather than an equality one on purpose. Two
    timezone objects compare equal when their offsets match, so on a machine
    already in UTC a stamp taken in local time would compare equal to UTC and
    the check would pass while saying nothing. The object utc_now attaches is
    the UTC singleton in every zone; a local stamp never is.
    """
    now = utc_now()

    assert now.tzinfo is timezone.utc


def test_new_timestamps_are_timezone_aware_utc(forced_local_timezone: str) -> None:
    """Timestamps QBOM stamps itself say which zone they are in.

    The offset check below is vacuous on a machine already in UTC, so the
    reading itself is compared against a UTC reading taken beside it. A stamp
    taken in local time carries the local wall clock and lands hours away.
    """
    trace = Trace()
    reference = datetime.now(timezone.utc)

    assert trace.created_at.tzinfo is not None
    assert trace.created_at.utcoffset() == timedelta(0)
    assert abs(trace.created_at.replace(tzinfo=None) - reference.replace(tzinfo=None)) < timedelta(seconds=5)


def test_building_a_trace_raises_no_utcnow_deprecation() -> None:
    """datetime.utcnow is deprecated and must not be reached during capture."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        Trace()

    utcnow_warnings = [w for w in caught if "utcnow" in str(w.message)]
    assert utcnow_warnings == []
