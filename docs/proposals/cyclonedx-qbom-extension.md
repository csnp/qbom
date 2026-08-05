# CycloneDX Extension Proposal: Quantum Bill of Materials (QBOM)

**Author:** CyberSecurity NonProfit (CSNP)
**Status:** Draft
**Created:** 2025-01-15
**Version:** 1.0

---

## Abstract

This proposal introduces a CycloneDX extension for capturing quantum computing experiment provenance, called the Quantum Bill of Materials (QBOM). The extension enables complete reproducibility documentation for quantum experiments by capturing software environments, quantum circuits, hardware calibration snapshots, transpilation parameters, and execution results.

---

## 1. Problem Statement

### 1.1 The Reproducibility Crisis in Quantum Computing

Quantum computing experiments face a severe reproducibility challenge. Unlike classical computing, quantum experiments are affected by:

1. **Hardware Drift**: Quantum hardware properties (T1, T2 coherence times, gate errors) change daily
2. **Transpilation Variability**: Circuit compilation produces different physical qubit mappings
3. **Calibration Windows**: Hardware is recalibrated frequently, changing baseline performance
4. **Framework Versions**: Quantum SDKs evolve rapidly with breaking changes

### 1.2 Current State

When researchers publish quantum computing results, they typically report:

> "We used Qiskit 1.0 on IBM Brisbane with 4096 shots."

This is insufficient for reproduction. Missing information includes:
- Exact Python environment and dependency versions
- Physical qubit assignment after transpilation
- Hardware calibration data at execution time
- Circuit optimization level and routing algorithm
- Complete gate sequence after transpilation

### 1.3 Why Existing SBOMs Are Insufficient

Standard SBOMs capture software dependencies but miss quantum-specific concerns:

| Concern | Traditional SBOM | QBOM Extension |
|---------|------------------|----------------|
| Software versions | ✓ | ✓ |
| Quantum circuit definition | ✗ | ✓ |
| Transpilation parameters | ✗ | ✓ |
| Hardware calibration snapshot | ✗ | ✓ |
| Physical qubit mapping | ✗ | ✓ |
| Execution parameters | ✗ | ✓ |
| Result verification hash | ✗ | ✓ |

---

## 2. Proposed Solution

### 2.1 Extension Namespace

```
Namespace: qbom
URI: https://qbom.csnp.org/schema/1.0
```

### 2.2 Extension Properties

The QBOM extension adds the following top-level properties to CycloneDX:

```json
{
  "extensions": {
    "qbom": {
      "version": "1.0",
      "traceId": "qbom_a1b2c3d4",
      "contentHash": "3c7a2b1f9e8d4a5b",
      "circuits": [...],
      "transpilation": {...},
      "hardware": {...},
      "execution": {...},
      "result": {...}
    }
  }
}
```

### 2.3 Schema Components

#### 2.3.1 Circuit Component

Captures the quantum circuit definition:

```json
{
  "name": "bell_state",
  "numQubits": 2,
  "numClbits": 2,
  "depth": 2,
  "gates": {
    "total": 3,
    "single": 1,
    "two": 1,
    "three": 0,
    "multi": 0,
    "breakdown": {"h": 1, "cx": 1, "measure": 2}
  },
  "hash": "sha256:...",
  "qasm": "OPENQASM 2.0; ..."
}
```

#### 2.3.2 Transpilation Component

Captures how the circuit was compiled for hardware:

```json
{
  "optimizationLevel": 3,
  "layoutMethod": "sabre",
  "routingMethod": "sabre",
  "basisGates": ["id", "rz", "sx", "x", "cx"],
  "couplingMap": [[0,1], [1,2], ...],
  "initialLayout": {"0": 12, "1": 15},
  "finalLayout": {"0": 12, "1": 15},
  "inputCircuit": {...},
  "outputCircuit": {...}
}
```

#### 2.3.3 Hardware Component

Captures the quantum hardware and calibration state:

```json
{
  "provider": "ibm_quantum",
  "backend": "ibm_brisbane",
  "numQubits": 127,
  "qubitsUsed": [12, 15],
  "isSimulator": false,
  "calibration": {
    "timestamp": "2025-01-15T06:00:00Z",
    "qubits": [
      {
        "index": 12,
        "t1Us": 145.2,
        "t2Us": 98.1,
        "frequency": 5.123,
        "readoutError": 0.018
      }
    ],
    "gates": [
      {
        "gate": "cx",
        "qubits": [12, 15],
        "error": 0.0082,
        "duration": 340
      }
    ]
  }
}
```

#### 2.3.4 Execution Component

Captures job execution parameters:

```json
{
  "shots": 4096,
  "seed": null,
  "jobId": "cq8x7k2j9f",
  "submittedAt": "2025-01-15T10:30:00Z",
  "completedAt": "2025-01-15T10:30:02Z",
  "executionTime": 2.3,
  "errorMitigation": {
    "method": "twirled_readout_error_extinction",
    "numRandomizations": 16
  }
}
```

#### 2.3.5 Result Component

Captures measurement outcomes:

```json
{
  "counts": {
    "raw": {"00": 2012, "01": 43, "10": 48, "11": 1993},
    "normalized": {"00": 0.4912, "11": 0.4866, ...}
  },
  "hash": "sha256:...",
  "metadata": {}
}
```

---

## 3. Use Cases

### 3.1 Academic Reproducibility

Researchers can attach QBOM traces to publications:

```bibtex
@article{quantum2025,
  title = {Novel Quantum Algorithm},
  qbom = {qbom_7x8k2mf9},
  qbom_hash = {3c7a2b1f9e8d4a5b}
}
```

### 3.2 Experiment Comparison

Organizations can compare experiments across time:

```bash
qbom diff qbom_7x8k2mf9 qbom_3j9x1kp2
```

### 3.3 Supply Chain Transparency

Quantum service providers can document:
- Which physical qubits were used
- Calibration state at execution time
- Complete software stack

### 3.4 Audit and Compliance

Regulated industries can verify:
- Experiment reproducibility
- Hardware configuration at execution
- Software integrity

---

## 4. Implementation

### 4.1 Reference Implementation

A reference implementation is available at:
- **Repository:** https://github.com/csnp/qbom
- **Documentation:** https://qbom.csnp.org

### 4.2 Framework Support

| Framework | Status |
|-----------|--------|
| Qiskit (IBM) | Supported |
| Cirq (Google) | Supported |
| PennyLane (Xanadu) | Supported |
| Braket (AWS) | Planned |

### 4.3 Integration Example

```python
import qbom  # Invisible capture enabled

# Your existing quantum code
from qiskit import QuantumCircuit, transpile
from qiskit_ibm_runtime import QiskitRuntimeService

qc = QuantumCircuit(2)
qc.h(0)
qc.cx(0, 1)
qc.measure_all()

service = QiskitRuntimeService()
backend = service.backend("ibm_brisbane")
job = backend.run(transpile(qc, backend), shots=4096)
result = job.result()

# Export as CycloneDX with QBOM extension
trace = qbom.current()
trace.export("experiment.cdx.json", format="cyclonedx")
```

---

## 5. Compatibility

### 5.1 CycloneDX Version

This extension is designed for CycloneDX 1.5 and later.

### 5.2 Backward Compatibility

The extension uses the standard CycloneDX `extensions` mechanism, ensuring:
- Existing tools can process the base SBOM
- QBOM-aware tools can extract quantum-specific data
- No breaking changes to existing workflows

### 5.3 Forward Compatibility

The extension schema is versioned independently:
- Minor versions add optional fields
- Major versions may change required fields
- Version is always included for parser compatibility

---

## 6. Security Considerations

### 6.1 Sensitive Data

QBOM traces may contain:
- Provider API keys (must be excluded)
- Job IDs (may enable result lookup)
- Proprietary circuits (user discretion)

The reference implementation:
- Never captures credentials
- Allows selective field exclusion
- Supports circuit obfuscation

### 6.2 Integrity Verification

Each trace includes a content hash for tamper detection:

```json
{
  "contentHash": "3c7a2b1f9e8d4a5b"
}
```

This hash covers:
- Circuit definitions
- Transpilation parameters
- Hardware configuration
- Execution parameters
- Result hashes

---

## 7. JSON Schema

The complete JSON Schema for the QBOM extension is available at:

```
https://qbom.csnp.org/schema/qbom-extension-1.0.json
```

---

## 8. References

1. CycloneDX Specification: https://cyclonedx.org/specification/
2. QBOM Specification: https://github.com/csnp/qbom/blob/main/docs/specs/qbom-spec-1.0.json
3. QRAMM Framework: https://qramm.org
4. Qiskit Documentation: https://qiskit.org/documentation/
5. OpenQASM Specification: https://openqasm.com

---

## 9. Acknowledgments

This proposal was developed by the CyberSecurity NonProfit (CSNP) as part of the QRAMM (Quantum Readiness Assurance Maturity Model) initiative.

Special thanks to:
- The CycloneDX community for the extensible SBOM framework
- The quantum computing community for reproducibility feedback
- OWASP for software security best practices

---

## Appendix A: Full Example

A complete CycloneDX document with QBOM extension:

```json
{
  "$schema": "http://cyclonedx.org/schema/bom-1.5.schema.json",
  "bomFormat": "CycloneDX",
  "specVersion": "1.5",
  "version": 1,
  "serialNumber": "urn:uuid:qbom_7x8k2mf9",
  "metadata": {
    "timestamp": "2025-01-15T10:30:00Z",
    "component": {
      "type": "application",
      "name": "bell-state-experiment",
      "version": "qbom_7x8k2mf9"
    },
    "properties": [
      {"name": "qbom:version", "value": "1.0"},
      {"name": "qbom:content-hash", "value": "3c7a2b1f9e8d4a5b"}
    ]
  },
  "components": [
    {
      "type": "library",
      "name": "qiskit",
      "version": "1.0.2",
      "purl": "pkg:pypi/qiskit@1.0.2"
    },
    {
      "type": "library",
      "name": "numpy",
      "version": "1.24.0",
      "purl": "pkg:pypi/numpy@1.24.0"
    }
  ],
  "extensions": {
    "qbom": {
      "version": "1.0",
      "traceId": "qbom_7x8k2mf9",
      "contentHash": "3c7a2b1f9e8d4a5b",
      "environment": {
        "python": "3.11.5",
        "platform": "Darwin",
        "quantumSdk": "qiskit"
      },
      "circuits": [{
        "name": "bell_state",
        "numQubits": 2,
        "depth": 2,
        "gates": {"total": 3, "h": 1, "cx": 1, "measure": 2},
        "hash": "sha256:a1b2c3..."
      }],
      "hardware": {
        "backend": "ibm_brisbane",
        "qubitsUsed": [12, 15],
        "calibration": {
          "timestamp": "2025-01-15T06:00:00Z",
          "qubits": [
            {"index": 12, "t1Us": 145.2, "t2Us": 98.1, "readoutError": 0.018},
            {"index": 15, "t1Us": 132.1, "t2Us": 89.3, "readoutError": 0.021}
          ],
          "gates": [
            {"gate": "cx", "qubits": [12, 15], "error": 0.0082}
          ]
        }
      },
      "execution": {
        "shots": 4096,
        "jobId": "cq8x7k2j9f"
      },
      "result": {
        "counts": {"00": 2012, "11": 1993, "01": 43, "10": 48},
        "hash": "sha256:..."
      }
    }
  }
}
```

---

## Appendix B: Reproducibility Score

The QBOM extension supports a reproducibility score (0-100) based on captured data:

| Component | Max Points | Description |
|-----------|------------|-------------|
| Environment | 20 | Software versions, platform |
| Circuit | 20 | Gate sequence, structure |
| Transpilation | 15 | Qubit mapping, optimization |
| Hardware | 25 | Backend, calibration snapshot |
| Execution | 10 | Shots, timing, job ID |
| Results | 10 | Counts, verification hash |

Interpretation:
- 90-100: Excellent - Fully reproducible
- 70-89: Good - Minor details missing
- 50-69: Fair - Some important info missing
- 25-49: Poor - Major gaps
- 0-24: Critical - Cannot reproduce
