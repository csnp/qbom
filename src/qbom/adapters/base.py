"""
Base Adapter Interface

All framework adapters implement this interface, ensuring consistent
behavior across Qiskit, Cirq, PennyLane, etc.
"""

from __future__ import annotations

import warnings
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qbom.core.session import Session

# One report per stage per process. A wrapper sits on a hot path, and a
# framework that fails capture once usually fails it on every call.
_WARNED_STAGES: set[str] = set()


@contextmanager
def capture_guard(framework: str, stage: str) -> Iterator[None]:
    """
    Run capture work, and give up on the capture rather than on the caller.

    An adapter runs inside a call the user made for their own reasons.
    Provenance that is not captured costs a trace. An exception escaping a
    wrapper costs the experiment, and the experiment is why the user is here.
    So anything raised inside this block ends the capture, and the wrapped call
    goes on to return its normal result.

    The framework's own call must not be made inside this block. Wrap the
    capture before it and the capture after it, and leave the call between
    them, or a failing capture would swallow the user's result.

    The first failure of a stage is reported once, because a run that captured
    nothing must not be mistaken for a run with nothing to capture.
    """
    try:
        yield
    except Exception as exc:
        key = f"{framework}.{stage}"
        if key not in _WARNED_STAGES:
            _WARNED_STAGES.add(key)
            try:
                warnings.warn(
                    f"QBOM could not capture {stage} ({exc!r}). {framework} is unaffected; "
                    f"this part of the trace is missing.",
                    RuntimeWarning,
                    stacklevel=3,
                )
            except Exception:
                # Reporting the failure must not become the failure. Under an
                # error-promoting warning filter, such as -W error or
                # PYTHONWARNINGS=error, warnings.warn raises, and raising here
                # would abort the caller's own call: exactly the thing this
                # guard exists to prevent, reintroduced by the guard itself.
                pass


class Adapter(ABC):
    """
    Base class for framework adapters.

    An adapter hooks into a quantum framework to capture operations.
    Subclasses must implement install() and uninstall() methods.

    Design principles:
    - Non-invasive: Never change framework behavior
    - Graceful: Silently degrade if capture fails
    - Complete: Capture everything needed for reproducibility
    """

    name: str = "base"

    def __init__(self, session: Session) -> None:
        self.session = session
        self._installed = False
        self._original_functions: dict[str, Any] = {}

    @abstractmethod
    def install(self) -> None:
        """
        Install hooks into the framework.

        Called once when QBOM is imported and the framework is detected.
        Should wrap relevant functions to capture their inputs/outputs.
        """
        pass

    @abstractmethod
    def uninstall(self) -> None:
        """
        Remove hooks from the framework.

        Called on shutdown or when explicitly requested.
        Should restore all original function behavior.
        """
        pass

    def _wrap_function(
        self,
        module: Any,
        func_name: str,
        wrapper_factory: Any,
    ) -> None:
        """
        Safely wrap a function with a capture wrapper.

        Args:
            module: The module containing the function
            func_name: Name of the function to wrap
            wrapper_factory: Callable that takes (original_func) and returns wrapper
        """
        original = getattr(module, func_name, None)
        if original is None:
            return

        # Store original for restoration
        key = f"{module.__name__}.{func_name}"
        self._original_functions[key] = (module, func_name, original)

        # Install wrapper
        wrapper = wrapper_factory(original)
        setattr(module, func_name, wrapper)

    def _unwrap_function(self, key: str) -> None:
        """Restore original function."""
        if key in self._original_functions:
            module, func_name, original = self._original_functions[key]
            setattr(module, func_name, original)
            del self._original_functions[key]

    def _unwrap_all(self) -> None:
        """Restore all wrapped functions."""
        for key in list(self._original_functions.keys()):
            self._unwrap_function(key)
