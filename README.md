# QBOM

**Invisible Provenance Capture for Quantum Computing Experiments**

*One import. Complete reproducibility. Zero code changes.*

[![CI](https://github.com/csnp/qramm-qbom/actions/workflows/ci.yml/badge.svg)](https://github.com/csnp/qramm-qbom/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/csnp/qramm-qbom/graph/badge.svg)](https://codecov.io/gh/csnp/qramm-qbom)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-green.svg)](https://python.org)

[Why QBOM](#why-qbom) • [Quick Start](#quick-start) • [Features](#features) • [Documentation](#documentation) • [Contributing](#contributing)

---

## The Quantum Reproducibility Crisis

Quantum computing experiments are notoriously difficult to reproduce. When a paper claims *"We achieved 73% fidelity on Grover's algorithm"*, reviewers and researchers have no way to verify or reproduce the result because critical information is missing:

| What's Reported | What's Actually Needed |
|-----------------|------------------------|
| "Qiskit 1.0" | Exact versions of qiskit, qiskit-aer, numpy, scipy... |
| "IBM Brisbane" | Which of the 127 qubits? What were the error rates? |
| "4096 shots" | What optimization level? What routing algorithm? |

**The challenge?** You can't reproduce what you can't document.

QBOM solves this by automatically capturing complete experiment provenance—with zero code changes required.

---

## Why QBOM

| Capability | QBOM | Manual Logging | Notebooks |
|------------|------|----------------|-----------|
| Zero code changes | Yes | No | No |
| Automatic capture | Yes | No | No |
| Calibration data (T1, T2, error rates) | Yes | Rarely | Rarely |
| Transpilation details | Yes | Often forgotten | Often forgotten |
| Content verification (hashing) | Yes | No | No |
| SBOM export (CycloneDX/SPDX) | Yes | No | No |
| Reproducibility scoring | Yes | No | No |
| Multi-framework support | Yes | Custom | Custom |

---

## Quick Start

### Installation

Requires Python 3.10+ ([install Python](https://python.org))

**Copy and paste this entire block:**

```bash
git clone https://github.com/csnp/qramm-qbom.git
cd qramm-qbom
pip install -e ".[qiskit]"
qbom --version
```

**Framework options:**

```bash
pip install -e ".[qiskit]"      # Qiskit support (includes qiskit-aer)
pip install -e ".[cirq]"        # Cirq support
pip install -e ".[pennylane]"   # PennyLane support
pip install -e ".[yaml]"        # YAML export
pip install -e ".[all]"         # Everything above
```

### Basic Usage

```python
import qbom  # Add this single line - that's it!

# Your existing quantum code - unchanged
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator

qc = QuantumCircuit(2, name="bell_state")
qc.h(0)
qc.cx(0, 1)
qc.measure_all()

backend = AerSimulator()
job = backend.run(qc, shots=4096)
result = job.result()

# View what was captured
qbom.show()
```

Import order does not matter. QBOM installs an import hook, so a framework
imported after `import qbom` is still captured.

**Output:**

```
╭──────────────────────────── QBOM: qbom_f8b889f7 ─────────────────────────────╮
│ Summary: 2q circuit | on aer_simulator | 4,096 shots                         │
│ Created: 2026-08-05 23:13:13 UTC                                             │
│ Hash: be41da5c7a0a1b82                                                       │
│                                                                              │
│ ENVIRONMENT                                                                  │
│   Python:  3.14.3                                                            │
│   SDK:     qiskit==2.5.1                                                     │
│   qiskit: 2.5.1                                                              │
│   qiskit-aer: 0.17.2                                                         │
│   numpy: 2.5.1                                                               │
│   scipy: 1.18.0                                                              │
│                                                                              │
│ CIRCUIT                                                                      │
│   Name:    bell_state                                                        │
│   Qubits:  2                                                                 │
│   Depth:   3                                                                 │
│   Gates:   5 (1 1q, 1 2q)                                                    │
│   Hash:    ad3deb49eae5f780                                                  │
│                                                                              │
│ HARDWARE                                                                     │
│   Provider: Aer (Local)                                                      │
│   Backend:  aer_simulator                                                    │
│   Type:     Simulator                                                        │
│                                                                              │
│ EXECUTION                                                                    │
│   Job ID:  b0a26563-e881-4252-841f-96a5b9bc91bc                              │
│   Shots:   4,096                                                             │
│                                                                              │
│ RESULTS                                                                      │
│   |00⟩ ███████████████░░░░░░░░░░░░░░░  50.7%                                 │
│   |11⟩ ██████████████░░░░░░░░░░░░░░░░  49.3%                                 │
│                                                                              │
╰──────────────────────────────────────────────────────────────────────────────╯
```

### Try It Out

```bash
# Run the included example
python examples/basic_usage.py

# List captured traces
qbom list

# View a trace
qbom show <trace-id>

# Check reproducibility score
qbom score <trace-id>
```

---

## Features

### What QBOM Captures

| Category | What's Captured |
|----------|-----------------|
| **Environment** | Python version, all package versions |
| **Circuit** | Gates, depth, qubits, content hash |
| **Transpilation** | Optimization level, qubit mapping, routing |
| **Hardware** | Backend, calibration (T1, T2, error rates) |
| **Execution** | Shots, job ID, timestamps |
| **Results** | Counts, probabilities, result hash |

### Supported Frameworks

| Framework | Status |
|-----------|--------|
| **Qiskit** | Full support |
| **Cirq** | Supported |
| **PennyLane** | Supported |
| **Braket** | Planned |

### Reproducibility Score

QBOM calculates a 0-100 score showing how reproducible your experiment is:

| Score | Meaning |
|-------|---------|
| 90-100 | Excellent - fully reproducible |
| 70-89 | Good - minor details missing |
| 50-69 | Fair - some info missing |
| 25-49 | Poor - major gaps |
| 0-24 | Critical - cannot reproduce |

```bash
$ qbom score qbom_bdbddf3c

╭─────────────────────────── Reproducibility Score ────────────────────────────╮
│ 71/100 (Good)                                                                │
╰─────────────────────────────── qbom_bdbddf3c ────────────────────────────────╯
                     Score Breakdown
┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━┓
┃ Component     ┃ Category              ┃ Score ┃ Status ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━┩
│ Environment   │ Software              │ 20/20 │ ●      │
│ Circuit       │ Quantum Program       │ 17/20 │ ◐      │
│ Transpilation │ Circuit Compilation   │  7/15 │ ◐      │
│ Hardware      │ Backend & Calibration │  9/25 │ ◐      │
│ Execution     │ Run Parameters        │ 10/10 │ ●      │
│ Results       │ Output Verification   │  8/10 │ ●      │
└───────────────┴───────────────────────┴───────┴────────┘

Recommendations:
  • Consider storing QASM for exact circuit reproduction
  • Qubit mapping not captured - results depend on physical qubit assignment
```

### Export Formats

```bash
qbom export <id> trace.json              # JSON (default)
qbom export <id> trace.cdx.json -f cyclonedx   # CycloneDX SBOM
qbom export <id> trace.spdx.json -f spdx       # SPDX SBOM
qbom export <id> trace.yaml -f yaml            # YAML, needs pip install "qbom[yaml]"
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [Installation](docs/INSTALLATION.md) | Detailed installation guide |
| [Usage Guide](docs/USAGE.md) | Complete usage examples |
| [CLI Reference](docs/CLI.md) | All commands and options |
| [Python API](docs/API.md) | Python API reference |
| [Adapters](docs/ADAPTERS.md) | Framework adapter details |
| [Use Cases](docs/USE-CASES.md) | Real-world scenarios |
| [Why QBOM?](docs/WHY-QBOM.md) | Background and motivation |

### CLI Reference

```
qbom list                     List recent traces
qbom show <id>                Display trace details
qbom score <id>               Calculate reproducibility score
qbom validate <id>            Check trace completeness
qbom diff <id1> <id2>         Compare two traces
qbom drift <id>               Analyze calibration drift
qbom export <id> <file>       Export to file
qbom paper <id>               Generate paper statement
qbom verify <file>            Verify trace integrity
```

#### `qbom list` - View Recent Traces

```
$ qbom list

                          Recent QBOM Traces
╭───────────────┬──────────────────┬───────────────┬─────────┬───────╮
│ ID            │ Created          │ Backend       │ Circuit │ Shots │
├───────────────┼──────────────────┼───────────────┼─────────┼───────┤
│ qbom_c4b17b13 │ 2025-01-15 14:40 │ aer_simulator │ 2q, d=3 │ 4,096 │
│ qbom_bf522429 │ 2025-01-15 14:45 │ aer_simulator │ 2q, d=3 │ 1,024 │
│ qbom_b8678a13 │ 2025-01-15 14:46 │ aer_simulator │ 2q, d=3 │ 1,024 │
╰───────────────┴──────────────────┴───────────────┴─────────┴───────╯
```

#### `qbom validate` - Check Trace Completeness

```
$ qbom validate qbom_c4b17b13

╭────────────────────────────── Trace Validation ──────────────────────────────╮
│ PASS                                                                         │
│ Trace is valid with 1 suggestion(s)                                          │
╰─────────────────────────────── qbom_c4b17b13 ────────────────────────────────╯

Circuit:
  ℹ No QASM or JSON representation stored
    Fix: Consider storing QASM for exact circuit reproduction.

0 errors | 0 warnings | 1 info
```

#### `qbom paper` - Generate Paper Statement

```
$ qbom paper qbom_c4b17b13

Reproducibility Statement

(For Methods section)

Experiments were performed using qiskit==2.2.3 on the aer_simulator simulator.
Circuits were transpiled with optimization level 2. Each experiment used 4,096
shots.

Complete QBOM trace: qbom_c4b17b13
Content hash: a9463e429a524897
```

### Python API

```python
import qbom

# View current trace
qbom.show()

# Get trace object
trace = qbom.current()
print(trace.environment.packages)
print(trace.hardware.backend_name)

# Export
qbom.export("experiment.json")

# Scoped experiments
with qbom.experiment(name="VQE optimization"):
    # quantum code here
    pass
```

---

## How It Works

```python
import qbom                    # 1. Import hook installed
from qiskit import ...         # 2. Qiskit adapter activates
transpile(circuit, backend)    # 3. Transpilation captured
job = backend.run(circuit)     # 4. Execution captured
result = job.result()          # 5. Results captured, trace saved
```

Traces are stored in `~/.qbom/traces/`.

---

## Architecture

```
qramm-qbom/
├── src/qbom/
│   ├── core/           # Data models, trace builder, session
│   ├── adapters/       # Qiskit, Cirq, PennyLane hooks
│   ├── analysis/       # Scoring, drift, validation
│   ├── cli/            # Command-line interface
│   └── notebook/       # Jupyter integration
├── docs/               # Documentation
├── examples/           # Example scripts
└── tests/              # Test suite
```

---

## Roadmap

### v0.1 (Current)
- [x] Zero-code provenance capture
- [x] Qiskit, Cirq, PennyLane support
- [x] Reproducibility scoring
- [x] CycloneDX/SPDX export
- [x] CLI and Jupyter integration

### v0.2 (Next)
- [ ] AWS Braket adapter
- [ ] Enhanced drift analysis
- [ ] Remote trace storage

### v1.0 (Future)
- [ ] IonQ and Rigetti adapters
- [ ] Web dashboard
- [ ] Team collaboration

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

```bash
# Development setup
git clone https://github.com/csnp/qramm-qbom.git
cd qramm-qbom
pip install -e ".[dev,all]"

# Run tests
pytest

# Type check and lint
mypy src/qbom
ruff check src/qbom
```

---

## About CSNP

QBOM is developed by the [CyberSecurity NonProfit (CSNP)](https://csnp.org), a 501(c)(3) organization dedicated to making cybersecurity knowledge accessible to everyone.

### QRAMM Toolkit

QBOM is part of the [QRAMM](https://qramm.org) (Quantum Readiness Assurance Maturity Model) toolkit:

| Tool | Purpose |
|------|---------|
| **QBOM** | Quantum experiment reproducibility |
| [CryptoScan](https://github.com/csnp/qramm-cryptoscan) | Cryptographic vulnerability discovery |
| [TLS Analyzer](https://github.com/csnp/qramm-tls-analyzer) | TLS/SSL configuration analysis |

---

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details.

Copyright 2025 CyberSecurity NonProfit (CSNP)

---

## Citation

```bibtex
@software{qbom2025,
  title = {QBOM: Quantum Bill of Materials},
  author = {{CyberSecurity NonProfit (CSNP)}},
  year = {2025},
  url = {https://github.com/csnp/qramm-qbom}
}
```

---

<div align="center">

**Built with purpose by [CSNP](https://csnp.org)** — Advancing cybersecurity for everyone

[QRAMM](https://qramm.org) • [CSNP](https://csnp.org) • [Issues](https://github.com/csnp/qramm-qbom/issues)

</div>
