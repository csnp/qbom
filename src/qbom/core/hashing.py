"""
The hashes QBOM records, in one place.

Each adapter used to carry its own copy of the result-hash expression. A
verifier has to produce the same bytes as the capture that wrote the value it
is checking, and three copies of one expression are three chances of drift, so
capture and verification now call the same function.

The expression is fixed. Changing it does not upgrade the traces already on
disk, it makes them unverifiable: the hash each one records was taken with the
expression in force when it was written.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any


def result_hash(counts: Mapping[str, Any]) -> str:
    """
    Hash a counts dictionary the way every recorded result hash was taken.

    Args:
        counts: Measurement outcomes as captured. Any mapping works, including
            the dict subclasses Qiskit and Cirq return from ``get_counts()``.

    Returns:
        The first 16 hex characters of the SHA-256 of the sorted items.
    """
    return hashlib.sha256(str(sorted(counts.items())).encode()).hexdigest()[:16]
