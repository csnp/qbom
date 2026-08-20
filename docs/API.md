# Python API Reference

Complete reference for the QBOM Python API.

## Module: qbom

The main module provides convenience functions for common operations.

### qbom.show()

Display the current trace in the terminal.

```python
import qbom

# After running your quantum experiment...
qbom.show()
```

### qbom.current()

Get the current or most recent trace.

```python
trace = qbom.current()
print(trace.id)
print(trace.summary)
```

**Returns:** `Trace` object

### qbom.export()

Export the current trace to a file.

```python
# Export as JSON (default)
path = qbom.export("experiment.qbom.json")

# Export as CycloneDX
path = qbom.export("experiment.cdx.json", format="cyclonedx")

# Export as SPDX
path = qbom.export("experiment.spdx.json", format="spdx")
```

**Parameters:**
- `path` (str | Path): Output file path
- `format` (str): Export format - "json", "cyclonedx", "spdx", "yaml"

**Returns:** `Path` to the exported file

### qbom.experiment()

Context manager for scoped experiments.

```python
with qbom.experiment("My Experiment", tags=["test"]) as exp:
    # Your quantum code here
    pass
# Trace is automatically saved
```

**Parameters:**
- `name` (str, optional): Experiment name
- `description` (str, optional): Experiment description
- `tags` (list[str], optional): Tags for categorization

**Returns:** `TraceBuilder` context

---

## Class: Trace

Represents a complete QBOM trace.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `id` | str | Unique trace identifier (e.g., "qbom_abc123") |
| `qbom_version` | str | QBOM format version |
| `created_at` | datetime | Trace creation timestamp |
| `environment` | Environment | Software environment |
| `circuits` | list[Circuit] | Captured circuits |
| `transpilation` | Transpilation | Transpilation details |
| `hardware` | Hardware | Hardware information |
| `execution` | Execution | Execution parameters |
| `result` | Result | Measurement results |
| `metadata` | Metadata | User-provided metadata |
| `summary` | str | Human-readable summary |
| `content_hash` | str | Content verification hash |

### Methods

#### trace.export()

Export trace to file.

```python
trace.export("output.json")
trace.export("output.cdx.json", format="cyclonedx")
```

#### trace.show()

Display trace in terminal.

```python
trace.show()
```

#### trace.to_dict()

Convert trace to dictionary.

```python
data = trace.to_dict()
```

---

## Class: Environment

Software environment information.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `python` | str | Python version |
| `platform` | str | Platform string |
| `packages` | list[Package] | Installed packages |
| `timestamp` | datetime | Capture timestamp |
| `quantum_sdk` | str | Primary quantum SDK |

---

## Class: Package

Package information.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `name` | str | Package name |
| `version` | str | Package version |
| `purl` | str | Package URL (PURL format) |

---

## Class: Circuit

Quantum circuit information.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `name` | str | Circuit name |
| `num_qubits` | int | Number of qubits |
| `num_clbits` | int | Number of classical bits |
| `depth` | int | Circuit depth |
| `gates` | GateCounts | Gate statistics |
| `hash` | str | Content hash |
| `qasm` | str | OpenQASM representation |
| `summary` | str | Human-readable summary |

---

## Class: GateCounts

Gate count statistics.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `single_qubit` | int | Single-qubit gate count |
| `two_qubit` | int | Two-qubit gate count |
| `total` | int | Total gate count |
| `by_name` | dict[str, int] | Counts by gate name |

---

## Class: Transpilation

Transpilation details.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `optimization_level` | int | Optimization level (0-3) |
| `basis_gates` | list[str] | Target basis gates |
| `seed` | int | Transpiler seed |
| `layout_method` | str | Layout method |
| `routing_method` | str | Routing method |
| `initial_layout` | QubitMapping | Initial qubit mapping |
| `final_layout` | QubitMapping | Final qubit mapping |
| `input_circuit` | Circuit | Pre-transpilation circuit |
| `output_circuit` | Circuit | Post-transpilation circuit |
| `depth_increase` | float | Depth ratio (output/input) |

---

## Class: Hardware

Hardware information.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `provider` | str | Provider name |
| `backend` | str | Backend name |
| `num_qubits` | int \| None | Total qubit count, or None where the backend does not report one |
| `qubits_used` | list[int] | Physical qubits used |
| `is_simulator` | bool | Whether backend is simulator |
| `calibration` | Calibration | Calibration data |
| `summary` | str | Human-readable summary |

---

## Class: Calibration

Hardware calibration snapshot.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `timestamp` | datetime | Calibration timestamp |
| `qubits` | list[QubitProperties] | Per-qubit properties |
| `gates` | list[GateProperties] | Per-gate properties |

---

## Class: QubitProperties

Per-qubit calibration data.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `index` | int | Qubit index |
| `t1_us` | float | T1 time in microseconds |
| `t2_us` | float | T2 time in microseconds |
| `readout_error` | float | Readout error rate |
| `frequency_ghz` | float | Qubit frequency in GHz |

---

## Class: GateProperties

Per-gate calibration data.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `gate` | str | Gate name |
| `qubits` | tuple[int, ...] | Qubits involved |
| `error` | float | Gate error rate |
| `duration_ns` | float | Gate duration in nanoseconds |

---

## Class: Execution

Execution parameters.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `job_id` | str | Job identifier |
| `shots` | int | Number of shots |
| `submitted_at` | datetime | Submission time |
| `completed_at` | datetime | Completion time |

---

## Class: Result

Measurement results.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `counts` | Counts | Measurement counts |
| `metadata` | dict | Additional metadata |
| `hash` | str | Result verification hash |

---

## Class: Counts

Measurement count statistics.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `raw` | dict[str, int] | Raw count dictionary |
| `shots` | int | Total shots |
| `probabilities` | dict[str, float] | Probability distribution |
| `top_results` | list[tuple] | Top results by probability |

---

## Module: qbom.analysis

Analysis tools for traces.

### calculate_score()

Calculate reproducibility score.

```python
from qbom.analysis import calculate_score

result = calculate_score(trace)
print(f"Score: {result.total_score}/100")
print(f"Grade: {result.grade}")
```

**Returns:** `ScoreResult`

### validate_trace()

Validate trace completeness.

```python
from qbom.analysis import validate_trace

result = validate_trace(trace)
result = validate_trace(trace, publication=True)  # Stricter
```

**Returns:** `ValidationResult`

### analyze_drift()

Analyze calibration drift.

```python
from qbom.analysis import analyze_drift

result = analyze_drift(trace)
print(f"Drift: {result.drift_score}")
```

**Returns:** `DriftResult`

---

## Module: qbom.core.session

Session management.

### Session.get()

Get the global session instance.

```python
from qbom.core.session import Session

session = Session.get()
```

### session.list_traces()

List recent traces.

```python
traces = session.list_traces(limit=10)
```

---

## See Also

- [Usage Guide](USAGE.md) - Usage examples
- [CLI Reference](CLI.md) - Command-line interface
