# Usage Guide

This guide covers how to use QBOM in your quantum computing projects.

## Basic Usage

### The One-Line Integration

Add `import qbom` at the top of your script:

```python
import qbom  # That's it!

from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator

# Your existing code works unchanged
qc = QuantumCircuit(2)
qc.h(0)
qc.cx(0, 1)
qc.measure_all()

backend = AerSimulator()
job = backend.run(qc, shots=4096)
result = job.result()

# View what was captured
qbom.show()
```

### Viewing Traces

```python
# Display current trace in terminal
qbom.show()

# Get the trace object
trace = qbom.current()
print(trace.id)
print(trace.summary)
```

### Exporting Traces

```python
# Export to JSON (default)
qbom.export("experiment.qbom.json")

# Export to specific format
qbom.export("experiment.cdx.json", format="cyclonedx")
qbom.export("experiment.spdx.json", format="spdx")
```

## Working with Traces

### The Trace Object

```python
trace = qbom.current()

# Environment information
print(trace.environment.python)        # "3.11.12"
print(trace.environment.packages)      # List of Package objects

# Circuit information
for circuit in trace.circuits:
    print(circuit.name)
    print(circuit.num_qubits)
    print(circuit.depth)
    print(circuit.gates.total)

# Hardware information
if trace.hardware:
    print(trace.hardware.provider)     # "IBM Quantum" or "Aer (Local)"
    print(trace.hardware.backend)      # "ibm_brisbane" or "aer_simulator"
    print(trace.hardware.is_simulator) # True/False

# Execution information
if trace.execution:
    print(trace.execution.shots)       # 4096
    print(trace.execution.job_id)      # "abc-123-def"

# Results
if trace.result:
    print(trace.result.counts.raw)     # {"00": 2048, "11": 2048}
    print(trace.result.counts.probabilities)  # {"00": 0.5, "11": 0.5}
```

### Transpilation Details

When you use `qiskit.transpile()`, QBOM captures the details:

```python
from qiskit import transpile

transpiled = transpile(circuit, backend, optimization_level=2)

trace = qbom.current()
if trace.transpilation:
    print(trace.transpilation.optimization_level)  # 2
    print(trace.transpilation.seed)
    print(trace.transpilation.input_circuit.depth)
    print(trace.transpilation.output_circuit.depth)
```

## Scoped Experiments

Use context managers to create isolated experiments:

```python
import qbom

with qbom.experiment("Bell State Test", tags=["tutorial"]) as exp:
    # All operations in this block are captured
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure_all()

    backend = AerSimulator()
    job = backend.run(qc, shots=1024)
    result = job.result()

# Trace is automatically finalized and saved when exiting the block
```

## Framework-Specific Examples

### Qiskit

```python
import qbom

from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator

# Create circuit
qc = QuantumCircuit(3)
qc.h(0)
qc.cx(0, 1)
qc.cx(1, 2)
qc.measure_all()

# Transpile (captured automatically)
backend = AerSimulator()
transpiled = transpile(qc, backend, optimization_level=2)

# Execute (captured automatically)
job = backend.run(transpiled, shots=4096)
result = job.result()

# View trace
qbom.show()
```

### Cirq

```python
import qbom

import cirq

# Create circuit
q0, q1 = cirq.LineQubit.range(2)
circuit = cirq.Circuit([
    cirq.H(q0),
    cirq.CNOT(q0, q1),
    cirq.measure(q0, q1, key='result')
])

# Simulate
simulator = cirq.Simulator()
result = simulator.run(circuit, repetitions=4096)

# View trace
qbom.show()
```

### PennyLane

```python
import qbom

import pennylane as qml

dev = qml.device("default.qubit", wires=2, shots=4096)

@qml.qnode(dev)
def bell_state():
    qml.Hadamard(wires=0)
    qml.CNOT(wires=[0, 1])
    return qml.counts()

result = bell_state()

# View trace
qbom.show()
```

## Jupyter Notebooks

QBOM provides rich display in Jupyter notebooks:

```python
import qbom

# ... run your quantum experiment ...

# Rich display
trace = qbom.current()
trace  # Displays formatted trace in notebook
```

You can also use:

```python
from qbom.notebook import display_trace
display_trace(trace)
```

## Analyzing Traces

### Reproducibility Score

```python
from qbom.analysis import calculate_score

trace = qbom.current()
result = calculate_score(trace)

print(f"Score: {result.total_score}/100")
print(f"Grade: {result.grade}")

for component in result.components:
    print(f"  {component.name}: {component.score}/{component.max_score}")
```

### Validation

```python
from qbom.analysis import validate_trace

trace = qbom.current()
result = validate_trace(trace)

print(f"Valid: {result.is_valid}")
for issue in result.issues:
    print(f"  [{issue.level}] {issue.message}")
```

### Calibration Drift

```python
from qbom.analysis import analyze_drift

trace = qbom.current()
result = analyze_drift(trace)

print(f"Drift Score: {result.drift_score}")
print(f"Feasibility: {result.reproduction_feasibility}")
```

## Best Practices

### 1. Import Order

Always import qbom first:

```python
import qbom  # First!

from qiskit import QuantumCircuit
import numpy as np
```

### 2. Named Experiments

Give your experiments descriptive names:

```python
with qbom.experiment("VQE Optimization Run 3",
                     description="Testing new ansatz",
                     tags=["vqe", "optimization"]) as exp:
    # ...
```

### 3. Export for Publication

Before submitting a paper, export and validate:

```bash
qbom validate qbom_abc123 --publication
qbom export qbom_abc123 supplementary_material.qbom.json
```

### 4. Include in Papers

Generate reproducibility statements:

```bash
qbom paper qbom_abc123
```

### 5. Version Control

Consider committing important traces:

```bash
mkdir -p experiments/traces
qbom export qbom_abc123 experiments/traces/main_result.qbom.json
git add experiments/traces/main_result.qbom.json
git commit -m "Add trace for main experimental result"
```

## Troubleshooting

### Empty Traces

If traces are empty:

1. Ensure you're using a supported framework
2. Call `qbom.current()` after `job.result()`
3. Check the adapter loaded:
   `from qbom.core.session import Session; print([a.name for a in Session.get()._adapters])`

Import order is not one of the causes. A framework imported after `import qbom`
is captured the same way as one imported before it.

### Missing Transpilation

Transpilation is only captured when using `qiskit.transpile()`:

```python
# Captured
from qiskit import transpile
transpiled = transpile(circuit, backend)

# Not captured (backend's internal transpilation)
job = backend.run(circuit)  # Uses default transpilation
```

### Multiple Experiments

Each `job.result()` call finalizes the current trace. For multiple experiments:

```python
# Option 1: Use scoped experiments
with qbom.experiment("Experiment 1"):
    # ...

with qbom.experiment("Experiment 2"):
    # ...

# Option 2: Access previous traces
traces = qbom.Session.get().list_traces()
```

## Next Steps

- [CLI Reference](CLI.md) - Command-line documentation
- [API Reference](API.md) - Full Python API
- [Adapters](ADAPTERS.md) - Framework adapter details
