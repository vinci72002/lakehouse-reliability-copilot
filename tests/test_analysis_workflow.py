"""Incident analysis stays a recommendation until a person decides."""

from datetime import datetime, timezone

import pytest

from ai.analyst import MockAnalyst
from ai.workflow import analyze_incident
from api.app import sample_incidents
from audit.approval import ApprovalDecision, submit_human_decision
from audit.log import AuditAction, AuditLog, record_analysis
from factories import make_event
from models.incident import Incident, IncidentStatus
from models.quality import Severity
from rag.retriever import KnowledgeBase

DETECTED_AT = datetime(2026, 10, 19, 19, 0, tzinfo=timezone.utc)


def test_each_sample_incident_gets_a_structured_analysis() -> None:
    knowledge = KnowledgeBase()
    analyst = MockAnalyst()
    telemetry = [make_event(event_id="EVT-KEEP", fuel_remaining_kg=10)]
    before = list(telemetry)
    incidents = sample_incidents()
    assert len(incidents) == 5

    for incident in incidents:
        completed = analyze_incident(incident, knowledge_base=knowledge, analyst=analyst)
        assert completed.analysis.validation_sql
        assert incident.dataset in completed.analysis.validation_sql
        assert completed.analysis.evidence
        assert completed.analysis.verification_steps
        assert 0 <= completed.analysis.confidence_score <= 1
        assert incident.status is IncidentStatus.OPEN
        assert completed.passages

    assert telemetry == before


def test_analysis_and_approval_do_not_change_telemetry(tmp_path) -> None:
    incident = next(item for item in sample_incidents() if item.rule_name == "fuel_non_negative")
    telemetry = [make_event(fuel_remaining_kg=-4), make_event(event_id="EVT-OK")]
    before = list(telemetry)
    completed = analyze_incident(
        incident,
        knowledge_base=KnowledgeBase(),
        analyst=MockAnalyst(),
    )
    audit = AuditLog(tmp_path / "audit.jsonl")
    record_analysis(incident, completed.analysis, audit, recorded_at=DETECTED_AT)
    updated, entry = submit_human_decision(
        incident,
        actor="morgan",
        decision=ApprovalDecision.APPROVE,
        note="Quarantine stands.",
        audit_log=audit,
        decided_at=DETECTED_AT,
    )

    assert incident.status is IncidentStatus.OPEN
    assert updated.status is IncidentStatus.APPROVED
    assert telemetry == before
    assert not (tmp_path / "bronze").exists()
    actions = [item.action for item in audit.read_all()]
    assert actions == [AuditAction.ANALYSIS_RECORDED, AuditAction.HUMAN_APPROVED]
    assert entry.actor == "morgan"
    assert "No telemetry tables were modified." in audit.read_all()[0].detail


def test_unknown_rule_is_rejected() -> None:
    incident = Incident(
        incident_id="INC-UNKNOWN",
        detected_at=DETECTED_AT,
        dataset="bronze.aircraft_telemetry",
        rule_name="not_a_rule",
        severity=Severity.LOW,
        failed_record_count=1,
        sample_records=[{"event_id": "EVT-1"}],
        summary="Unknown rule",
    )
    with pytest.raises(Exception) as caught:
        analyze_incident(incident, knowledge_base=KnowledgeBase(), analyst=MockAnalyst())
    assert "not_a_rule" in str(caught.value)
