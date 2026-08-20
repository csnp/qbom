"""
Cirq Adapter

Captures Cirq operations for Google quantum hardware and simulators:
- Circuit creation and manipulation
- Simulator execution
- Google Quantum Engine execution
- Measurement results
"""

from __future__ import annotations

import functools
import hashlib
from typing import TYPE_CHECKING, Any

from qbom.adapters.base import Adapter, capture_guard
from qbom.core.hashing import result_hash
from qbom.core.models import (
    Circuit,
    Counts,
    Execution,
    GateCounts,
    Hardware,
    Result,
)
from qbom.core.timeutil import utc_now

if TYPE_CHECKING:
    from qbom.core.session import Session


def _hash_circuit(circuit: Any) -> str:
    """Compute deterministic hash of a Cirq circuit."""
    try:
        # Use string representation for hashing
        circuit_str = str(circuit)
        return hashlib.sha256(circuit_str.encode()).hexdigest()[:16]
    except Exception:
        return hashlib.sha256(b"unknown").hexdigest()[:16]


def _circuit_to_model(circuit: Any) -> Circuit:
    """Convert Cirq Circuit to QBOM Circuit model."""
    try:
        import cirq

        # Count gates
        gate_counts: dict[str, int] = {}
        single_qubit = 0
        two_qubit = 0
        total = 0

        for moment in circuit:
            for op in moment:
                gate_name = type(op.gate).__name__.lower()
                gate_counts[gate_name] = gate_counts.get(gate_name, 0) + 1
                total += 1

                num_qubits = len(op.qubits)
                if num_qubits == 1:
                    single_qubit += 1
                elif num_qubits == 2:
                    two_qubit += 1

        gates = GateCounts(
            single_qubit=single_qubit,
            two_qubit=two_qubit,
            total=total,
            by_name=gate_counts,
        )

        # Get qubit count
        all_qubits = circuit.all_qubits()
        num_qubits = len(all_qubits)

        # Count measurement operations for classical bits
        num_clbits = sum(1 for op in circuit.all_operations() if isinstance(op.gate, cirq.MeasurementGate))

        return Circuit(
            name=None,
            num_qubits=num_qubits,
            num_clbits=num_clbits,
            depth=len(circuit),
            gates=gates,
            hash=_hash_circuit(circuit),
            qasm=None,  # Cirq uses different format
        )
    except Exception:
        # Fallback minimal circuit
        return Circuit(
            num_qubits=0,
            depth=0,
            gates=GateCounts(total=0),
            hash=_hash_circuit(circuit),
        )


def _extract_counts_from_result(result: Any, num_shots: int) -> Counts:
    """Extract measurement counts from Cirq result."""
    try:
        # Cirq results have measurements as numpy arrays
        counts_dict: dict[str, int] = {}

        if hasattr(result, "measurements"):
            # Get all measurement keys
            for key in result.measurements:
                measurement_array = result.measurements[key]
                # Convert each shot to bitstring
                for shot in measurement_array:
                    bitstring = "".join(str(bit) for bit in shot)
                    counts_dict[bitstring] = counts_dict.get(bitstring, 0) + 1

        if not counts_dict:
            # Try histogram method if available
            if hasattr(result, "histogram"):
                hist = result.histogram(key=list(result.measurements.keys())[0])
                counts_dict = {format(k, "b"): v for k, v in hist.items()}

        return Counts(raw=counts_dict, shots=num_shots)
    except Exception:
        return Counts(raw={}, shots=num_shots)


class CirqAdapter(Adapter):
    """
    Cirq framework adapter.

    Hooks into:
    - cirq.Simulator.run()
    - cirq.Simulator.simulate()
    - cirq.google.Engine.run() (if available)
    """

    name = "cirq"

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self._pending_circuits: list[Any] = []

    def install(self) -> None:
        """Install Cirq hooks."""
        if self._installed:
            return

        try:
            import cirq

            # Hook Simulator.run
            self._hook_simulator_run(cirq)

            # Hook Simulator.simulate (for state vector simulation)
            self._hook_simulator_simulate(cirq)

            # Hook DensityMatrixSimulator if available
            self._hook_density_matrix_simulator(cirq)

            # Hook Google Quantum Engine if available
            self._hook_quantum_engine()

            self._installed = True
        except ImportError:
            pass  # Cirq not installed

    def _hook_simulator_run(self, cirq: Any) -> None:
        """Hook cirq.Simulator.run() for sampling."""
        try:
            original_run = cirq.Simulator.run
            adapter = self

            @functools.wraps(original_run)
            def wrapped_run(
                self_sim: Any,
                program: Any,
                param_resolver: Any = None,
                repetitions: int = 1,
                **kwargs: Any,
            ) -> Any:
                submitted_at = utc_now()

                with capture_guard(adapter.name, "Simulator.run input"):
                    builder = adapter.session.current_builder
                    builder.add_circuit(_circuit_to_model(program))
                    builder.set_hardware(
                        Hardware(
                            provider="Cirq",
                            backend="cirq.Simulator",
                            num_qubits=len(program.all_qubits()),
                            is_simulator=True,
                        )
                    )

                result = original_run(self_sim, program, param_resolver, repetitions, **kwargs)

                with capture_guard(adapter.name, "Simulator.run result"):
                    builder = adapter.session.current_builder
                    builder.set_execution(
                        Execution(
                            shots=repetitions,
                            submitted_at=submitted_at,
                            completed_at=utc_now(),
                        )
                    )

                    counts = _extract_counts_from_result(result, repetitions)
                    builder.set_result(Result(counts=counts, hash=result_hash(counts.raw)))

                    adapter.session.finalize_trace()

                return result

            cirq.Simulator.run = wrapped_run
            self._original_functions["cirq.Simulator.run"] = (
                cirq.Simulator,
                "run",
                original_run,
            )
        except Exception:
            pass

    def _hook_simulator_simulate(self, cirq: Any) -> None:
        """Hook cirq.Simulator.simulate() for state vector simulation."""
        try:
            original_simulate = cirq.Simulator.simulate
            adapter = self

            # Forward the call verbatim rather than restating cirq's signature.
            # Restating it means restating its defaults, and they drift: this
            # wrapper declared `qubit_order=None` and passed it positionally,
            # while cirq's own default is QubitOrder.DEFAULT. So a plain
            # simulate(circuit) reached cirq as simulate(circuit, None, None)
            # and died inside the user's own call with
            # "Don't know how to interpret <None> as a Basis". A wrapper that
            # does not name a default cannot contradict one.
            @functools.wraps(original_simulate)
            def wrapped_simulate(self_sim: Any, *args: Any, **kwargs: Any) -> Any:
                with capture_guard(adapter.name, "Simulator.simulate input"):
                    program = args[0] if args else kwargs.get("program")
                    builder = adapter.session.current_builder
                    builder.add_circuit(_circuit_to_model(program))
                    builder.set_hardware(
                        Hardware(
                            provider="Cirq",
                            backend="cirq.Simulator (state vector)",
                            num_qubits=len(program.all_qubits()),
                            is_simulator=True,
                        )
                    )

                result = original_simulate(self_sim, *args, **kwargs)

                with capture_guard(adapter.name, "Simulator.simulate result"):
                    # State vector simulation is a single "shot".
                    adapter.session.current_builder.set_execution(
                        Execution(shots=1, completed_at=utc_now()),
                    )

                return result

            cirq.Simulator.simulate = wrapped_simulate
            self._original_functions["cirq.Simulator.simulate"] = (
                cirq.Simulator,
                "simulate",
                original_simulate,
            )
        except Exception:
            pass

    def _hook_density_matrix_simulator(self, cirq: Any) -> None:
        """Hook DensityMatrixSimulator if available."""
        try:
            if hasattr(cirq, "DensityMatrixSimulator"):
                original_run = cirq.DensityMatrixSimulator.run
                adapter = self

                @functools.wraps(original_run)
                def wrapped_run(
                    self_sim: Any,
                    program: Any,
                    param_resolver: Any = None,
                    repetitions: int = 1,
                    **kwargs: Any,
                ) -> Any:
                    submitted_at = utc_now()

                    with capture_guard(adapter.name, "DensityMatrixSimulator.run input"):
                        builder = adapter.session.current_builder
                        builder.add_circuit(_circuit_to_model(program))
                        builder.set_hardware(
                            Hardware(
                                provider="Cirq",
                                backend="cirq.DensityMatrixSimulator",
                                num_qubits=len(program.all_qubits()),
                                is_simulator=True,
                            )
                        )

                    result = original_run(self_sim, program, param_resolver, repetitions, **kwargs)

                    with capture_guard(adapter.name, "DensityMatrixSimulator.run result"):
                        builder = adapter.session.current_builder
                        builder.set_execution(
                            Execution(
                                shots=repetitions,
                                submitted_at=submitted_at,
                                completed_at=utc_now(),
                            )
                        )

                        counts = _extract_counts_from_result(result, repetitions)
                        builder.set_result(Result(counts=counts, hash=result_hash(counts.raw)))

                        adapter.session.finalize_trace()

                    return result

                cirq.DensityMatrixSimulator.run = wrapped_run
                self._original_functions["cirq.DensityMatrixSimulator.run"] = (
                    cirq.DensityMatrixSimulator,
                    "run",
                    original_run,
                )
        except Exception:
            pass

    def _hook_quantum_engine(self) -> None:
        """Hook Google Quantum Engine for real hardware execution."""
        try:
            import cirq_google

            if hasattr(cirq_google, "Engine"):
                # Hook the sampler's run method
                original_run = cirq_google.Engine.get_sampler
                adapter = self

                # This is more complex - would need to wrap the sampler
                # For now, document that Google hardware requires additional setup
                pass

        except ImportError:
            pass  # cirq_google not installed

    def uninstall(self) -> None:
        """Remove Cirq hooks."""
        self._unwrap_all()
        self._installed = False
