"""
PennyLane Adapter

Captures PennyLane operations for hybrid quantum-classical workflows:
- Device creation and configuration
- QNode execution
- Measurement results
- Gradient computations
"""

from __future__ import annotations

import functools
import hashlib
from typing import TYPE_CHECKING, Any

from qbom.adapters.base import Adapter
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


def _extract_circuit_info(tape: Any) -> Circuit:
    """Extract circuit information from a PennyLane tape."""
    try:
        # Count operations
        gate_counts: dict[str, int] = {}
        single_qubit = 0
        two_qubit = 0
        total = 0

        for op in tape.operations:
            gate_name = op.name.lower()
            gate_counts[gate_name] = gate_counts.get(gate_name, 0) + 1
            total += 1

            num_wires = len(op.wires)
            if num_wires == 1:
                single_qubit += 1
            elif num_wires == 2:
                two_qubit += 1

        gates = GateCounts(
            single_qubit=single_qubit,
            two_qubit=two_qubit,
            total=total,
            by_name=gate_counts,
        )

        # Get wire count
        num_qubits = len(tape.wires)

        # Count measurements
        num_measurements = len(tape.measurements)

        # Compute circuit hash from operations
        ops_str = str([(op.name, op.wires.tolist(), op.parameters) for op in tape.operations])
        circuit_hash = hashlib.sha256(ops_str.encode()).hexdigest()[:16]

        return Circuit(
            name=tape.name if hasattr(tape, "name") else None,
            num_qubits=num_qubits,
            num_clbits=num_measurements,
            depth=len(tape.operations),  # Simplified depth
            gates=gates,
            hash=circuit_hash,
        )
    except Exception:
        return Circuit(
            num_qubits=0,
            depth=0,
            gates=GateCounts(total=0),
            hash=hashlib.sha256(b"unknown").hexdigest()[:16],
        )


def _extract_device_info(device: Any) -> Hardware:
    """Extract hardware information from a PennyLane device."""
    try:
        # Determine provider based on device name
        device_name = device.name if hasattr(device, "name") else str(type(device).__name__)
        short_name = device.short_name if hasattr(device, "short_name") else device_name

        # Detect provider
        provider = "PennyLane"
        if "qiskit" in device_name.lower():
            provider = "IBM Quantum (via PennyLane)"
        elif "cirq" in device_name.lower():
            provider = "Google (via PennyLane)"
        elif "braket" in device_name.lower():
            provider = "AWS Braket (via PennyLane)"
        elif "lightning" in device_name.lower():
            provider = "PennyLane Lightning"

        # Check if simulator
        is_simulator = any(sim in device_name.lower() for sim in ["default", "lightning", "simulator", "sim"])

        # Get number of wires/qubits
        num_qubits = device.num_wires if hasattr(device, "num_wires") else 0

        return Hardware(
            provider=provider,
            backend=short_name,
            num_qubits=num_qubits,
            is_simulator=is_simulator,
        )
    except Exception:
        return Hardware(
            provider="PennyLane",
            backend="unknown",
            num_qubits=0,
            is_simulator=True,
        )


def _process_result(result: Any, shots: int | None) -> tuple[Counts | None, str]:
    """Process PennyLane result into counts if applicable."""
    try:
        # If result is a dictionary of counts (from qml.counts())
        if isinstance(result, dict):
            counts_dict = {str(k): int(v) for k, v in result.items()}
            total_shots = sum(counts_dict.values())
            result_hash = hashlib.sha256(str(sorted(counts_dict.items())).encode()).hexdigest()[:16]
            return Counts(raw=counts_dict, shots=total_shots), result_hash

        # If result is a numpy array or similar
        if hasattr(result, "tolist"):
            result_str = str(result.tolist())
        else:
            result_str = str(result)

        result_hash = hashlib.sha256(result_str.encode()).hexdigest()[:16]

        # For expectation values, we don't have counts
        return None, result_hash

    except Exception:
        return None, hashlib.sha256(b"unknown").hexdigest()[:16]


class PennyLaneAdapter(Adapter):
    """
    PennyLane framework adapter.

    Hooks into:
    - QNode execution
    - Device creation
    - qml.execute()
    """

    name = "pennylane"

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self._active_devices: dict[int, Hardware] = {}

    def install(self) -> None:
        """Install PennyLane hooks."""
        if self._installed:
            return

        try:
            import pennylane as qml

            # Hook QNode.__call__
            self._hook_qnode_call(qml)

            # Hook device creation to track devices
            self._hook_device_creation(qml)

            # Hook qml.execute for batch execution
            self._hook_execute(qml)

            self._installed = True
        except ImportError:
            pass  # PennyLane not installed

    def _hook_qnode_call(self, qml: Any) -> None:
        """Hook QNode execution."""
        try:
            original_call = qml.QNode.__call__
            adapter = self

            @functools.wraps(original_call)
            def wrapped_call(self_qnode: Any, *args: Any, **kwargs: Any) -> Any:
                builder = adapter.session.current_builder

                # Capture device info
                device = self_qnode.device
                hardware = _extract_device_info(device)
                builder.set_hardware(hardware)

                submitted_at = utc_now()

                # Execute original
                result = original_call(self_qnode, *args, **kwargs)

                completed_at = utc_now()

                # Try to extract circuit info from the tape
                try:
                    if hasattr(self_qnode, "tape") and self_qnode.tape is not None:
                        circuit = _extract_circuit_info(self_qnode.tape)
                        builder.add_circuit(circuit)
                    elif hasattr(self_qnode, "qtape") and self_qnode.qtape is not None:
                        circuit = _extract_circuit_info(self_qnode.qtape)
                        builder.add_circuit(circuit)
                except Exception:
                    pass

                # Get shots from device
                shots = getattr(device, "shots", None)
                if isinstance(shots, int):
                    num_shots = shots
                elif shots is not None:
                    num_shots = shots.total_shots if hasattr(shots, "total_shots") else 1
                else:
                    num_shots = 1

                # Capture execution
                execution = Execution(
                    shots=num_shots,
                    submitted_at=submitted_at,
                    completed_at=completed_at,
                )
                builder.set_execution(execution)

                # Process result
                counts, result_hash = _process_result(result, num_shots)
                if counts:
                    qbom_result = Result(counts=counts, hash=result_hash)
                else:
                    # For expectation values, create a minimal result
                    qbom_result = Result(
                        counts=Counts(raw={}, shots=num_shots),
                        hash=result_hash,
                        metadata={"type": "expectation_value", "value": str(result)},
                    )
                builder.set_result(qbom_result)

                # Finalize trace
                adapter.session.finalize_trace()

                return result

            qml.QNode.__call__ = wrapped_call
            self._original_functions["pennylane.QNode.__call__"] = (
                qml.QNode,
                "__call__",
                original_call,
            )
        except Exception:
            pass

    def _hook_device_creation(self, qml: Any) -> None:
        """Hook device creation to track active devices."""
        try:
            original_device = qml.device
            adapter = self

            @functools.wraps(original_device)
            def wrapped_device(name: str, *args: Any, **kwargs: Any) -> Any:
                device = original_device(name, *args, **kwargs)

                # Store device info for later reference
                adapter._active_devices[id(device)] = _extract_device_info(device)

                return device

            qml.device = wrapped_device
            self._original_functions["pennylane.device"] = (qml, "device", original_device)
        except Exception:
            pass

    def _hook_execute(self, qml: Any) -> None:
        """Hook qml.execute for batch execution."""
        try:
            if not hasattr(qml, "execute"):
                return

            original_execute = qml.execute
            adapter = self

            @functools.wraps(original_execute)
            def wrapped_execute(
                tapes: Any,
                device: Any,
                *args: Any,
                **kwargs: Any,
            ) -> Any:
                builder = adapter.session.current_builder

                # Capture device
                hardware = _extract_device_info(device)
                builder.set_hardware(hardware)

                # Capture circuits from tapes
                if isinstance(tapes, (list, tuple)):
                    for tape in tapes:
                        try:
                            circuit = _extract_circuit_info(tape)
                            builder.add_circuit(circuit)
                        except Exception:
                            pass
                else:
                    try:
                        circuit = _extract_circuit_info(tapes)
                        builder.add_circuit(circuit)
                    except Exception:
                        pass

                submitted_at = utc_now()

                # Execute original
                result = original_execute(tapes, device, *args, **kwargs)

                completed_at = utc_now()

                # Get shots
                shots = getattr(device, "shots", None)
                num_shots = shots if isinstance(shots, int) else 1

                execution = Execution(
                    shots=num_shots,
                    submitted_at=submitted_at,
                    completed_at=completed_at,
                )
                builder.set_execution(execution)

                # Process result
                _, result_hash = _process_result(result, num_shots)
                qbom_result = Result(
                    counts=Counts(raw={}, shots=num_shots),
                    hash=result_hash,
                    metadata={"type": "batch_execution"},
                )
                builder.set_result(qbom_result)

                adapter.session.finalize_trace()

                return result

            qml.execute = wrapped_execute
            self._original_functions["pennylane.execute"] = (qml, "execute", original_execute)
        except Exception:
            pass

    def uninstall(self) -> None:
        """Remove PennyLane hooks."""
        self._unwrap_all()
        self._installed = False
