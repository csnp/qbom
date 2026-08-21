"""
QBOM: Quantum Bill of Materials

Invisible provenance capture for quantum computing experiments.
One import. Complete reproducibility.

Usage:
    import qbom  # That's it. Everything is now captured.

    # Your quantum code works exactly as before
    from qiskit import QuantumCircuit, transpile
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    # ...

    # Access your trace
    trace = qbom.current()
    trace.export("experiment.qbom.json")

Copyright 2025 CyberSecurity NonProfit (CSNP)
Licensed under Apache 2.0
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _installed_version

try:
    # Read the version the package was installed with, so pyproject.toml is the
    # single place it is declared. Hardcoding it here as well let the two drift:
    # qbom.__version__ said 0.1.0 while qbom --version said 0.1.1.
    __version__ = _installed_version("qbom")
except PackageNotFoundError:  # pragma: no cover - running from a source tree
    __version__ = "unknown"

__author__ = "CSNP"

from qbom.core.session import Session, current, experiment, export, show
from qbom.core.trace import Trace

__all__ = [
    "Trace",
    "Session",
    "current",
    "experiment",
    "export",
    "show",
    "__version__",
]

# Auto-initialize on import
Session.auto_start()
