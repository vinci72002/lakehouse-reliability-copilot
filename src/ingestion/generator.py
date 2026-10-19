"""Deterministic aircraft telemetry for local lakehouse runs."""

import random
from datetime import datetime, timedelta, timezone

from ingestion.faults import FaultInjection, apply_faults
from models.limits import ALTITUDE_MAX_FT, ALTITUDE_MIN_FT
from models.telemetry import TelemetryEvent

_CRUISE_ALTITUDE_FT = 35_000.0
_FUEL_START_KG = 12_000.0
_FUEL_BURN_KG = 4_500.0
_EVENT_INTERVAL = timedelta(seconds=60)


def generate_telemetry(
    *,
    record_count: int,
    aircraft_count: int = 4,
    start_time: datetime | None = None,
    seed: int = 7,
    faults: list[FaultInjection] | None = None,
) -> list[TelemetryEvent]:
    """Build a clean fleet sample, then append any requested faults.

    The same seed and inputs always return the same events. Noise stays
    inside the data-quality bounds, so a batch with no faults passes
    every Phase 1 rule.
    """
    if record_count < 0:
        raise ValueError("record_count must be >= 0")
    if aircraft_count < 1:
        raise ValueError("aircraft_count must be >= 1")

    origin = start_time or datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
    if origin.tzinfo is None or origin.utcoffset() is None:
        raise ValueError("start_time must be timezone-aware")

    rng = random.Random(seed)
    events: list[TelemetryEvent] = []
    for slot, count in enumerate(_split(record_count, aircraft_count)):
        aircraft_id = f"AC-{1000 + slot}"
        flight_id = f"FLT-{origin:%Y%m%d}-{aircraft_id}"
        for index in range(count):
            events.append(
                _event(
                    slot=slot,
                    index=index,
                    total=count,
                    aircraft_id=aircraft_id,
                    flight_id=flight_id,
                    event_time=origin + _EVENT_INTERVAL * index,
                    rng=rng,
                )
            )
    return apply_faults(events, list(faults or []))


def _split(total: int, buckets: int) -> list[int]:
    base, extra = divmod(total, buckets)
    return [base + (1 if slot < extra else 0) for slot in range(buckets)]


def _event(
    *,
    slot: int,
    index: int,
    total: int,
    aircraft_id: str,
    flight_id: str,
    event_time: datetime,
    rng: random.Random,
) -> TelemetryEvent:
    phase = 0.5 if total <= 1 else index / (total - 1)
    if phase < 0.15:
        climb = phase / 0.15
        altitude = 500.0 + climb * (_CRUISE_ALTITUDE_FT - 500.0)
        vertical_speed = 1_600.0
        ground_speed = 160.0 + climb * 200.0
    elif phase > 0.85:
        descent = (phase - 0.85) / 0.15
        altitude = _CRUISE_ALTITUDE_FT - descent * (_CRUISE_ALTITUDE_FT - 800.0)
        vertical_speed = -1_400.0
        ground_speed = 420.0 - descent * 180.0
    else:
        altitude = _CRUISE_ALTITUDE_FT + (slot % 10) * 200.0
        vertical_speed = 0.0
        ground_speed = 455.0

    altitude += rng.uniform(-25.0, 25.0)
    ground_speed = max(0.0, ground_speed + rng.uniform(-8.0, 8.0))
    engine_temp = 640.0 + rng.uniform(-2.0, 2.0)
    latitude = -35.0 + (slot % 25) * 2.0 + phase * 1.5 + rng.uniform(-0.02, 0.02)
    longitude = -120.0 + (slot % 25) * 2.0 + phase * 2.0 + rng.uniform(-0.02, 0.02)

    altitude = min(max(altitude, ALTITUDE_MIN_FT + 100.0), ALTITUDE_MAX_FT - 100.0)
    fuel = max(150.0, _FUEL_START_KG - phase * _FUEL_BURN_KG - (slot % 10) * 30.0)

    return TelemetryEvent(
        event_id=f"EVT-{slot:03d}-{index:06d}",
        aircraft_id=aircraft_id,
        flight_id=flight_id,
        event_time=event_time,
        latitude=latitude,
        longitude=longitude,
        altitude_ft=altitude,
        ground_speed_kts=ground_speed,
        vertical_speed_fpm=vertical_speed,
        engine_temp_c=engine_temp,
        fuel_remaining_kg=fuel,
    )
