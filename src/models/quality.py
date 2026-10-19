"""Data-quality results shared by the rule engine and incident builder."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from models.telemetry import TelemetryEvent


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RuleEvaluation(BaseModel):
    """Outcome of one rule against one dataset snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_name: str
    severity: Severity
    description: str
    dataset: str
    passed: bool
    failed_record_count: int
    failed_indices: list[int]
    failed_records: list[TelemetryEvent]
    violation_sql: str

    @model_validator(mode="after")
    def _counts_match(self) -> "RuleEvaluation":
        if self.passed != (self.failed_record_count == 0):
            raise ValueError("passed does not match failed_record_count")
        if len(self.failed_records) != self.failed_record_count:
            raise ValueError("failed_record_count does not match failed_records")
        if len(self.failed_indices) != self.failed_record_count:
            raise ValueError("failed_indices do not match failed_record_count")
        if self.failed_record_count < 0:
            raise ValueError("failed_record_count cannot be negative")
        return self
