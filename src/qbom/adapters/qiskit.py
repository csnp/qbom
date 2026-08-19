"""
Qiskit Adapter

Captures Qiskit operations invisibly:
- Circuit creation and manipulation
- Transpilation with all settings
- Backend selection and calibration
- Job execution and results
"""

from __future__ import annotations

import functools
import hashlib
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from qbom.adapters.base import Adapter
from qbom.core.models import (
    Calibration,
    Circuit,
    Counts,
    Execution,
    GateCounts,
    GateProperties,
    Hardware,
    QubitMapping,
    QubitProperties,
    Result,
    Transpilation,
)
from qbom.core.timeutil import utc_now

if TYPE_CHECKING:
    from qbom.core.session import Session


def _hash_circuit(circuit: Any) -> str:
    """Compute deterministic hash of a Qiskit circuit."""
    try:
        # Use QASM for hashing if available
        qasm = circuit.qasm()
        return hashlib.sha256(qasm.encode()).hexdigest()[:16]
    except Exception:
        # Fallback to gate sequence
        ops = str(circuit.data)
        return hashlib.sha256(ops.encode()).hexdigest()[:16]


def _circuit_to_model(circuit: Any, name: str | None = None) -> Circuit:
    """Convert Qiskit QuantumCircuit to QBOM Circuit model."""
    gate_counts = circuit.count_ops()

    # Classify gates
    single_qubit = 0
    two_qubit = 0
    for gate, count in gate_counts.items():
        # Common two-qubit gates
        if gate in ("cx", "cz", "cy", "swap", "iswap", "ecr", "rzz", "rxx", "ryy"):
            two_qubit += count
        elif gate not in ("measure", "barrier", "reset"):
            single_qubit += count

    gates = GateCounts(
        single_qubit=single_qubit,
        two_qubit=two_qubit,
        total=sum(gate_counts.values()),
        by_name=dict(gate_counts),
    )

    # Get QASM if circuit is small enough
    qasm = None
    if circuit.num_qubits <= 20:
        try:
            qasm = circuit.qasm()
        except Exception:
            pass

    return Circuit(
        name=name or circuit.name or None,
        num_qubits=circuit.num_qubits,
        num_clbits=circuit.num_clbits,
        depth=circuit.depth(),
        gates=gates,
        hash=_hash_circuit(circuit),
        qasm=qasm,
    )


def _extract_layout(layout: Any) -> QubitMapping | None:
    """Extract qubit mapping from Qiskit Layout object."""
    if layout is None:
        return None

    try:
        # Handle different Qiskit layout formats
        if hasattr(layout, "get_virtual_bits"):
            virtual_bits = layout.get_virtual_bits()
            mapping = {v._index: k for k, v in virtual_bits.items() if hasattr(v, "_index")}
            if mapping:
                return QubitMapping(logical_to_physical=mapping)
        elif hasattr(layout, "input_qubit_mapping"):
            return QubitMapping(logical_to_physical=dict(layout.input_qubit_mapping))
    except Exception:
        pass

    return None


def _capture_calibration(backend: Any) -> Calibration | None:
    """Capture hardware calibration from backend properties."""
    try:
        props = backend.properties()
        if props is None:
            return None

        timestamp = props.last_update_date or utc_now()

        # Capture qubit properties
        qubits = []
        for i in range(backend.num_qubits):
            try:
                qubits.append(
                    QubitProperties(
                        index=i,
                        t1_us=props.t1(i) * 1e6 if props.t1(i) else None,
                        t2_us=props.t2(i) * 1e6 if props.t2(i) else None,
                        readout_error=props.readout_error(i),
                        frequency_ghz=props.frequency(i) / 1e9 if props.frequency(i) else None,
                    )
                )
            except Exception:
                pass

        # Capture gate properties
        gates = []
        for gate in props.gates:
            try:
                if gate.gate in ("cx", "ecr", "cz"):  # Two-qubit gates
                    error = None
                    duration = None
                    for param in gate.parameters:
                        if param.name == "gate_error":
                            error = param.value
                        elif param.name == "gate_length":
                            duration = param.value * 1e9  # Convert to ns

                    gates.append(
                        GateProperties(
                            gate=gate.gate,
                            qubits=tuple(gate.qubits),
                            error=error,
                            duration_ns=duration,
                        )
                    )
            except Exception:
                pass

        return Calibration(
            timestamp=timestamp,
            qubits=qubits,
            gates=gates,
        )
    except Exception:
        return None


class QiskitAdapter(Adapter):
    """
    Qiskit framework adapter.

    Hooks into:
    - qiskit.transpile()
    - Backend.run()
    - Job.result()
    """

    name = "qiskit"

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self._pending_job_data: dict[str, dict[str, Any]] = {}

    def install(self) -> None:
        """Install Qiskit hooks."""
        try:
            import qiskit

            # Hook transpile (only once)
            if not self._installed:
                self._wrap_function(qiskit, "transpile", self._make_transpile_wrapper)

            # Always try to hook backend run - new backends may have been imported
            self._hook_backend_run()

            self._installed = True
        except ImportError:
            pass  # Qiskit not installed

    def _make_transpile_wrapper(self, original: Callable) -> Callable:
        """Create wrapper for qiskit.transpile()."""

        @functools.wraps(original)
        def wrapper(circuits: Any, backend: Any = None, **kwargs: Any) -> Any:
            # Capture input
            builder = self.session.current_builder
            is_list = isinstance(circuits, list)
            input_circuits = circuits if is_list else [circuits]

            # Capture input circuits
            for qc in input_circuits:
                builder.add_circuit(_circuit_to_model(qc, "input"))

            # Call original
            result = original(circuits, backend, **kwargs)

            # Capture output
            output_circuits = result if is_list else [result]
            output = output_circuits[0] if output_circuits else None

            # Build transpilation record
            transpilation = Transpilation(
                optimization_level=kwargs.get("optimization_level"),
                basis_gates=kwargs.get("basis_gates"),
                seed=kwargs.get("seed_transpiler"),
                layout_method=kwargs.get("layout_method"),
                routing_method=kwargs.get("routing_method"),
                initial_layout=_extract_layout(kwargs.get("initial_layout")),
                final_layout=_extract_layout(getattr(output, "_layout", None)) if output else None,
                input_circuit=_circuit_to_model(input_circuits[0]) if input_circuits else None,
                output_circuit=_circuit_to_model(output) if output else None,
            )
            builder.set_transpilation(transpilation)

            # Capture backend info
            if backend is not None:
                self._capture_backend(backend)

            return result

        return wrapper

    def _capture_backend(self, backend: Any) -> None:
        """Capture backend information."""
        builder = self.session.current_builder

        try:
            is_sim = hasattr(backend, "options") and getattr(backend.options, "simulator", False)
            if not is_sim:
                is_sim = "simulator" in backend.name.lower() or "aer" in backend.name.lower()
        except Exception:
            is_sim = False

        provider_name = "Unknown"
        try:
            if hasattr(backend, "provider") and callable(backend.provider):
                provider = backend.provider()
                if provider:
                    provider_name = type(provider).__name__
                    if "IBM" in provider_name or "ibm" in str(backend.name):
                        provider_name = "IBM Quantum"
        except Exception:
            pass  # Keep provider_name as Unknown

        # Local simulators don't have providers
        if provider_name == "Unknown" and "aer" in backend.name.lower():
            provider_name = "Aer (Local)"

        hardware = Hardware(
            provider=provider_name,
            backend=backend.name,
            num_qubits=backend.num_qubits,
            is_simulator=is_sim,
            calibration=_capture_calibration(backend),
        )
        builder.set_hardware(hardware)

    def _hook_backend_run(self) -> None:
        """Hook into backend.run() to capture execution."""
        adapter = self

        def make_run_wrapper(original_run: Callable, class_name: str) -> Callable:
            """Create a wrapper for a run method."""

            @functools.wraps(original_run)
            def wrapped_run(self_backend: Any, *args: Any, **kwargs: Any) -> Any:
                # Capture circuit if passed as first arg
                circuits = args[0] if args else kwargs.get("circuits")
                if circuits is not None:
                    adapter._capture_circuits_from_run(circuits)

                # Capture backend info
                adapter._capture_backend(self_backend)

                job = original_run(self_backend, *args, **kwargs)

                # Store job metadata for later capture
                try:
                    job_id = job.job_id()
                except Exception:
                    job_id = str(id(job))

                adapter._pending_job_data[job_id] = {
                    "submitted_at": utc_now(),
                    "shots": kwargs.get("shots", 4096),
                    "backend": self_backend,
                }

                # Hook job.result()
                original_result = job.result

                @functools.wraps(original_result)
                def wrapped_result(*result_args: Any, **result_kwargs: Any) -> Any:
                    result = original_result(*result_args, **result_kwargs)
                    adapter._capture_result(job, result, job_id)
                    return result

                job.result = wrapped_result

                return job

            return wrapped_run

        # Hook AerBackend.run (used by AerSimulator)
        try:
            from qiskit_aer.backends.aerbackend import AerBackend

            if not hasattr(AerBackend, "_qbom_hooked"):
                original_run = AerBackend.run
                AerBackend.run = make_run_wrapper(original_run, "AerBackend")
                AerBackend._qbom_hooked = True
                self._original_functions["AerBackend.run"] = (AerBackend, "run", original_run)
        except ImportError:
            pass

        # Hook BackendV2.run (for IBM backends and others)
        try:
            from qiskit.providers import BackendV2

            if not hasattr(BackendV2, "_qbom_hooked"):
                original_run = BackendV2.run
                BackendV2.run = make_run_wrapper(original_run, "BackendV2")
                BackendV2._qbom_hooked = True
                self._original_functions["BackendV2.run"] = (BackendV2, "run", original_run)
        except ImportError:
            pass

    def _capture_circuits_from_run(self, circuits: Any) -> None:
        """Capture circuits passed to run()."""
        builder = self.session.current_builder

        # Handle single circuit or list
        circuit_list = circuits if isinstance(circuits, list) else [circuits]

        for qc in circuit_list:
            try:
                builder.add_circuit(_circuit_to_model(qc))
            except Exception:
                pass  # Silently continue

    @classmethod
    def _get_instance(cls) -> QiskitAdapter | None:
        """Get the active QiskitAdapter instance."""
        from qbom.core.session import Session

        session = Session.get()
        for adapter in session._adapters:
            if isinstance(adapter, QiskitAdapter):
                return adapter
        return None

    def _capture_result(self, job: Any, result: Any, job_id: str | None = None) -> None:
        """Capture job result."""
        builder = self.session.current_builder

        if job_id is None:
            try:
                job_id = job.job_id()
            except Exception:
                job_id = str(id(job))

        # Get stored job data
        job_data = self._pending_job_data.pop(job_id, {})

        # Capture execution info
        execution = Execution(
            job_id=job_id,
            shots=job_data.get("shots", 4096),
            submitted_at=job_data.get("submitted_at"),
            completed_at=utc_now(),
        )
        builder.set_execution(execution)

        # Capture results
        try:
            # Handle different result formats
            if hasattr(result, "get_counts"):
                counts_dict = result.get_counts()
                if isinstance(counts_dict, list):
                    counts_dict = counts_dict[0]

                shots = sum(counts_dict.values())
                counts = Counts(raw=counts_dict, shots=shots)

                result_hash = hashlib.sha256(str(sorted(counts_dict.items())).encode()).hexdigest()[:16]

                qbom_result = Result(
                    counts=counts,
                    hash=result_hash,
                )
                builder.set_result(qbom_result)

                # Finalize the trace
                self.session.finalize_trace()

        except Exception:
            pass

    def uninstall(self) -> None:
        """Remove Qiskit hooks."""
        self._unwrap_all()
        self._installed = False
