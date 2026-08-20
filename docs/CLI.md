# CLI Reference

Complete reference for the QBOM command-line interface.

## Overview

```bash
qbom [OPTIONS] COMMAND [ARGS]...
```

### Global Options

| Option | Description |
|--------|-------------|
| `--version` | Show version and exit |
| `--help` | Show help message and exit |

## Commands

### qbom list

List recent experiment traces.

```bash
qbom list [OPTIONS]
```

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `-n, --limit` | 10 | Number of traces to show |

**Example:**

```bash
$ qbom list

                          Recent QBOM Traces
╭───────────────┬──────────────────┬───────────────┬─────────┬───────╮
│ ID            │ Created          │ Backend       │ Circuit │ Shots │
├───────────────┼──────────────────┼───────────────┼─────────┼───────┤
│ qbom_c4b17b13 │ 2025-01-15 14:30 │ aer_simulator │ 2q, d=3 │ 4,096 │
│ qbom_a1b2c3d4 │ 2025-01-15 14:25 │ ibm_brisbane  │ 5q, d=8 │ 8,192 │
╰───────────────┴──────────────────┴───────────────┴─────────┴───────╯
```

---

### qbom show

Display detailed view of a trace.

```bash
qbom show TRACE_ID
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `TRACE_ID` | Trace ID or path to trace file |

**Example:**

```bash
$ qbom show qbom_c4b17b13

╭──────────────────────────── QBOM: qbom_c4b17b13 ─────────────────────────────╮
│ Summary: 2 circuits | on aer_simulator | 4,096 shots                         │
│ Created: 2025-01-15 14:30:07 UTC                                             │
│ Hash: a9463e429a524897                                                       │
│                                                                              │
│ ENVIRONMENT                                                                  │
│   Python:  3.11.12                                                           │
│   SDK:     qiskit==2.2.3                                                     │
│   ...                                                                        │
╰──────────────────────────────────────────────────────────────────────────────╯
```

---

### qbom score

Calculate and display reproducibility score.

```bash
qbom score TRACE_ID
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `TRACE_ID` | Trace ID or path to trace file |

**Example:**

```bash
$ qbom score qbom_c4b17b13

╭─────────────────────────── Reproducibility Score ────────────────────────────╮
│ 71/100 (Good)                                                                │
╰──────────────────────────────────────────────────────────────────────────────╯

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
```

**Score Grades:**

| Score | Grade |
|-------|-------|
| 90-100 | Excellent |
| 70-89 | Good |
| 50-69 | Fair |
| 25-49 | Poor |
| 0-24 | Critical |

---

### qbom validate

Validate a trace for completeness.

```bash
qbom validate TRACE_ID [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `TRACE_ID` | Trace ID or path to trace file |

**Options:**

| Option | Description |
|--------|-------------|
| `--publication` | Use stricter validation for publication |

**Example:**

```bash
$ qbom validate qbom_c4b17b13

╭────────────────────────────── Trace Validation ──────────────────────────────╮
│ PASS                                                                         │
│                                                                              │
│ Trace is valid with 1 suggestion(s)                                          │
╰─────────────────────────────── qbom_c4b17b13 ────────────────────────────────╯

Circuit:
  ℹ No QASM or JSON representation stored
    Fix: Consider storing QASM for exact circuit reproduction.

0 errors | 0 warnings | 1 info
```

**Publication mode:**

```bash
$ qbom validate qbom_c4b17b13 --publication
```

Uses stricter checks appropriate for academic publication.

---

### qbom diff

Compare two traces side by side.

```bash
qbom diff TRACE_ID_1 TRACE_ID_2
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `TRACE_ID_1` | First trace ID |
| `TRACE_ID_2` | Second trace ID |

**Example:**

```bash
$ qbom diff qbom_abc123 qbom_def456

╭─────────────────────────────────────────────────────────────────────╮
│ Property           │ qbom_abc123      │ qbom_def456      │ Match   │
├────────────────────┼──────────────────┼──────────────────┼─────────┤
│ Backend            │ ibm_brisbane     │ ibm_kyoto        │ ✗       │
│ Qubits Used        │ [12, 15]         │ [0, 1]           │ ✗       │
│ Optimization       │ 3                │ 2                │ ✗       │
│ Shots              │ 4096             │ 4096             │ ✓       │
│ Circuit Hash       │ ad3deb49...      │ ad3deb49...      │ ✓       │
╰─────────────────────────────────────────────────────────────────────╯

⚠ Different backends may explain result differences
```

---

### qbom drift

Analyze calibration drift for a trace.

```bash
qbom drift TRACE_ID
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `TRACE_ID` | Trace ID or path to trace file |

**Example:**

```bash
$ qbom drift qbom_c4b17b13

╭────────────────────────────── Calibration Drift ─────────────────────────────╮
│ Drift Score: 35/100                                                          │
│ Reproduction Feasibility: Medium                                             │
╰─────────────────────────────── qbom_c4b17b13 ────────────────────────────────╯

Recommendations:
  • Calibration is 3 days old - expect variation
  • Significant drift on qubits: 12, 15
```

---

### qbom export

Export a trace to a file.

```bash
qbom export TRACE_ID OUTPUT_FILE [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `TRACE_ID` | Trace ID or path to trace file |
| `OUTPUT_FILE` | Output file path |

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `-f, --format` | `json` | Export format: `json`, `cyclonedx`, `spdx`, `yaml` |

**Examples:**

```bash
# Export as JSON (default)
qbom export qbom_c4b17b13 trace.json

# Export as CycloneDX SBOM
qbom export qbom_c4b17b13 trace.cdx.json -f cyclonedx

# Export as SPDX SBOM
qbom export qbom_c4b17b13 trace.spdx.json -f spdx

# Export as YAML. Needs PyYAML: pip install "qbom[yaml]"
qbom export qbom_c4b17b13 trace.yaml -f yaml
```

---

### qbom paper

Generate a reproducibility statement for academic papers.

```bash
qbom paper TRACE_ID
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `TRACE_ID` | Trace ID or path to trace file |

**Example:**

```bash
$ qbom paper qbom_c4b17b13

Reproducibility Statement
─────────────────────────
Experiments were performed using qiskit==2.2.3 on the aer_simulator
backend. Circuits were transpiled with optimization level 2.
Each experiment used 4,096 shots.

Complete QBOM trace: qbom_c4b17b13
Content hash: a9463e429a524897
```

This statement can be included in your paper's Methods section.

---

### qbom verify

Check a QBOM file against the hashes it records.

```bash
qbom verify FILE
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `FILE` | Path to QBOM JSON file |

**Exit codes:**

| Code | Meaning |
|------|---------|
| `0` | Every recorded hash matches the content the file carries |
| `1` | A hash does not match, or the file is not a QBOM trace |

**Example:**

```bash
$ qbom verify experiment.qbom.json

QBOM Verification

  ✓ QBOM document structure: QBOM 1.0 trace qbom_ba1d3fbe
  ✓ Content hash against trace content: matches, 0909d25f80c0f8cf
  ✓ Result hash against recorded counts: matches, 6c6cb00ac5a34314 over 2
outcomes
  ✓ Execution timestamp order: in order, submitted_at then completed_at

VERDICT: every hash this file records matches the content it carries
A circuit hash is taken from the framework's own circuit object, which the
trace does not store, so an individual circuit body is not independently
checked.
```

A file whose measurement counts were edited after it was written:

```bash
$ qbom verify tampered.qbom.json

QBOM Verification

  ✓ QBOM document structure: QBOM 1.0 trace qbom_f71674c9
  ✓ Content hash against trace content: matches, fce1733fa9b3355d
  ✗ Result hash against recorded counts: the file records 2326158e16888826,
its counts hash to dc0603dc165dd60e. The measurement outcomes changed after
this trace was written
  ✓ Execution timestamp order: in order, submitted_at then completed_at

VERDICT: verification failed (Result hash against recorded counts)

$ echo $?
1
```

The content hash covers the circuits, the transpilation, the backend, the
qubits used, the shot count, the seed and the recorded result hash. It does
not cover the counts themselves, so rewriting only the counts leaves it
matching. That case is caught by recomputing the result hash, which is why
both checks run and neither substitutes for the other.

A line marked `?` is a check that could not run, and it establishes nothing.
A result that is not counts, an expectation value for instance, is hashed over
a value the trace does not store, so its hash cannot be recomputed and is
reported that way rather than as verified.

---

### qbom init

Initialize QBOM in the current project.

```bash
qbom init
```

Creates a `.qbom/` directory in the current project for project-specific configuration.

**Example:**

```bash
$ qbom init
Initialized QBOM in /path/to/project/.qbom/
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `QBOM_STORAGE_PATH` | Override default trace storage location |
| `QBOM_AUTO_SAVE` | Set to `0` to disable automatic trace saving |

**Example:**

```bash
export QBOM_STORAGE_PATH=/custom/path/traces
export QBOM_AUTO_SAVE=0
```

---

## Exit Codes

| Code | Description |
|------|-------------|
| 0 | Success |
| 1 | General error |
| 2 | Trace not found |
| 3 | Invalid input |

---

## See Also

- [Usage Guide](USAGE.md) - Python usage examples
- [API Reference](API.md) - Python API documentation
