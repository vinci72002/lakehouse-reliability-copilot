"""Gold flight summary produced from silver telemetry."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FlightSummary(BaseModel):
    """One flight's curated metrics.

    Built only from silver rows, so quarantined measurements do not
    enter these aggregates.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    aircraft_id: str = Field(min_length=1)
    flight_id: str = Field(min_length=1)
    event_count: int = Field(ge=1)
    start_time: datetime
    end_time: datetime
    min_altitude_ft: float
    max_altitude_ft: float
    avg_ground_speed_kts: float
    min_fuel_remaining_kg: float
    max_engine_temp_c: float

    @field_validator("start_time", "end_time")
    @classmethod
    def _timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value
