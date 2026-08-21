# Changelog

All notable changes to QBOM are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **Every SBOM QBOM exported named the wrong tool version.** SPDX declared
  `creationInfo.creators` as `["Tool: qbom-1.0"]`, and SPDX 2.3 defines that
  field as `Tool: <name>-<version>`, so every document asserted it was produced
  by qbom 1.0. The CycloneDX output carried a `qbom:version` property saying the
  same thing and no record of the tool at all. The cause was a conflation: the
  code used the trace FORMAT version, which is 1.0 and belongs to the file
  layout, where the TOOL version belongs. They are different numbers. SPDX and
  CycloneDX now both name the package version, read from the installed package
  so it cannot fall behind a release, and the format version is still reported
  under a name that cannot be mistaken for it.
- **The CycloneDX export was not valid CycloneDX.** It failed the 1.5 schema
  the document itself declares in its own `$schema` field, on three counts, so
  any conformant reader rejected it. The root carried an `extensions` key, and
  1.5 permits no additional root properties. `serialNumber` was
  `urn:uuid:` followed by the trace id, and a trace id is not a UUID. And
  `metadata.component.description` was emitted as null on any trace without a
  description, where the schema requires a string or nothing. The serial number
  is now a UUID derived from the trace id, so the same trace always exports the
  same one and it can still be recomputed by anyone holding the id. No field is
  emitted as null in either format.
- **`qbom verify` verified nothing.** It appended a literal `True` for each of
  four checks and then printed "VERDICT: QBOM appears authentic and complete",
  which was the only verdict it could reach. A trace whose measurement counts
  had been replaced passed. So did an edited shot count, `{}`, and
  `{"hello": "world"}`, and every one of them exited 0, so no script or CI step
  could tell a forgery from a real record. Verification now recomputes both
  hashes a trace carries and compares each against the value the file records.
  Rewriting the counts moves the result hash, which is recomputed from
  `result.counts.raw`. Rewriting the circuits, the transpilation, the backend,
  the qubits used, the shot count, the seed or the recorded result hash moves
  the content hash. The content hash covers the result hash and not the counts
  themselves, so both checks run and neither substitutes for the other. A
  mismatch, a document carrying no `qbom_version` and no `id`, and a file that
  is not a QBOM trace all exit 1.
- **A check that could not fail was shown as a check that passed.** "Circuit
  hash present" and "Result hash present" were presence tests reported beside
  a verdict about authenticity. Each line now says what was compared against
  what. A check that could not run is marked `?` and is counted as neither a
  pass nor a failure: a result hash taken over an expectation value covers a
  number the trace does not store, so it is reported as one that could not be
  recomputed rather than as one that verified.
- **`import qbom` could stop the script that imported it.** Capturing a backend
  built `Hardware(num_qubits=backend.num_qubits, ...)`, and `num_qubits` is
  legitimately `None` for an unbounded simulator such as Qiskit's
  `BasicSimulator`, so `transpile(circuit, BasicSimulator())` ended in
  `ValidationError: 1 validation error for Hardware`. Deleting the `import
  qbom` line made the same script run. `Hardware.num_qubits` now accepts a
  backend that reports no qubit count, and every place an adapter captures
  inside a wrapper around a call the user made, in all three adapters, now
  degrades to "not captured" instead of raising into that call. The first time
  a capture stage fails it reports itself once on stderr, so a run that
  captured nothing is not mistaken for a run with nothing to capture.
- **`README.md` called an attribute that does not exist.** The Python API
  snippet read `trace.hardware.backend_name`; the attribute is
  `trace.hardware.backend`, as `docs/API.md` already documented.
- **`cirq.Simulator().simulate(circuit)` ended in `ValueError: Don't know how to
  interpret <None> as a Basis`.** The wrapper restated Cirq's signature, and so
  restated its defaults, declaring `qubit_order=None` where Cirq's own default
  is `QubitOrder.DEFAULT`, then forwarding it positionally. A plain
  `simulate(circuit)` therefore reached Cirq with arguments the user never
  wrote, and failed inside the user's own call. The wrapper now forwards the
  call verbatim, so a default it does not name is a default it cannot
  contradict.
- **The audit workflow in `docs/USE-CASES.md` told the reader to verify the
  wrong file.** It ran `qbom verify` against the CycloneDX export. Integrity is
  established from the counts and content a trace records, which an SBOM export
  does not carry, so that only ever appeared to work while verification
  established nothing. The workflow now exports the trace as well and verifies
  that.
- **Every timestamp was recorded without saying which zone it was in.** Capture
  called `datetime.utcnow()`, which returns a value carrying no UTC offset and
  which Python 3.12 deprecated. Anyone reading a trace had to know by
  convention that the value was UTC rather than local time, and on Python 3.12
  and newer a capture emitted `DeprecationWarning: datetime.datetime.utcnow()
  is deprecated`. Timestamps QBOM stamps are now timezone-aware UTC. A
  timestamp with no offset, which is what every trace written by an earlier
  release contains, is read as UTC at the point it is compared, so `qbom drift`
  still reports on traces already on disk instead of ending in `TypeError:
  can't subtract offset-naive and offset-aware datetimes`. A timestamp sitting
  within one UTC offset of the earliest or latest datetime Python can hold
  cannot be moved to UTC without leaving that range, so it is compared in the
  offset it already carries rather than raising `OverflowError`. Such a file
  was readable before this change and stays readable.

- **Nothing was captured on Python 3.12 and newer.** `QBOMImportFinder`
  implemented `find_module()` and `load_module()`, an API Python 3.12 removed.
  The finder sat in `sys.meta_path` and was never consulted, so a framework
  imported after `import qbom` never got its adapter. Following the documented
  order (`import qbom` first) produced an empty trace, wrote nothing to
  `~/.qbom/traces/`, and exited 0 with no warning. The finder now implements
  `find_spec()` and wraps the module's loader, installing the adapter once the
  framework's own `__init__` has finished executing.
- **`pip install "qbom[qiskit]"` did not install the simulator the examples
  use.** The extra declared only `qiskit`, while `README.md` and both Qiskit
  examples import `qiskit_aer`, so the documented walkthrough stopped at
  `ModuleNotFoundError`. The extra now includes `qiskit-aer`.
- **`qbom export <id> out.yaml -f yaml` ended in a traceback.** PyYAML was
  imported unguarded and was not a declared dependency. There is now a `yaml`
  extra, and the missing dependency is reported with the command that installs
  it.
- **Every command taking a trace id exited 0 when the trace did not exist.**
  `show`, `export`, `diff`, `paper`, `score`, `drift` and `validate` printed
  "Trace not found" and returned success, so no script or CI step could detect
  the failure. They now exit 1. A damaged or unreadable trace file is reported
  the same way instead of raising.
- **`qbom.experiment()` was documented but not exported.** `README.md`,
  `docs/USAGE.md` and `examples/scoped_experiment.py` all call it; the example
  died on `AttributeError`.
- **The reproducibility statement was ungrammatical.** Software and hardware
  were joined with a period, producing "using qiskit==2.5.1. on the
  aer_simulator simulator", a fragment in text meant for a Methods section. An
  empty trace rendered the statement as a single ".".
- **`examples/basic_usage.py` printed formatting markup** (`[bold]...[/bold]`)
  instead of applying it.
- A partial trace id resolved through filesystem order, so the same id could
  select a different trace on a different machine. Matches are now ordered.

### Changed

- The CycloneDX export no longer embeds the whole trace. It used to carry a
  root `extensions` key holding a complete copy of the trace, including every
  captured package, which is what made the document invalid. The trace id and
  content hash travel in `metadata.properties` instead, so an SBOM can still be
  tied to the trace it came from, and the trace itself is exported by the same
  command without `-f`. A reader who was parsing `extensions.qbom` should read
  the trace export instead.
- The version is declared once, in `pyproject.toml`. `qbom.__version__` reads
  the version the package was installed with. It used to be a second literal in
  `src/qbom/__init__.py`, so bumping one and not the other made
  `qbom --version` and `qbom.__version__` disagree, with nothing to catch it.
- `qbom verify` sets an exit code. A clean file exits 0 and a failure exits 1,
  so a CI step can gate on it. Its output changed shape: the sample in
  `docs/CLI.md` was regenerated from an actual run.
- `Hardware.num_qubits` may be null. Every trace already on disk records an
  integer, and its content hash does not move, because the field was never
  covered by it. `docs/specs/qbom-spec-1.0.json` and `docs/API.md` say so.
- Timestamps in exported traces now carry a UTC offset. A field that read
  `"created_at": "2026-08-19T21:48:41.891059"` now reads `"created_at":
  "2026-08-19T21:48:41.891059+00:00"`. The instant is the same and the trace
  content hash does not move, because it never covered timestamps. A trace
  written by an earlier release is not rewritten when it is read: its
  timestamps stay exactly as they are on disk, without an offset.
- README and docs sample output regenerated from an actual run. The previous
  samples predated several output changes.
- CI runs on Python 3.13 as well as 3.10 to 3.12.
