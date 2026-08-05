# Framework Adapters

QBOM uses adapters to capture operations from different quantum frameworks. This document explains how adapters work and their current capabilities.

## Overview

Adapters are installed automatically when you import a quantum framework after importing QBOM:

```python
import qbom                    # Install import hook
from qiskit import ...         # Qiskit adapter installed
```

## Supported Frameworks

### Qiskit

**Status:** Full Support

**Captured Operations:**

| Operation | Function Hooked | Data Captured |
|-----------|-----------------|---------------|
| Transpilation | `qiskit.transpile()` | Optimization level, basis gates, layout, routing, seed, input/output circuits |
| Execution | `Backend.run()` | Circuits, backend info, shots |
| Results | `Job.result()` | Counts, probabilities, timing |
| Calibration | Backend properties | T1, T2, readout error, gate errors |

**Supported Backends:**
- AerSimulator (local simulation)
- IBM Quantum backends (via qiskit-ibm-runtime)
- Any BackendV2-compatible backend

**Example:**

```python
import qbom

from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator

qc = QuantumCircuit(2)
qc.h(0)
qc.cx(0, 1)
qc.measure_all()

backend = AerSimulator()
transpiled = transpile(qc, backend, optimization_level=2)
job = backend.run(transpiled, shots=4096)
result = job.result()

# All operations captured
qbom.show()
```

---

### Cirq

**Status:** Supported

**Captured Operations:**

| Operation | Function Hooked | Data Captured |
|-----------|-----------------|---------------|
| Simulation | `Simulator.run()` | Circuit, repetitions |
| Results | Simulation result | Measurement counts |

**Supported Simulators:**
- `cirq.Simulator`
- `cirq.DensityMatrixSimulator`

**Example:**

```python
import qbom

import cirq

q0, q1 = cirq.LineQubit.range(2)
circuit = cirq.Circuit([
    cirq.H(q0),
    cirq.CNOT(q0, q1),
    cirq.measure(q0, q1, key='result')
])

simulator = cirq.Simulator()
result = simulator.run(circuit, repetitions=4096)

qbom.show()
```

---

### PennyLane

**Status:** Supported

**Captured Operations:**

| Operation | Function Hooked | Data Captured |
|-----------|-----------------|---------------|
| QNode execution | QNode call | Circuit, device, shots |
| Results | Return value | Counts, expectation values |

**Supported Devices:**
- `default.qubit`
- `lightning.qubit`
- Other PennyLane devices

**Example:**

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

qbom.show()
```

---

### Braket (Planned)

**Status:** Planned

Amazon Braket support is planned for a future release.

---

## How Adapters Work

### 1. Import Detection

QBOM installs a Python import hook (`sys.meta_path`) that detects when quantum frameworks are imported:

```python
class QBOMImportFinder(importlib.abc.MetaPathFinder):
    WATCHED_MODULES = {
        "qiskit": "qiskit",
        "qiskit_aer": "qiskit",
        "cirq": "cirq",
        "pennylane": "pennylane",
    }

    def find_spec(self, fullname, path=None, target=None):
        if "." in fullname or fullname not in self.WATCHED_MODULES:
            return None
        spec = self._find_real_spec(fullname, path, target)
        ...
        # Wrap the loader so the adapter is installed once the framework's
        # own __init__ has finished and its classes exist.
```

The finder wraps the loader rather than acting in `find_spec` itself, because
the adapter has to hook classes such as `AerBackend`, which do not exist until
the module has executed.

### 2. Adapter Installation

When a watched module is imported, the corresponding adapter is installed:

```python
ADAPTER_MAP = {
    "qiskit": ("qbom.adapters.qiskit", "QiskitAdapter"),
    "cirq": ("qbom.adapters.cirq", "CirqAdapter"),
    "pennylane": ("qbom.adapters.pennylane", "PennyLaneAdapter"),
}
```

### 3. Function Hooking

Adapters wrap framework functions to capture data:

```python
def install(self):
    # Wrap qiskit.transpile
    self._wrap_function(qiskit, "transpile", self._make_transpile_wrapper)

    # Wrap Backend.run
    self._hook_backend_run()
```

### 4. Data Capture

When wrapped functions are called, adapters capture relevant data:

```python
def _make_transpile_wrapper(self, original):
    def wrapper(circuits, backend=None, **kwargs):
        # Capture input
        builder = self.session.current_builder
        builder.add_circuit(_circuit_to_model(circuits))

        # Call original
        result = original(circuits, backend, **kwargs)

        # Capture transpilation details
        transpilation = Transpilation(
            optimization_level=kwargs.get("optimization_level"),
            # ...
        )
        builder.set_transpilation(transpilation)

        return result
    return wrapper
```

---

## Writing Custom Adapters

To add support for a new framework, create an adapter class:

```python
from qbom.adapters.base import Adapter

class MyFrameworkAdapter(Adapter):
    name = "myframework"

    def install(self):
        """Install hooks for the framework."""
        if self._installed:
            return

        import myframework

        # Wrap functions
        self._wrap_function(
            myframework,
            "run_circuit",
            self._make_run_wrapper
        )

        self._installed = True

    def _make_run_wrapper(self, original):
        def wrapper(*args, **kwargs):
            # Capture input
            builder = self.session.current_builder
            # ... capture circuit info ...

            # Call original
            result = original(*args, **kwargs)

            # Capture output
            # ... capture results ...

            return result
        return wrapper

    def uninstall(self):
        """Remove hooks."""
        self._unwrap_all()
        self._installed = False
```

Register the adapter in `session.py`:

```python
ADAPTER_MAP = {
    # ...existing adapters...
    "myframework": ("qbom.adapters.myframework", "MyFrameworkAdapter"),
}
```

---

## Adapter Limitations

### General Limitations

- Adapters only capture operations that go through hooked functions
- Direct manipulation of internal framework data may not be captured
- Some metadata may not be available for all backends

### Qiskit Limitations

- Transpilation is only captured when using `qiskit.transpile()`
- Backend's internal transpilation (when passing untranspiled circuits to `run()`) is not captured
- Some older Qiskit versions may have limited support

### Cirq Limitations

- Google Quantum Engine-specific features may have limited capture
- Custom gates may not have full metadata

### PennyLane Limitations

- Gradient computation details are not fully captured
- Some device-specific features may not be captured

---

## Troubleshooting

### Adapter Not Loading

```python
# Check if adapter is installed
from qbom.core.session import Session
session = Session.get()
print([a.name for a in session._adapters])  # Should include your framework
```

### Empty Traces

Import order does not matter. The import hook installs the adapter whether the
framework is imported before or after `import qbom`:

```python
import qbom
from qiskit import ...   # captured

from qiskit import ...   # also captured
import qbom
```

If a trace is still empty, check that the adapter loaded at all:

```python
from qbom.core.session import Session
print([a.name for a in Session.get()._adapters])
```

### Missing Data

Some data may only be captured in specific scenarios:

```python
# Transpilation captured
transpiled = transpile(circuit, backend)

# Transpilation NOT captured (uses backend defaults)
job = backend.run(circuit)  # Untranspiled
```

---

## See Also

- [Usage Guide](USAGE.md) - Framework-specific examples
- [API Reference](API.md) - Data model documentation
