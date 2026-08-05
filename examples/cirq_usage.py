#!/usr/bin/env python3
"""
QBOM with Cirq Example

Demonstrates QBOM capture with Google's Cirq framework.
"""

import qbom  # Import first to enable capture

import cirq

# Create qubits
q0, q1 = cirq.LineQubit.range(2)

# Create a Bell state circuit
circuit = cirq.Circuit([
    cirq.H(q0),
    cirq.CNOT(q0, q1),
    cirq.measure(q0, q1, key='result')
])

print("Circuit:")
print(circuit)

# Run on simulator
simulator = cirq.Simulator()
result = simulator.run(circuit, repetitions=4096)

# Print results
print("\nResults:")
print(result.histogram(key='result'))

# Access the QBOM trace
trace = qbom.current()
print(f"\nQBOM Trace: {trace.id}")
print(f"Summary: {trace.summary}")

# Show full trace
trace.show()

# Export
trace.export("cirq_bell_state.qbom.json")
print("\nExported to: cirq_bell_state.qbom.json")
