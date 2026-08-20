"""
QBOM Session Management

The Session is the invisible orchestrator that makes QBOM magic work.
When you `import qbom`, a session is automatically started and begins
capturing quantum operations.
"""

from __future__ import annotations

import atexit
import importlib
import importlib.abc
import platform
import sys
import threading
import warnings
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from qbom.core.models import Environment, Package
from qbom.core.timeutil import utc_now
from qbom.core.trace import Trace, TraceBuilder

if TYPE_CHECKING:
    from importlib.machinery import ModuleSpec
    from types import ModuleType

    from qbom.adapters.base import Adapter


def _notify_framework_imported(framework: str, session: Session | None = None) -> None:
    """
    Install or refresh the adapter for a framework that has just been imported.

    A failure here must never break the import that triggered it: the user's
    experiment matters more than its provenance. It is reported rather than
    swallowed, so a run without capture is not mistaken for a run with nothing
    to capture.
    """
    try:
        (session or Session.get())._reinstall_adapter_for(framework)
    except Exception as exc:
        warnings.warn(
            f"QBOM could not install its {framework} adapter after {framework} was "
            f"imported ({exc!r}). This run will not be captured for that framework.",
            RuntimeWarning,
            stacklevel=2,
        )


class _QBOMLoader(importlib.abc.Loader):
    """
    Loader proxy that notifies QBOM once the real module has finished executing.

    Everything is delegated to the loader the normal import machinery chose.
    The only addition is the callback after ``exec_module``, which is the
    earliest point at which the framework's classes exist and can be hooked.
    """

    def __init__(self, loader: Any, framework: str, session: Session | None = None) -> None:
        self._qbom_loader = loader
        self._qbom_framework = framework
        self._qbom_session = session

    def create_module(self, spec: ModuleSpec) -> ModuleType | None:
        return self._qbom_loader.create_module(spec)  # type: ignore[no-any-return]

    def exec_module(self, module: ModuleType) -> None:
        self._qbom_loader.exec_module(module)

        # Hand the module back to its real loader before anything can inspect
        # it, so __loader__ and __spec__.loader look exactly as they would
        # without QBOM installed. Code that calls inspect.getsource() or
        # isinstance(loader, SourceFileLoader) then behaves unchanged.
        try:
            module.__loader__ = self._qbom_loader
            spec = getattr(module, "__spec__", None)
            if spec is not None:
                spec.loader = self._qbom_loader
        except Exception:
            pass

        _notify_framework_imported(self._qbom_framework, self._qbom_session)

    def __getattr__(self, name: str) -> Any:
        # Guard the proxy's own attributes so a lookup before __init__ finishes
        # raises AttributeError instead of recursing.
        if name.startswith("_qbom_"):
            raise AttributeError(name)
        return getattr(self._qbom_loader, name)


class QBOMImportFinder(importlib.abc.MetaPathFinder):
    """
    Import hook to detect when quantum frameworks are imported after QBOM.

    This ensures adapters are installed even if qiskit/cirq/pennylane
    are imported after 'import qbom'.

    Only top-level framework packages are wrapped. Submodule imports cost one
    dictionary lookup and are otherwise ignored, so the adapter is reinstalled
    exactly once per framework, at the point its ``__init__`` has finished and
    its classes (``AerBackend``, for instance) exist.
    """

    # Map top-level distributions to their main framework
    WATCHED_MODULES = {
        "qiskit": "qiskit",
        "qiskit_aer": "qiskit",  # Part of qiskit ecosystem
        "qiskit_ibm_runtime": "qiskit",
        "cirq": "cirq",
        "cirq_google": "cirq",
        "pennylane": "pennylane",
    }

    def __init__(self, session: Session | None = None) -> None:
        self._session = session
        self._resolving: set[str] = set()

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None = None,
        target: ModuleType | None = None,
    ) -> ModuleSpec | None:
        """Called when Python tries to import a module."""
        if "." in fullname:
            return None

        framework = self.WATCHED_MODULES.get(fullname)
        if framework is None:
            return None

        if fullname in self._resolving:
            return None  # re-entrant call from the delegation below

        self._resolving.add(fullname)
        try:
            spec = self._find_real_spec(fullname, path, target)
        finally:
            self._resolving.discard(fullname)

        if spec is None or spec.loader is None:
            return None
        if isinstance(spec.loader, _QBOMLoader):
            return spec  # already wrapped, do not stack another proxy
        if not hasattr(spec.loader, "exec_module"):
            return None  # legacy loader, leave it to the normal machinery

        spec.loader = _QBOMLoader(spec.loader, framework, self._session)
        return spec

    def _find_real_spec(
        self,
        fullname: str,
        path: Sequence[str] | None,
        target: ModuleType | None,
    ) -> ModuleSpec | None:
        """
        Ask every other meta path finder, in order, for the real spec.

        Other QBOM finders are skipped as well as this one. Two of them stacked
        would wrap the loader twice, notify twice, and leave the proxy visible
        as the module's __loader__.

        Exceptions from a finder are deliberately not caught, because
        importlib does not catch them either. A sandbox that installs a finder
        raising ImportError to deny a module has to keep denying it with QBOM
        present; swallowing that here would turn this hook into a way around
        an import block for the six names it watches.
        """
        for finder in list(sys.meta_path):
            if finder is self or isinstance(finder, QBOMImportFinder):
                continue
            find_spec = getattr(finder, "find_spec", None)
            if find_spec is None:
                continue
            spec = find_spec(fullname, path, target)
            if spec is not None:
                return spec  # type: ignore[no-any-return]
        return None


class Session:
    """
    Global session manager for QBOM.

    A session captures all quantum operations from import to exit.
    Sessions can be nested for scoped experiments.
    """

    _instance: Session | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._traces: list[Trace] = []
        self._current_builder: TraceBuilder | None = None
        self._adapters: list[Adapter] = []
        self._storage_path = Path.home() / ".qbom" / "traces"
        self._auto_save = True
        self._started = False
        self._import_finder: QBOMImportFinder | None = None

    @classmethod
    def get(cls) -> Session:
        """Get or create the global session."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def auto_start(cls) -> None:
        """Auto-start session on import (called from __init__.py)."""
        session = cls.get()
        if not session._started:
            session.start()

    def start(self) -> None:
        """Start the session and install adapters."""
        if self._started:
            return

        self._started = True
        self._storage_path.mkdir(parents=True, exist_ok=True)

        # Capture initial environment
        self._current_builder = TraceBuilder()
        self._current_builder.set_environment(self._capture_environment())

        # Install import hook to detect quantum frameworks imported later
        self._import_finder = QBOMImportFinder(self)
        sys.meta_path.insert(0, self._import_finder)

        # Install adapters for frameworks already imported
        self._install_adapters()

        # Save traces on exit
        atexit.register(self._on_exit)

    def _capture_environment(self) -> Environment:
        """Capture current software environment."""
        packages = []

        # Get installed packages
        try:
            from importlib.metadata import distributions

            quantum_prefixes = (
                "qiskit",
                "cirq",
                "pennylane",
                "braket",
                "pytket",
                "pyquil",
            )
            for dist in distributions():
                name = dist.metadata["Name"]
                if name and any(name.lower().startswith(p) for p in quantum_prefixes):
                    packages.append(
                        Package(
                            name=name.lower(),
                            version=dist.version,
                            purl=f"pkg:pypi/{name.lower()}@{dist.version}",
                        )
                    )

            # Always include core scientific packages
            core_packages = ["numpy", "scipy"]
            for dist in distributions():
                name = dist.metadata["Name"]
                if name and name.lower() in core_packages:
                    packages.append(
                        Package(
                            name=name.lower(),
                            version=dist.version,
                            purl=f"pkg:pypi/{name.lower()}@{dist.version}",
                        )
                    )
        except Exception:
            pass  # Graceful degradation

        return Environment(
            python=platform.python_version(),
            platform=platform.platform(),
            packages=packages,
            timestamp=utc_now(),
        )

    # Mapping of framework name to adapter info
    ADAPTER_MAP = {
        "qiskit": ("qbom.adapters.qiskit", "QiskitAdapter"),
        "cirq": ("qbom.adapters.cirq", "CirqAdapter"),
        "pennylane": ("qbom.adapters.pennylane", "PennyLaneAdapter"),
    }

    def _install_adapters(self) -> None:
        """Detect and install available framework adapters."""
        for module_name in self.ADAPTER_MAP:
            if module_name in sys.modules:
                self._install_adapter_for(module_name)

    def _install_adapter_for(self, framework: str) -> None:
        """Install adapter for a specific framework."""
        if framework not in self.ADAPTER_MAP:
            return

        # Check if already installed
        adapter_module, adapter_class = self.ADAPTER_MAP[framework]
        for existing in self._adapters:
            if existing.name == framework:
                return  # Already installed

        try:
            mod = importlib.import_module(adapter_module)
            adapter = getattr(mod, adapter_class)(self)
            adapter.install()
            self._adapters.append(adapter)
        except ImportError:
            pass  # Adapter not available

    def _reinstall_adapter_for(self, framework: str) -> None:
        """Reinstall adapter to pick up newly imported classes."""
        if framework not in self.ADAPTER_MAP:
            return

        # Find existing adapter
        adapter_module, adapter_class = self.ADAPTER_MAP[framework]
        existing_adapter = None
        for adapter in self._adapters:
            if adapter.name == framework:
                existing_adapter = adapter
                break

        if existing_adapter:
            # Re-run install to hook any new classes
            existing_adapter.install()
        else:
            # Install for first time
            self._install_adapter_for(framework)

    @property
    def current_builder(self) -> TraceBuilder:
        """Get the current trace builder."""
        if self._current_builder is None:
            self._current_builder = TraceBuilder()
            self._current_builder.set_environment(self._capture_environment())
        return self._current_builder

    def finalize_trace(self) -> Trace:
        """
        Finalize and save the current trace.

        Called when an experiment completes (e.g., after job.result()).
        """
        if self._current_builder is None:
            raise RuntimeError("No active trace to finalize")

        trace = self._current_builder.build()
        self._traces.append(trace)

        if self._auto_save:
            self._save_trace(trace)

        # Start a new builder for the next experiment
        self._current_builder = TraceBuilder()
        self._current_builder.set_environment(self._capture_environment())

        return trace

    def _save_trace(self, trace: Trace) -> Path:
        """Save trace to local storage."""
        path = self._storage_path / f"{trace.id}.json"
        trace.export(path)
        return path

    def _on_exit(self) -> None:
        """Called when Python exits."""
        # Finalize any pending trace
        if self._current_builder and self._current_builder._data.get("result"):
            try:
                self.finalize_trace()
            except Exception:
                pass  # Don't raise during shutdown

        # Uninstall adapters
        for adapter in self._adapters:
            try:
                adapter.uninstall()
            except Exception:
                pass

        # Remove the import hook
        if self._import_finder is not None:
            try:
                sys.meta_path.remove(self._import_finder)
            except ValueError:
                pass
            self._import_finder = None

    # ========================================================================
    # Context Manager for Scoped Experiments
    # ========================================================================

    @contextmanager
    def experiment(
        self,
        name: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> Iterator[TraceBuilder]:
        """
        Context manager for scoped experiments.

        Example:
            with qbom.experiment("Bell State Test") as exp:
                # Your quantum code here
                pass
            # Trace is automatically finalized and saved
        """
        # Save current builder
        parent_builder = self._current_builder

        # Create new builder for this experiment
        self._current_builder = TraceBuilder()
        self._current_builder.set_environment(self._capture_environment())
        self._current_builder.set_metadata(name=name, description=description, tags=tags)

        try:
            yield self._current_builder
        finally:
            # Finalize this experiment
            if self._current_builder._data.get("result"):
                self.finalize_trace()

            # Restore parent builder
            self._current_builder = parent_builder

    # ========================================================================
    # Public API
    # ========================================================================

    def list_traces(self, limit: int = 10) -> list[Trace]:
        """List recent traces."""
        # Combine in-memory and saved traces
        traces = list(self._traces)

        # Load from disk
        if self._storage_path.exists():
            for path in sorted(self._storage_path.glob("*.json"), reverse=True):
                if len(traces) >= limit:
                    break
                try:
                    traces.append(Trace.model_validate_json(path.read_text()))
                except Exception:
                    pass

        return traces[:limit]


# ============================================================================
# Module-level convenience functions
# ============================================================================


def current() -> Trace:
    """
    Get the current or most recent trace.

    Returns the trace being built for the current experiment.
    If the current experiment has completed (e.g., after job.result()),
    returns the most recently finalized trace instead.
    """
    session = Session.get()
    builder = session.current_builder

    # If current builder has meaningful data, return it
    if builder._data.get("circuits") or builder._data.get("result"):
        return builder.build()

    # Otherwise return the most recent finalized trace if available
    if session._traces:
        return session._traces[-1]

    # Fall back to empty trace from current builder
    return builder.build()


def export(path: str | Path, format: str = "json") -> Path:
    """Export the current trace to a file."""
    trace = current()
    return trace.export(path, format=format)  # type: ignore


def show() -> None:
    """Display the current trace in the terminal."""
    trace = current()
    trace.show()


@contextmanager
def experiment(
    name: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
) -> Iterator[TraceBuilder]:
    """
    Context manager for scoped experiments.

    Example:
        import qbom

        with qbom.experiment("My Experiment") as exp:
            # Your quantum code here
            qc = QuantumCircuit(2)
            # ...

        # Trace is automatically saved
    """
    session = Session.get()
    with session.experiment(name, description, tags) as builder:
        yield builder
