# QBOM Use Cases

Real-world scenarios where QBOM provides value.

---

## Use Case 1: Academic Paper Reproducibility

### The Problem

Dr. Chen publishes a paper: *"Novel VQE implementation achieves 95% accuracy on H2 molecule simulation."*

Six months later, Dr. Patel tries to reproduce it:
- Paper says "Qiskit 1.0" but there are 50+ Qiskit sub-packages
- Paper says "IBM Brisbane" but which of the 127 qubits?
- Paper says "optimization level 3" but what about layout and routing?
- Paper doesn't mention calibration data, which changes daily

**Result:** Dr. Patel gets 67% accuracy and can't determine why.

### The Solution

```python
import qbom  # Dr. Chen adds this one line

# ... VQE experiment code ...

# Generate reproducibility statement for paper
# $ qbom paper qbom_vqe_h2_final
```

**Paper now includes:**

```
Reproducibility Statement
─────────────────────────
Experiments were performed using qiskit==1.0.2, qiskit-aer==0.12.0,
numpy==1.24.3 on IBM Quantum ibm_brisbane (qubits 12, 15, 18).
Calibration data from 2025-01-15T06:00:00Z (T1: 145μs, 132μs, 128μs;
CX error: 0.82%). Circuits transpiled with optimization_level=3,
layout_method=sabre, routing_method=sabre, seed=42.
Each experiment: 8,192 shots.

QBOM trace: qbom_vqe_h2_final
Content hash: 3c7a2b1f9e8d4a5b
Supplementary material: experiment.qbom.json
```

**Dr. Patel can now:**
1. See exact software versions
2. Know which physical qubits were used
3. See calibration data at time of experiment
4. Understand transpilation choices
5. Compare their own trace to identify differences

---

## Use Case 2: Debugging Result Discrepancies

### The Problem

Your team runs the same algorithm twice and gets different results:
- Run A: 73% fidelity
- Run B: 58% fidelity

Nobody knows why.

### The Solution

```bash
$ qbom diff qbom_run_a qbom_run_b

╭─────────────────────────────────────────────────────────────────────╮
│ Property           │ Run A            │ Run B            │ Match   │
├────────────────────┼──────────────────┼──────────────────┼─────────┤
│ Backend            │ ibm_brisbane     │ ibm_brisbane     │ ✓       │
│ Physical Qubits    │ [12, 15]         │ [45, 46]         │ ✗       │
│ CX Error (q0-q1)   │ 0.82%            │ 2.1%             │ ✗       │
│ T1 (q0)            │ 145μs            │ 89μs             │ ✗       │
│ Calibration Date   │ 2025-01-15 06:00 │ 2025-01-15 06:00 │ ✓       │
│ Circuit Hash       │ ad3deb49...      │ ad3deb49...      │ ✓       │
│ Optimization       │ 2                │ 2                │ ✓       │
╰─────────────────────────────────────────────────────────────────────╯

⚠ Different physical qubits with significantly different error rates
  may explain the 15% fidelity difference.
```

**Answer:** The transpiler assigned different physical qubits. Run B used qubits with 2.5x higher CX error rate.

---

## Use Case 3: Regulatory Compliance

### The Problem

A quantum computing company needs to:
- Document all experiments for audit
- Prove experiments were run as claimed
- Integrate with existing SBOM tools

### The Solution

```bash
# Export the trace itself, then to standard SBOM formats
qbom export qbom_prod_run_123 audit/experiment.qbom.json
qbom export qbom_prod_run_123 audit/experiment.cdx.json -f cyclonedx
qbom export qbom_prod_run_123 audit/experiment.spdx.json -f spdx

# Verify integrity. This reads the QBOM trace, not the SBOM: the hashes are
# recomputed from the counts and content the trace records, which an SBOM
# export does not carry.
qbom verify audit/experiment.qbom.json
```

**CycloneDX output integrates with:**
- Dependency-Track
- OWASP tools
- Enterprise SBOM systems

**Audit trail includes:**
- Exact software versions (with PURLs)
- Hardware used
- Timestamp of execution
- Cryptographic hash for tamper detection

---

## Use Case 4: Teaching Quantum Computing

### The Problem

Students submit quantum computing assignments. The professor needs to:
- Verify students actually ran the experiments
- Check if they used the correct parameters
- Understand why some students get different results

### The Solution

**Assignment instructions:**
```
Submit your code AND the QBOM trace file:
$ qbom export <your-trace-id> homework3.qbom.json
```

**Grading:**
```bash
# Quick verification
$ qbom show homework3.qbom.json

# Check they used required parameters
$ qbom validate homework3.qbom.json

# Compare to reference solution
$ qbom diff reference.qbom.json homework3.qbom.json
```

---

## Use Case 5: Algorithm Benchmarking

### The Problem

You're comparing three quantum algorithms and need to ensure fair comparison:
- Same hardware conditions
- Same shot counts
- Controlled variables

### The Solution

```python
import qbom

algorithms = ["grover", "vqe", "qaoa"]

for algo in algorithms:
    with qbom.experiment(f"Benchmark: {algo}", tags=["benchmark"]):
        run_algorithm(algo)

# Compare all three
$ qbom list --tag benchmark

# Verify fair comparison
$ qbom diff qbom_grover qbom_vqe
$ qbom diff qbom_vqe qbom_qaoa
```

**Benchmark report shows:**
- All used same backend
- All used same optimization level
- Calibration data was consistent
- Only algorithm differed

---

## Use Case 6: Tracking Calibration Drift

### The Problem

Your experiment worked last week but fails today. Is it:
- Code changes?
- Hardware degradation?
- Calibration drift?

### The Solution

```bash
$ qbom drift qbom_last_week

╭────────────────────────────── Calibration Drift ─────────────────────────────╮
│ Drift Score: 72/100 (High)                                                   │
│ Reproduction Feasibility: Low                                                │
╰──────────────────────────────────────────────────────────────────────────────╯

Qubit Drift Analysis:
  Qubit 12: T1 dropped 45% (145μs → 80μs)
  Qubit 15: Readout error increased 3x (1.8% → 5.4%)
  CX(12,15): Error increased 2x (0.82% → 1.7%)

Recommendations:
  • Hardware calibration has drifted significantly
  • Consider re-running on different qubits
  • Current calibration may not support this circuit fidelity
```

**Answer:** Hardware degraded, not your code.

---

## Use Case 7: Collaborative Research

### The Problem

Research team across three institutions needs to:
- Share experimental configurations
- Reproduce each other's results
- Build on previous work

### The Solution

```bash
# Institution A runs experiment
$ qbom export qbom_initial_result experiment_v1.qbom.json

# Share via git/email/cloud
$ git add experiment_v1.qbom.json
$ git commit -m "Initial VQE results"

# Institution B reproduces and extends
$ qbom show experiment_v1.qbom.json  # See exact setup
$ # Run their own experiment
$ qbom diff experiment_v1.qbom.json qbom_our_run  # Compare

# Institution C reviews both
$ qbom verify experiment_v1.qbom.json  # Integrity check
$ qbom score experiment_v1.qbom.json   # Reproducibility assessment
```

---

## Use Case 8: Grant Reporting

### The Problem

Funding agency requires:
- Proof that quantum hardware was used
- Documentation of experimental methodology
- Evidence of reproducibility efforts

### The Solution

```bash
# Generate documentation package
qbom list --limit 50 > grant_experiments.txt
qbom export qbom_main_result grant/main_result.qbom.json
qbom paper qbom_main_result > grant/reproducibility_statement.txt
qbom score qbom_main_result > grant/reproducibility_score.txt

# Validate for publication standards
qbom validate qbom_main_result --publication
```

**Grant report includes:**
- List of all experiments run
- Detailed trace of key results
- Reproducibility score (71/100 - Good)
- Statement for publications

---

## Use Case 9: CI/CD for Quantum Code

### The Problem

Quantum algorithm library needs automated testing that:
- Verifies algorithms work correctly
- Catches regressions
- Documents expected behavior

### The Solution

```python
# tests/test_bell_state.py
import qbom
import pytest

def test_bell_state():
    # Run experiment
    result = run_bell_state_experiment()

    # Get trace
    trace = qbom.current()

    # Verify circuit structure
    assert trace.circuits[0].num_qubits == 2
    assert trace.circuits[0].depth <= 5

    # Verify results are Bell-like
    probs = trace.result.counts.probabilities
    assert probs.get("00", 0) > 0.45
    assert probs.get("11", 0) > 0.45
    assert probs.get("01", 0) < 0.05
    assert probs.get("10", 0) < 0.05

    # Export for regression tracking
    trace.export(f"tests/traces/bell_state_{trace.id}.json")
```

---

## Use Case 10: Customer Support

### The Problem

Customer reports: "Your quantum library gives wrong results on my system."

Support needs to:
- Understand customer's environment
- Reproduce the issue
- Identify root cause

### The Solution

**Customer submits:**
```bash
$ qbom export <trace-id> bug_report.qbom.json
```

**Support reviews:**
```bash
$ qbom show bug_report.qbom.json

# Environment: Python 3.9.1 (we require 3.10+)
# qiskit: 0.45.0 (outdated, known bug)
# Backend: local simulator (not real hardware)

$ qbom validate bug_report.qbom.json
# Warning: qiskit version 0.45.0 has known issues with...
```

**Root cause identified in minutes, not hours.**

---

## Summary

| Use Case | Key Benefit |
|----------|-------------|
| Academic Papers | Complete reproducibility documentation |
| Debugging | Quick identification of configuration differences |
| Compliance | Standard SBOM format integration |
| Teaching | Easy verification and comparison |
| Benchmarking | Controlled variable documentation |
| Drift Tracking | Hardware vs software issue identification |
| Collaboration | Shareable, verifiable experiment records |
| Grant Reporting | Automated documentation generation |
| CI/CD | Regression testing with trace verification |
| Support | Quick environment and configuration analysis |

---

## Next Steps

- [Installation](INSTALLATION.md) - Get started with QBOM
- [Usage Guide](USAGE.md) - Learn how to use QBOM
- [CLI Reference](CLI.md) - Command-line documentation
