"""Reliability incidents opened from failed data-quality rules."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.quality import Severity


class IncidentStatus(str, Enum):
    OPEN = "open"
    APPROVED = "approved"
    REJECTED = "rejected"


class Incident(BaseModel):
    """One incident per failed rule on a dataset.

    Status changes only through a human decision. Creating or approving
    an incident does not rewrite telemetry tables.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    incident_id: str = Field(min_length=1)
    detected_at: datetime
    dataset: str = Field(min_length=1)
    rule_name: str = Field(min_length=1)
    severity: Severity
    failed_record_count: int = Field(ge=1)
    sample_records: list[dict[str, Any]]
    status: IncidentStatus = IncidentStatus.OPEN
    summary: str = Field(min_length=1)

    @field_validator("detected_at")
    @classmethod
    def _timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("detected_at must be timezone-aware")
        return value
