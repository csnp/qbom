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
| `TRACE_ID` | Trace ID, or part of one. Not a file path; see [Trace files](#trace-files) |

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
| `TRACE_ID` | Trace ID, or part of one. Not a file path; see [Trace files](#trace-files) |

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
| `TRACE_ID` | Trace ID, or part of one. Not a file path; see [Trace files](#trace-files) |

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

The circuit rows compare the circuit each run executed. Transpilation maps
qubits, substitutes gates for the target basis and changes depth, so two runs of
the same source circuit at different optimization levels, or against different
backends, execute different circuits. Where a trace recorded a transpiled
circuit, that is the one compared, and the `Source circuit hash` row compares
the circuits as submitted. Where it did not, the circuit as submitted is
compared. The `Circuit compared` row and the line under the table say which.

**Example:** one source circuit transpiled to the basis `rz, sx, x, cx` at
optimization levels 0 and 3.

```bash
$ qbom diff qbom_45794141 qbom_b699d139

                           QBOM Comparison
╭─────────────────────┬──────────────────┬──────────────────┬───────╮
│ Property            │ qbom_45794141    │ qbom_b699d139    │ Match │
├─────────────────────┼──────────────────┼──────────────────┼───────┤
│ Python              │ 3.12.12          │ 3.12.12          │   ✓   │
│ Quantum SDK         │ qiskit==2.5.2    │ qiskit==2.5.2    │   ✓   │
│ Circuit compared    │ transpiled       │ transpiled       │   ✓   │
│ Circuit qubits      │ 3                │ 3                │   ✓   │
│ Circuit depth       │ 14               │ 6                │   ✗   │
│ Circuit gates       │ 16 (9 1q, 4 2q)  │ 8 (3 1q, 2 2q)   │   ✗   │
│ Circuit hash        │ 68e64e9917d33a7c │ c0ccfad4f8df576e │   ✗   │
│ Source circuit hash │ 1cff503a9be0a406 │ 1cff503a9be0a406 │   ✓   │
│ Backend             │ aer_simulator    │ aer_simulator    │   ✓   │
│ Physical qubits     │ []               │ []               │   ✓   │
│ Shots               │ 256              │ 256              │   ✓   │
╰─────────────────────┴──────────────────┴──────────────────┴───────╯
Circuit rows compare the transpiled circuit each trace executed, not the circuit as submitted.

⚠ Same source circuit, but transpilation produced different executed circuits
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
| `TRACE_ID` | Trace ID, or part of one. Not a file path; see [Trace files](#trace-files) |

**Example:**

```bash
$ qbom drift qbom_c4b17b13

╭───────────────────────── Calibration Drift Analysis ─────────────────────────╮
│ Drift Score: 35/100 (higher means more drift)                                │
│ Reproduction Feasibility: Medium                                             │
╰─────────────────────────────── qbom_c4b17b13 ────────────────────────────────╯

Recommendations:
  • Calibration is 3 days old - expect variation
  • Significant drift on qubits: 12, 15
```

The drift score runs the opposite way to the reproducibility score from
`qbom score`: 0 means no measured change, and a higher number means more drift.

A simulator has no hardware calibration, so for a simulator run drift does not
apply and no score is given:

```bash
$ qbom drift qbom_a5544aa9

╭───────────────────────── Calibration Drift Analysis ─────────────────────────╮
│ Drift Score: not applicable (simulator, no hardware calibration)             │
│ Reproduction Feasibility: Not applicable                                     │
╰─────────────────────────────── qbom_a5544aa9 ────────────────────────────────╯

Recommendations:
  • cirq.Simulator is a simulator, so calibration drift does not apply
  • A re-run can still return different counts unless the simulator is seeded
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
| `TRACE_ID` | Trace ID, or part of one. Not a file path; see [Trace files](#trace-files) |
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

# Export as YAML. Needs PyYAML: pip install -e ".[yaml]" in the checkout
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
| `TRACE_ID` | Trace ID, or part of one. Not a file path; see [Trace files](#trace-files) |

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

  ✓ QBOM document structure: QBOM 1.1 trace qbom_04b85c65
  ✓ Content hash against trace content: matches, ae7fde51df02706e
  ✓ Result hash against recorded counts: matches, 2326158e16888826 over 2
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

  ✓ QBOM document structure: QBOM 1.1 trace qbom_04b85c65
  ✓ Content hash against trace content: matches, ae7fde51df02706e
  ✗ Result hash against recorded counts: the file records 2326158e16888826,
its counts hash to dc0603dc165dd60e. The measurement outcomes changed after
this trace was written
  ✓ Execution timestamp order: in order, submitted_at then completed_at

VERDICT: verification failed (Result hash against recorded counts)

$ echo $?
1
```

A file whose package list was edited after it was written:

```bash
$ qbom verify forged.qbom.json

QBOM Verification

  ✓ QBOM document structure: QBOM 1.1 trace qbom_04b85c65
  ✗ Content hash against trace content: the file records ae7fde51df02706e,
its content hashes to 219945a40539a631. Circuits, transpilation, backend,
qubits used, shots, seed, environment, metadata or the recorded result hash
changed after this trace was written
  ✓ Result hash against recorded counts: matches, 2326158e16888826 over 2
outcomes
  ✓ Execution timestamp order: in order, submitted_at then completed_at

VERDICT: verification failed (Content hash against trace content)

$ echo $?
1
```

The content hash covers the circuits, the transpilation, the backend, the
qubits used, the shot count, the seed, the software environment (Python
version, platform and every package), the metadata (name, description, tags,
authors, paper and experiment id) and the recorded result hash. It does not
cover the counts themselves, so rewriting only the counts leaves it matching.
That case is caught by recomputing the result hash, which is why both checks
run and neither substitutes for the other.

Each trace records its format in `qbom_version`. Traces in format 1.0, written
by qbom 0.1.1 and earlier, were hashed without the environment and the
metadata. They still verify, against the content their format covered, and
the check says what it could not cover:

```
  ✓ Content hash against trace content: matches, fce1733fa9b3355d. Format 1.0
traces were hashed without the environment and the metadata, so those are not
checked
```

A file in a format this release does not know fails the content hash check,
because there is no way to tell what its hash was taken over.

A line marked `?` is a check that could not run, and it establishes nothing.
A result that is not counts, an expectation value for instance, is hashed over
a value the trace does not store, so its hash cannot be recomputed and is
reported that way rather than as verified.

---

### qbom init

Print how to enable capture in a script or notebook.

```bash
qbom init
```

It creates no files and changes nothing. Capture needs no setup beyond
`import qbom`.

**Example:**

```bash
$ qbom init
QBOM Initialization

Add this to your Python scripts or notebooks:

import qbom  # That's it!

Your experiments will be automatically captured.
Traces stored in: ~/.qbom/traces/
```

---

## Trace files

Every command except `qbom verify` takes a trace id and reads the trace from
the trace store, `~/.qbom/traces/`, where each trace is a file named
`<trace-id>.json`. A file path given in place of an id is refused with
`Trace not found`.

To work with a trace file someone sent you, check it, then add it to your store
under its id:

```bash
# Check the file. The document structure line names its trace id.
$ qbom verify homework3.qbom.json

QBOM Verification

  ✓ QBOM document structure: QBOM 1.0 trace qbom_5e0a91c2
  ...

# Add it to your trace store under that id
$ cp homework3.qbom.json ~/.qbom/traces/qbom_5e0a91c2.json

# Every other command now finds it
$ qbom show qbom_5e0a91c2
```

QBOM reads no environment variables of its own. The store is always
`~/.qbom/traces/` in the home directory of the user running it.

---

## Exit Codes

| Code | Description |
|------|-------------|
| 0 | Success |
| 1 | The trace was not found or could not be read, an export failed, or `qbom verify` found a hash that does not match |
| 2 | Usage error: an unknown command or option, a missing argument, or a `qbom verify` file that does not exist |

`qbom validate` exits 0 even when it reports FAIL
([#6](https://github.com/csnp/qbom/issues/6)), so it cannot yet gate a CI step.

---

## See Also

- [Usage Guide](USAGE.md) - Python usage examples
- [API Reference](API.md) - Python API documentation
