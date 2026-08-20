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
from datetime import datetime
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
    """
    Process PennyLane result into counts if applicable.

    A counts result is hashed by the same function every adapter uses, so
    `qbom verify` can recompute it from the stored counts. A result that is not
    counts, an expectation value for instance, is hashed over a value the trace
    does not store, and verification reports that hash as one it could not
    recompute rather than as one it checked.
    """
    try:
        # If result is a dictionary of counts (from qml.counts())
        if isinstance(result, dict):
            counts_dict = {str(k): int(v) for k, v in result.items()}
            total_shots = sum(counts_dict.values())
            return Counts(raw=counts_dict, shots=total_shots), result_hash(counts_dict)

        # If result is a numpy array or similar
        if hasattr(result, "tolist"):
            result_str = str(result.tolist())
        else:
            result_str = str(result)

        # For expectation values, we don't have counts
        return None, hashlib.sha256(result_str.encode()).hexdigest()[:16]

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
                submitted_at = utc_now()

                with capture_guard(adapter.name, "QNode call device"):
                    adapter.session.current_builder.set_hardware(_extract_device_info(self_qnode.device))

                result = original_call(self_qnode, *args, **kwargs)

                with capture_guard(adapter.name, "QNode call result"):
                    adapter._capture_qnode_result(self_qnode, result, submitted_at)

                return result

            qml.QNode.__call__ = wrapped_call
            self._original_functions["pennylane.QNode.__call__"] = (
                qml.QNode,
                "__call__",
                original_call,
            )
        except Exception:
            pass

    def _capture_qnode_result(self, qnode: Any, result: Any, submitted_at: datetime) -> None:
        """Record the tape, the shot count and the result of a QNode call."""
        builder = self.session.current_builder
        completed_at = utc_now()

        # A QNode does not always expose a tape, and reading it is the part of
        # this most likely to move between PennyLane releases. Losing the
        # circuit must not also lose the execution and the result below.
        try:
            tape = getattr(qnode, "tape", None) or getattr(qnode, "qtape", None)
            if tape is not None:
                builder.add_circuit(_extract_circuit_info(tape))
        except Exception:
            pass

        # Shots live on the device, as an int on older releases and as a Shots
        # object on newer ones.
        shots = getattr(qnode.device, "shots", None)
        if isinstance(shots, int):
            num_shots = shots
        elif shots is not None:
            num_shots = shots.total_shots if hasattr(shots, "total_shots") else 1
        else:
            num_shots = 1

        builder.set_execution(
            Execution(shots=num_shots, submitted_at=submitted_at, completed_at=completed_at),
        )

        counts, recorded_hash = _process_result(result, num_shots)
        if counts:
            builder.set_result(Result(counts=counts, hash=recorded_hash))
        else:
            # An expectation value is not counts. The hash covers the value
            # itself, which is kept in metadata rather than in counts.
            builder.set_result(
                Result(
                    counts=Counts(raw={}, shots=num_shots),
                    hash=recorded_hash,
                    metadata={"type": "expectation_value", "value": str(result)},
                )
            )

        self.session.finalize_trace()

    def _hook_device_creation(self, qml: Any) -> None:
        """Hook device creation to track active devices."""
        try:
            original_device = qml.device
            adapter = self

            @functools.wraps(original_device)
            def wrapped_device(name: str, *args: Any, **kwargs: Any) -> Any:
                device = original_device(name, *args, **kwargs)

                with capture_guard(adapter.name, "device creation"):
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
                submitted_at = utc_now()

                with capture_guard(adapter.name, "execute input"):
                    builder = adapter.session.current_builder
                    builder.set_hardware(_extract_device_info(device))

                    for tape in tapes if isinstance(tapes, (list, tuple)) else [tapes]:
                        try:
                            builder.add_circuit(_extract_circuit_info(tape))
                        except Exception:
                            pass

                result = original_execute(tapes, device, *args, **kwargs)

                with capture_guard(adapter.name, "execute result"):
                    builder = adapter.session.current_builder

                    shots = getattr(device, "shots", None)
                    num_shots = shots if isinstance(shots, int) else 1

                    builder.set_execution(
                        Execution(
                            shots=num_shots,
                            submitted_at=submitted_at,
                            completed_at=utc_now(),
                        )
                    )

                    _, recorded_hash = _process_result(result, num_shots)
                    builder.set_result(
                        Result(
                            counts=Counts(raw={}, shots=num_shots),
                            hash=recorded_hash,
                            metadata={"type": "batch_execution"},
                        )
                    )

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
