"""Append-only audit log for incident creation and human decisions."""

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.analysis import RootCauseAnalysis
from models.incident import Incident


class AuditAction(str, Enum):
    INCIDENT_CREATED = "incident_created"
    ANALYSIS_RECORDED = "analysis_recorded"
    HUMAN_APPROVED = "human_approved"
    HUMAN_REJECTED = "human_rejected"


class AuditEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    audit_id: str = Field(min_length=1)
    recorded_at: datetime
    actor: str = Field(min_length=1)
    action: AuditAction
    incident_id: str = Field(min_length=1)
    dataset: str = Field(min_length=1)
    detail: str = Field(min_length=1)

    @field_validator("recorded_at")
    @classmethod
    def _timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("recorded_at must be timezone-aware")
        return value


class AuditLog:
    """JSONL log. Entries are appended and never rewritten."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def append(self, entry: AuditEntry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(entry.model_dump_json() + "\n")

    def read_all(self) -> list[AuditEntry]:
        if not self.path.exists():
            return []
        entries: list[AuditEntry] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entries.append(AuditEntry.model_validate_json(line))
        return entries


def new_audit_id() -> str:
    return f"AUD-{uuid4().hex[:12].upper()}"


def record_incident_creation(
    incidents: list[Incident],
    audit_log: AuditLog,
    *,
    actor: str,
    recorded_at: datetime | None = None,
) -> list[AuditEntry]:
    """Record that the quality engine opened incidents. This does not change telemetry."""
    actor_name = require_text(actor, "actor")
    timestamp = recorded_at or datetime.now(timezone.utc)
    entries: list[AuditEntry] = []
    for incident in incidents:
        entry = AuditEntry(
            audit_id=new_audit_id(),
            recorded_at=timestamp,
            actor=actor_name,
            action=AuditAction.INCIDENT_CREATED,
            incident_id=incident.incident_id,
            dataset=incident.dataset,
            detail=incident.summary,
        )
        audit_log.append(entry)
        entries.append(entry)
    return entries


def record_analysis(
    incident: Incident,
    analysis: RootCauseAnalysis,
    audit_log: AuditLog,
    *,
    actor: str = "ai-analyst",
    recorded_at: datetime | None = None,
) -> AuditEntry:
    """Record that an analysis was stored. This does not change telemetry."""
    actor_name = require_text(actor, "actor")
    timestamp = recorded_at or datetime.now(timezone.utc)
    entry = AuditEntry(
        audit_id=new_audit_id(),
        recorded_at=timestamp,
        actor=actor_name,
        action=AuditAction.ANALYSIS_RECORDED,
        incident_id=incident.incident_id,
        dataset=incident.dataset,
        detail=(
            f"Recorded root-cause analysis for {incident.rule_name} "
            f"with confidence {analysis.confidence_score:.2f}. "
            "No telemetry tables were modified."
        ),
    )
    audit_log.append(entry)
    return entry


def require_text(value: str, label: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{label} must be non-empty")
    return cleaned
