"""Faults that the synthetic generator can append to a clean batch."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from models.telemetry import TelemetryEvent


class FaultKind(str, Enum):
    DUPLICATE_EVENT_ID = "duplicate_event_id"
    MISSING_FLIGHT_ID = "missing_flight_id"
    NEGATIVE_FUEL = "negative_fuel"
    INVALID_ALTITUDE = "invalid_altitude"
    NULL_ENGINE_TEMPERATURE = "null_engine_temperature"


class FaultInjection(BaseModel):
    """How many copies of one fault to append."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: FaultKind
    count: int = Field(default=1, ge=0)


def apply_faults(
    records: list[TelemetryEvent],
    faults: list[FaultInjection],
) -> list[TelemetryEvent]:
    """Append fault rows without altering the clean records.

    Duplicate injection copies an existing event_id. Every other fault
    uses a new event_id so the new row fails only the intended rule.
    The source rows are the original batch, not rows created by an
    earlier fault in the same call.
    """
    if any(fault.count > 0 for fault in faults) and not records:
        raise ValueError("cannot inject faults into an empty batch")

    output = list(records)
    for fault in faults:
        for index in range(fault.count):
            source = records[index % len(records)]
            output.append(_inject(source, fault.kind, index))
    return output


def _inject(source: TelemetryEvent, kind: FaultKind, index: int) -> TelemetryEvent:
    if kind is FaultKind.DUPLICATE_EVENT_ID:
        return source.model_copy(deep=True)

    updates: dict[str, object] = {"event_id": f"EVT-FAULT-{kind.value}-{index:04d}"}
    if kind is FaultKind.MISSING_FLIGHT_ID:
        updates["flight_id"] = None
    elif kind is FaultKind.NEGATIVE_FUEL:
        updates["fuel_remaining_kg"] = -25.0 * (index + 1)
    elif kind is FaultKind.INVALID_ALTITUDE:
        updates["altitude_ft"] = -10_000.0 if index % 2 == 0 else 120_000.0
    elif kind is FaultKind.NULL_ENGINE_TEMPERATURE:
        updates["engine_temp_c"] = None
    else:
        raise ValueError(f"unsupported fault: {kind}")
    return source.model_copy(update=updates)
