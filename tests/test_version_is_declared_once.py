"""The version is declared in one place and every surface agrees with it.

Before this, `pyproject.toml` and `src/qbom/__init__.py` both carried a literal.
Bumping one and not the other shipped a release where `qbom --version` reported
0.1.1 while `qbom.__version__` reported 0.1.0, with nothing to catch it.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import qbom

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

# Read the declaration textually rather than with tomllib, which is stdlib only
# from Python 3.11. This package supports 3.10, and an import error here would
# take the whole file out of collection on the interpreter it most needs to run
# on. The pattern is scoped to the [project] table so it cannot pick up a
# dependency pin such as "ruff>=0.1.0".
_PROJECT_VERSION = re.compile(
    r"^\[project\]$.*?^version\s*=\s*[\"'](?P<version>[^\"']+)[\"']",
    re.MULTILINE | re.DOTALL,
)


def declared_version() -> str:
    """The version as declared in pyproject.toml, the single source of truth."""
    match = _PROJECT_VERSION.search(PYPROJECT.read_text(encoding="utf-8"))
    assert match is not None, "no version declared in the [project] table"
    return match.group("version")


def test_the_package_reports_the_declared_version() -> None:
    assert qbom.__version__ == declared_version()


def test_the_cli_reports_the_declared_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "qbom.cli.main", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert declared_version() in result.stdout


def test_no_source_file_hardcodes_a_second_version_literal() -> None:
    """A literal version string in the package is a second source of truth.

    This is what actually failed: the drift was invisible because nothing
    compared the two declarations.
    """
    src = Path(__file__).resolve().parent.parent / "src" / "qbom"
    pattern = re.compile(r"""^\s*__version__\s*=\s*["']\d+\.\d+""", re.MULTILINE)
    offenders = [
        path.relative_to(src).as_posix()
        for path in src.rglob("*.py")
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"hardcoded version literal in: {offenders}"
