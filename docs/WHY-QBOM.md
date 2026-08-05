# Why QBOM?

**A plain-language guide for researchers, managers, and decision-makers.**

---

## The 30-Second Version

Quantum experiments are hard to reproduce. When someone says "I ran this on IBM's quantum computer and got 73% accuracy," there's no way to know:

- Which of IBM's 20+ quantum computers they used
- Which physical qubits on that computer (there are 127 of them)
- What the error rates were that day (they change every 24 hours)
- How their code was compiled for the hardware

**QBOM captures all of this automatically.** Add one line to your code, and every experiment is fully documented.

---

## The Problem: Quantum Results Can't Be Trusted

### A Real Scenario

Dr. Smith publishes a paper: "Our algorithm achieves 73% fidelity on a quantum computer."

Dr. Jones tries to reproduce it: "I only got 41%. Is the paper wrong? Is my code wrong?"

Neither knows the answer because Dr. Smith didn't record:
- The exact hardware state at the time
- How the quantum circuit was compiled
- Which physical qubits were assigned

**This is the quantum reproducibility crisis.**

### Why Quantum Is Different

In classical computing, running the same code gives the same results. In quantum computing:

| Factor | Classical | Quantum |
|--------|-----------|---------|
| Hardware state | Stable | Changes daily |
| Code compilation | Deterministic | Can vary each run |
| Physical location | Doesn't matter | Critical (which qubit) |
| Environmental noise | Negligible | Major factor |

Imagine if every time you ran Excel, the answers changed based on which chip in your computer happened to be warmest that morning. That's quantum computing today.

---

## The Solution: Invisible Provenance Capture

QBOM works like a flight recorder for quantum experiments.

### Before QBOM

```python
# Your quantum code
from qiskit import QuantumCircuit
circuit = QuantumCircuit(2)
circuit.h(0)
circuit.cx(0, 1)
# ... run experiment ...
# Hope you remembered to write down everything!
```

### After QBOM

```python
import qbom  # Add this line

# Your exact same quantum code
from qiskit import QuantumCircuit
circuit = QuantumCircuit(2)
circuit.h(0)
circuit.cx(0, 1)
# ... run experiment ...
# Everything is automatically captured!
```

**That's it.** One import. Your workflow doesn't change.

---

## What Gets Captured

QBOM automatically records:

### 1. Software Environment
- Python version
- All package versions (Qiskit, NumPy, etc.)
- Operating system

*Why it matters:* Different software versions can produce different results.

### 2. Quantum Circuit
- Gate sequence
- Number of qubits
- Circuit depth
- A "fingerprint" to verify the circuit hasn't changed

*Why it matters:* The circuit is your experiment's core logic.

### 3. Compilation Details
- How the circuit was optimized
- Which physical qubits were assigned
- What transformations were applied

*Why it matters:* The same circuit runs differently on different physical qubits.

### 4. Hardware Calibration (The Key Insight)
- Which quantum computer
- Which physical qubits
- Error rates at that moment
- Coherence times at that moment

*Why it matters:* **This is what makes QBOM essential.** Hardware calibration changes every day. Without this snapshot, reproduction is nearly impossible.

### 5. Execution Details
- Number of shots (repetitions)
- Job ID for traceability
- Timing information

### 6. Results
- Measurement outcomes
- A hash to verify results haven't been altered

---

## Who Benefits

### Researchers

**Problem:** "My colleague can't reproduce my results."

**Solution:** Share your QBOM trace. They can see exactly what hardware state you had.

### Journal Editors

**Problem:** "How do we verify quantum computing claims?"

**Solution:** Require QBOM traces as supplementary material.

### Funding Agencies

**Problem:** "Are these quantum results legitimate?"

**Solution:** QBOM provides auditable, verifiable provenance.

### Industry

**Problem:** "We need to document our quantum experiments for compliance."

**Solution:** QBOM exports to standard SBOM formats (CycloneDX, SPDX).

---

## The Reproducibility Score

QBOM includes a 0-100 score showing how reproducible your experiment is:

| Score | Grade | Meaning |
|-------|-------|---------|
| 90-100 | Excellent | Everything captured. Fully reproducible. |
| 70-89 | Good | Minor details missing. Likely reproducible. |
| 50-69 | Fair | Some important info missing. May be reproducible. |
| 25-49 | Poor | Major gaps. Difficult to reproduce. |
| 0-24 | Critical | Minimal documentation. Cannot reproduce. |

Run `qbom score <trace_id>` to see your score and get recommendations.

---

## Integration with Standards

QBOM doesn't reinvent the wheel. It extends existing standards:

### CycloneDX Compatibility

CycloneDX is the leading software bill of materials (SBOM) standard. QBOM exports to CycloneDX format, adding quantum-specific extensions.

```bash
qbom export my_trace experiment.cdx.json --format cyclonedx
```

### SPDX Compatibility

SPDX is another major SBOM standard. QBOM supports it too.

```bash
qbom export my_trace experiment.spdx.json --format spdx
```

This means QBOM traces work with existing software supply chain tools.

---

## Getting Started

### Installation

```bash
pip install qbom
```

### Basic Usage

```python
import qbom  # Add at the top of your script

# Your existing quantum code here
# ...

# View what was captured
qbom.show()

# Export for sharing
qbom.export("my_experiment.qbom.json")
```

### Command Line

```bash
# List your traces
qbom list

# View a trace
qbom show qbom_a1b2c3d4

# Check reproducibility score
qbom score qbom_a1b2c3d4

# Validate for publication
qbom validate qbom_a1b2c3d4 --publication

# Generate paper statement
qbom paper qbom_a1b2c3d4
```

---

## For Non-Technical Stakeholders

### What to Tell Your Team

> "QBOM is like version control for quantum experiments. It captures everything needed to reproduce our results, without changing how researchers work."

### Key Points for Proposals

1. **Zero friction:** Researchers add one line of code
2. **Complete capture:** Hardware state, software versions, everything
3. **Standards-based:** Works with existing SBOM tools
4. **Open source:** No vendor lock-in, community-driven

### Compliance Value

- Meets emerging quantum experiment documentation requirements
- Provides audit trail for regulated industries
- Integrates with existing software supply chain processes

---

## Frequently Asked Questions

### Does this slow down my experiments?

No. QBOM captures data during existing operations. There's no additional overhead.

### What about proprietary circuits?

You control what gets shared. Export only the metadata you're comfortable with.

### Does it work with simulators?

Yes. Simulator runs are captured too, though calibration data isn't relevant.

### What quantum frameworks are supported?

- Qiskit (IBM)
- Cirq (Google)
- PennyLane (Xanadu)
- More coming soon

### Is this only for academic research?

No. Industry users benefit from compliance documentation and reproducibility guarantees.

---

## Learn More

- **GitHub:** https://github.com/csnp/qbom
- **Specification:** https://github.com/csnp/qbom/blob/main/docs/specs/qbom-spec-1.0.json
- **QRAMM Framework:** https://qramm.org

---

## About CSNP

QBOM is developed by the CyberSecurity NonProfit (CSNP) as part of our mission to advance cybersecurity through open-source tools and education.

**Website:** https://csnp.org

---

*"Quantum experiments should be reproducible. QBOM makes it happen."*
