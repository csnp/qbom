"""UTC time helpers.

QBOM timestamps are UTC. Timestamps QBOM stamps itself are timezone-aware, so
the value says which zone it is in rather than leaving the reader to assume.

Traces written by earlier releases stored naive timestamps that were also UTC,
the format just did not record the offset. A naive value read back from such a
trace is therefore read as UTC, not as local time. Normalise at the point where
a stored timestamp is compared or subtracted, so the value the user's file
holds is never rewritten.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    """Return a datetime as a timezone-aware UTC datetime.

    A value with no offset is read as UTC, which is what QBOM timestamps have
    always meant. A value that already carries an offset is converted to UTC
    and is otherwise unchanged.

    Use this before comparing or subtracting a timestamp that came from a
    trace file, because that file may predate offsets being written.

    One aware value cannot be converted: a timestamp within one UTC offset of
    datetime.min or datetime.max moves outside the representable range when
    the offset is applied, and astimezone raises OverflowError. Such a value
    is returned unchanged. It already carries an offset, so it still compares
    and subtracts correctly against any other aware value, which is all the
    callers of this function ask of it. Reading a file that holds one must not
    fail when the code this replaced could read it.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    try:
        return value.astimezone(timezone.utc)
    except OverflowError:
        return value
