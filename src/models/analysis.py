"""Structured root-cause contract for a later analyst model.

Phase 1 defines the shape only. Nothing in this package calls a model
or applies a recommended action to lakehouse tables.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RootCauseAnalysis(BaseModel):
    """Evidence-backed analysis that a human must review before action."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    root_cause: str = Field(min_length=1)
    evidence: list[str] = Field(min_length=1)
    impact: str = Field(min_length=1)
    validation_sql: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)
    verification_steps: list[str] = Field(min_length=1)
    confidence_score: float = Field(ge=0.0, le=1.0)

    @field_validator("evidence", "verification_steps")
    @classmethod
    def _items_not_blank(cls, values: list[str]) -> list[str]:
        if any(not item.strip() for item in values):
            raise ValueError("items must be non-empty")
        return values
