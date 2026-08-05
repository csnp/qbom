"""
Tests that the API the docs and examples call actually exists.

qbom.experiment() was documented in README.md, docs/USAGE.md, the session
module's own docstring and examples/scoped_experiment.py, but was never
imported into qbom/__init__.py, so the example died on AttributeError.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import qbom

REPO_ROOT = Path(__file__).resolve().parents[1]

DOC_SOURCES = [
    *sorted(REPO_ROOT.glob("*.md")),
    *sorted((REPO_ROOT / "docs").glob("*.md")),
    *sorted((REPO_ROOT / "examples").glob("*.py")),
]


def _documented_attributes() -> set[str]:
    """Every qbom.<name>( call that appears in a doc or an example."""
    names: set[str] = set()
    for source in DOC_SOURCES:
        names.update(re.findall(r"\bqbom\.([a-z_][a-z0-9_]*)\(", source.read_text()))
    return names


@pytest.mark.parametrize("name", sorted(_documented_attributes()))
def test_documented_attribute_exists(name):
    assert hasattr(qbom, name), f"docs and examples call qbom.{name}(), which the package does not export"
    assert name in qbom.__all__, f"qbom.{name} works but is missing from __all__"


def test_the_scan_found_something():
    """Guard the premise: an empty scan would make the test above vacuous."""
    found = _documented_attributes()
    assert len(found) >= 4, f"expected the docs to call several qbom functions, found {found!r}"
