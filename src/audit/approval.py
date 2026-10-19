"""Human approval for an incident.

Approving or rejecting updates the incident status and writes an audit
entry. It does not update bronze, silver, gold, or quarantine tables.
"""

from datetime import datetime, timezone
from enum import Enum

from audit.log import AuditAction, AuditEntry, AuditLog, new_audit_id, require_text
from models.incident import Incident, IncidentStatus


class ApprovalDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


def submit_human_decision(
    incident: Incident,
    *,
    actor: str,
    decision: ApprovalDecision,
    note: str,
    audit_log: AuditLog,
    decided_at: datetime | None = None,
) -> tuple[Incident, AuditEntry]:
    """Record a person's decision and return the updated incident."""
    if incident.status is not IncidentStatus.OPEN:
        raise ValueError(f"incident {incident.incident_id} is already {incident.status.value}")

    actor_name = require_text(actor, "actor")
    reason = require_text(note, "note")
    timestamp = decided_at or datetime.now(timezone.utc)
    if decision is ApprovalDecision.APPROVE:
        status = IncidentStatus.APPROVED
        action = AuditAction.HUMAN_APPROVED
    elif decision is ApprovalDecision.REJECT:
        status = IncidentStatus.REJECTED
        action = AuditAction.HUMAN_REJECTED
    else:
        raise ValueError(f"unsupported decision: {decision}")

    updated = incident.model_copy(update={"status": status})
    entry = AuditEntry(
        audit_id=new_audit_id(),
        recorded_at=timestamp,
        actor=actor_name,
        action=action,
        incident_id=incident.incident_id,
        dataset=incident.dataset,
        detail=reason,
    )
    audit_log.append(entry)
    return updated, entry
