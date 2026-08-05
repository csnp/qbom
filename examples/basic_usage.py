#!/usr/bin/env python3
"""
QBOM Basic Usage Example

This example shows how QBOM invisibly captures quantum experiment provenance.
Just import qbom at the top of your script - that's it!
"""

import qbom  # ← This is all you need. Everything is now captured.

# Your regular quantum code works exactly as before
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator

# Create a Bell state circuit
qc = QuantumCircuit(2, 2)
qc.h(0)
qc.cx(0, 1)
qc.measure([0, 1], [0, 1])

# Run on simulator
backend = AerSimulator()
transpiled = transpile(qc, backend, optimization_level=3)
job = backend.run(transpiled, shots=4096)
result = job.result()

# Print results
counts = result.get_counts()
print("Results:", counts)

# Access the QBOM trace - everything was captured automatically!
trace = qbom.current()
print(f"\nQBOM Trace: {trace.id}")
print(f"Summary: {trace.summary}")

# Show full trace in terminal
trace.show()

# Export for reproducibility
trace.export("bell_state.qbom.json")
print("\nExported to: bell_state.qbom.json")

# Generate paper statement. It carries formatting, so it needs a rich console;
# a plain print() shows the markup instead of applying it.
from rich.console import Console

from qbom.cli.display import generate_paper_statement

console = Console()
console.print("\n--- Paper Statement ---")
console.print(generate_paper_statement(trace))
