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

__version__ = "0.1.0"
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
