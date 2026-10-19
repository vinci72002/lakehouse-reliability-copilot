"""Bronze telemetry contract for aircraft position and engine readings."""

import math
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.limits import (
    LATITUDE_MAX_DEG,
    LATITUDE_MIN_DEG,
    LONGITUDE_MAX_DEG,
    LONGITUDE_MIN_DEG,
)


class TelemetryEvent(BaseModel):
    """One raw telemetry point as it lands in bronze.

    Optional fields and impossible measurements are accepted here.
    Data-quality rules decide what may enter silver. Bronze keeps the
    original record so incidents can show the failing sample.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(min_length=1)
    aircraft_id: str = Field(min_length=1)
    flight_id: str | None = None
    event_time: datetime
    latitude: float = Field(ge=LATITUDE_MIN_DEG, le=LATITUDE_MAX_DEG)
    longitude: float = Field(ge=LONGITUDE_MIN_DEG, le=LONGITUDE_MAX_DEG)
    altitude_ft: float
    ground_speed_kts: float
    vertical_speed_fpm: float
    engine_temp_c: float | None = None
    fuel_remaining_kg: float

    @field_validator("event_time")
    @classmethod
    def _timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("event_time must be timezone-aware")
        return value

    @field_validator(
        "latitude",
        "longitude",
        "altitude_ft",
        "ground_speed_kts",
        "vertical_speed_fpm",
        "fuel_remaining_kg",
    )
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("value must be finite")
        return value

    @field_validator("engine_temp_c")
    @classmethod
    def _finite_temperature(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("engine_temp_c must be finite")
        return value
