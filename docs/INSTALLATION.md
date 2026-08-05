# Installation Guide

## Requirements

- Python 3.10 or higher
- pip (Python package manager)
- Git

## Quick Install

Copy and paste this entire block:

```bash
git clone https://github.com/csnp/qbom.git
cd qbom
pip install -e ".[qiskit]"
qbom --version
```

## Framework Options

Install with your preferred quantum framework:

```bash
# Qiskit (recommended for IBM Quantum). Includes qiskit-aer, which carries
# the AerSimulator the examples use.
pip install -e ".[qiskit]"

# Cirq (for Google Quantum)
pip install -e ".[cirq]"

# PennyLane (for hybrid quantum-classical)
pip install -e ".[pennylane]"

# YAML export (qbom export <id> out.yaml -f yaml)
pip install -e ".[yaml]"

# Everything above
pip install -e ".[all]"
```

### What Gets Installed

**Core dependencies** (always installed):
- rich >= 13.0.0 (terminal formatting)
- pydantic >= 2.0.0 (data models)
- click >= 8.0.0 (CLI)
- xxhash >= 3.0.0 (content hashing)

**Optional dependencies:**
- `[qiskit]`: qiskit >= 1.0.0, qiskit-aer >= 0.15.0
- `[cirq]`: cirq >= 1.0.0
- `[pennylane]`: pennylane >= 0.30.0
- `[yaml]`: pyyaml >= 6.0

## Verify Installation

```bash
# Check CLI
qbom --version
qbom --help

# Check Python import
python -c "import qbom; print('QBOM installed successfully')"
```

## Trace Storage

QBOM stores traces in your home directory:

```
~/.qbom/
└── traces/
    ├── qbom_abc123.json
    ├── qbom_def456.json
    └── ...
```

This directory is created automatically on first use.

## Development Installation

For contributing to QBOM:

```bash
git clone https://github.com/csnp/qbom.git
cd qbom

# Install with dev dependencies and all frameworks
pip install -e ".[dev,all]"

# Run tests
pytest

# Type check
mypy src/qbom

# Lint
ruff check src/qbom
```

## Upgrading

Pull the latest changes and reinstall:

```bash
cd qbom
git pull
pip install -e ".[qiskit]"
```

## Uninstalling

```bash
pip uninstall qbom
```

To remove stored traces:

```bash
rm -rf ~/.qbom
```

## Troubleshooting

### Import Errors

Check Python version:

```bash
python --version  # Should be 3.10+
```

### Framework Not Detected

Ensure `import qbom` appears **before** framework imports:

```python
# Correct
import qbom
from qiskit import QuantumCircuit

# Incorrect (may miss operations)
from qiskit import QuantumCircuit
import qbom
```

### Permission Errors

Fix trace directory permissions:

```bash
chmod 755 ~/.qbom
chmod 755 ~/.qbom/traces
```

## Next Steps

- [Usage Guide](USAGE.md) — Learn how to use QBOM
- [CLI Reference](CLI.md) — Command-line documentation
- [API Reference](API.md) — Python API documentation
