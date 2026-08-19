# Changelog

All notable changes to QBOM are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

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

- Timestamps in exported traces now carry a UTC offset. A field that read
  `"created_at": "2026-08-19T21:48:41.891059"` now reads `"created_at":
  "2026-08-19T21:48:41.891059+00:00"`. The instant is the same and the trace
  content hash does not move, because it never covered timestamps. A trace
  written by an earlier release is not rewritten when it is read: its
  timestamps stay exactly as they are on disk, without an offset.
- README and docs sample output regenerated from an actual run. The previous
  samples predated several output changes.
- CI runs on Python 3.13 as well as 3.10 to 3.12.
