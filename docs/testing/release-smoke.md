# Release smoke test: qramm-qbom

Manual pre-release walkthrough. Run it before every publish, from a clean
checkout in a fresh virtualenv, and record the actual output rather than a
summary. Every step below states an expected result, so a step can fail.

QBOM captures silently by design, which means a broken capture path looks
exactly like a successful run with nothing to capture. Several steps exist only
to tell those two apart. Do not skip them.

## 1. Clean install, the way the README says

```bash
python3 -m venv /tmp/qbom-smoke && source /tmp/qbom-smoke/bin/activate
pip install -e ".[qiskit]"
qbom --version
```

- [ ] Install exits 0.
- [ ] `python -c "import qiskit_aer"` succeeds. The `qiskit` extra must carry
      the simulator the examples import, not just `qiskit`.
- [ ] `qbom --version` prints the version in `pyproject.toml`.

## 2. Capture works in the documented import order

The premise of the tool is that import order does not matter. Test the order
the docs lead with, because it is the one that has broken before.

```bash
export HOME=$(mktemp -d)     # keep the real ~/.qbom out of the measurement
python examples/basic_usage.py
```

- [ ] Exits 0.
- [ ] Prints a trace panel with circuit, hardware, execution and results
      sections. `Summary: Empty trace` is a failure, not an empty experiment.
- [ ] `ls $HOME/.qbom/traces/` lists one JSON file.
- [ ] The paper statement renders as formatted text. Literal `[bold]` or
      `[dim]` markup in the output is a failure.
- [ ] The statement reads as sentences. "using qiskit==X. on the Y simulator"
      is a failure.

Then the reverse order, which has always worked and must keep working:

```bash
python - <<'EOF'
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
import qbom
qc = QuantumCircuit(2, 2); qc.h(0); qc.cx(0, 1); qc.measure([0, 1], [0, 1])
AerSimulator().run(qc, shots=128).result().get_counts()
print("circuits:", len(qbom.current().circuits))
EOF
```

- [ ] Prints `circuits: 1` or more.

## 3. Scoped experiments

```bash
python examples/scoped_experiment.py
```

- [ ] Exits 0 and reports two traces. An `AttributeError` on `qbom.experiment`
      means the public API is not exported.

## 4. Every documented command

Run each command the README, `docs/CLI.md` and `--help` show, against the trace
from step 2. Take the id from `qbom list`.

- [ ] `qbom list` shows the trace.
- [ ] `qbom show <id>` renders the panel.
- [ ] `qbom score <id>` prints a score with a component breakdown.
- [ ] `qbom validate <id>` prints a verdict.
- [ ] `qbom drift <id>` prints an analysis or an honest "no calibration".
- [ ] `qbom paper <id>` prints the statement.
- [ ] `qbom diff <id> <id>` prints a comparison table.
- [ ] `qbom export <id> /tmp/t.json` writes the file.
- [ ] `qbom export <id> /tmp/t.cdx.json -f cyclonedx` writes the file.
- [ ] `qbom export <id> /tmp/t.spdx.json -f spdx` writes the file.
- [ ] `qbom verify /tmp/t.json` reports the trace as authentic.

No command may answer `unknown command`, `unknown flag`, `no such option` or
`accepts at most N arg(s)`. If a command appears in help text or in a fix
suggestion, it must exist.

## 5. Failure paths report failure

A tool that reports success on a failure cannot be used in CI.

```bash
qbom score no_such_trace; echo "exit=$?"
qbom show no_such_trace; echo "exit=$?"
qbom export no_such_trace /tmp/x.json; echo "exit=$?"
```

- [ ] Each prints a "not found" message and exits **non-zero**.
- [ ] With PyYAML absent, `qbom export <id> /tmp/t.yaml -f yaml` names PyYAML
      and the install command, and exits non-zero. No traceback.
- [ ] With PyYAML present (`pip install -e ".[yaml]"`), the same command writes
      the file and exits 0.

## 6. Sample output in the docs is real

- [ ] Every sample output block in `README.md` was regenerated from a real run
      of the code directly above it, at this version. Stale panels are the
      usual defect: check the summary line, the section headings and the table
      columns, not only the numbers.
- [ ] Every `pip install` line in `README.md` and `docs/INSTALLATION.md`
      matches the extras in `pyproject.toml`.

## 7. Checks CI runs

```bash
ruff check src/qbom tests
ruff format --check src/qbom
mypy src/qbom --ignore-missing-imports
pytest
```

- [ ] All four pass.
- [ ] The import-hook tests in `tests/test_import_hook.py` ran rather than
      skipped. They skip when qiskit-aer is missing, and a skipped test proves
      nothing.

## 8. Public repo hygiene

- [ ] `git status` shows no `CLAUDE.md`, `.claude/`, `.cursorrules` or
      credential file staged.
- [ ] `.git/info/exclude` covers those paths.

## Result

- Date:
- Tester:
- Version under test:
- Python version:
- Verdict: PASS / FAIL
- Notes:
