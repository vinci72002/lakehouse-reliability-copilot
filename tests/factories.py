"""Shared telemetry rows for tests."""

from datetime import datetime, timezone

from models.telemetry import TelemetryEvent


def make_event(**overrides: object) -> TelemetryEvent:
    payload: dict[str, object] = {
        "event_id": "EVT-1",
        "aircraft_id": "AC-1000",
        "flight_id": "FLT-1",
        "event_time": datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc),
        "latitude": 34.0,
        "longitude": -118.0,
        "altitude_ft": 35_000.0,
        "ground_speed_kts": 450.0,
        "vertical_speed_fpm": 0.0,
        "engine_temp_c": 780.0,
        "fuel_remaining_kg": 5_000.0,
    }
    payload.update(overrides)
    return TelemetryEvent(**payload)  # type: ignore[arg-type]
