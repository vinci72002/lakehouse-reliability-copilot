"""Human approval writes an audit entry and leaves telemetry unchanged."""

from datetime import datetime, timezone

import pytest

from audit.approval import ApprovalDecision, submit_human_decision
from audit.log import AuditAction, AuditLog, record_incident_creation
from dq.engine import run_quality_checks
from dq.incidents import create_incidents
from factories import make_event
from models.incident import IncidentStatus

DETECTED_AT = datetime(2026, 10, 19, 16, 0, tzinfo=timezone.utc)


def _open_incident():
    evaluations = run_quality_checks([make_event(fuel_remaining_kg=-2)])
    return create_incidents(evaluations, detected_at=DETECTED_AT, id_factory=lambda: "INC-FUEL")[0]


def test_approval_updates_status_only_and_appends_audit(tmp_path) -> None:
    telemetry = [make_event(fuel_remaining_kg=-2), make_event(event_id="EVT-OK")]
    before = list(telemetry)
    incident = _open_incident()
    log = AuditLog(tmp_path / "audit.jsonl")
    created = record_incident_creation([incident], log, actor="dq-engine", recorded_at=DETECTED_AT)
    updated, entry = submit_human_decision(
        incident,
        actor="alex",
        decision=ApprovalDecision.APPROVE,
        note="Quarantine stands. Do not backfill fuel.",
        audit_log=log,
        decided_at=DETECTED_AT,
    )

    assert incident.status is IncidentStatus.OPEN
    assert updated.status is IncidentStatus.APPROVED
    assert telemetry == before
    assert created[0].action is AuditAction.INCIDENT_CREATED
    assert entry.actor == "alex"
    assert entry.action is AuditAction.HUMAN_APPROVED
    assert entry.detail == "Quarantine stands. Do not backfill fuel."
    reloaded = AuditLog(tmp_path / "audit.jsonl").read_all()
    assert [item.action for item in reloaded] == [
        AuditAction.INCIDENT_CREATED,
        AuditAction.HUMAN_APPROVED,
    ]


def test_reject_then_block_a_second_decision(tmp_path) -> None:
    incident = _open_incident()
    log = AuditLog(tmp_path / "audit.jsonl")
    rejected, entry = submit_human_decision(
        incident,
        actor="sam",
        decision=ApprovalDecision.REJECT,
        note="False positive from a test probe.",
        audit_log=log,
        decided_at=DETECTED_AT,
    )
    assert rejected.status is IncidentStatus.REJECTED
    assert entry.action is AuditAction.HUMAN_REJECTED
    with pytest.raises(ValueError):
        submit_human_decision(
            rejected,
            actor="sam",
            decision=ApprovalDecision.APPROVE,
            note="Trying again.",
            audit_log=log,
            decided_at=DETECTED_AT,
        )
    with pytest.raises(ValueError):
        submit_human_decision(
            incident,
            actor="  ",
            decision=ApprovalDecision.APPROVE,
            note="missing actor",
            audit_log=log,
            decided_at=DETECTED_AT,
        )
    with pytest.raises(ValueError):
        submit_human_decision(
            incident,
            actor="sam",
            decision=ApprovalDecision.APPROVE,
            note="  ",
            audit_log=log,
            decided_at=DETECTED_AT,
        )
