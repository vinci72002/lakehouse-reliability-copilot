"""Incidents opened from data-quality failures."""

import json
from datetime import datetime, timezone

import pytest

from dq.engine import run_quality_checks
from dq.incidents import create_incidents
from factories import make_event
from models.incident import IncidentStatus


DETECTED_AT = datetime(2026, 10, 19, 13, 30, tzinfo=timezone.utc)


def test_passing_rules_create_no_incidents() -> None:
    evaluations = run_quality_checks([make_event(), make_event(event_id="EVT-2")])
    assert create_incidents(evaluations, detected_at=DETECTED_AT) == []


def test_incident_contains_the_required_fields_and_limits_the_sample() -> None:
    events = [make_event(event_id=f"EVT-{index}", fuel_remaining_kg=-float(index + 1)) for index in range(8)]
    events.append(make_event(event_id="EVT-GOOD", fuel_remaining_kg=10))
    evaluations = run_quality_checks(events)
    ids = iter(["INC-1"])
    incidents = create_incidents(
        evaluations,
        detected_at=DETECTED_AT,
        sample_limit=5,
        id_factory=lambda: next(ids),
    )
    assert len(incidents) == 1
    incident = incidents[0]
    assert incident.incident_id == "INC-1"
    assert incident.detected_at == DETECTED_AT
    assert incident.dataset == "bronze.aircraft_telemetry"
    assert incident.rule_name == "fuel_non_negative"
    assert incident.severity.value == "critical"
    assert incident.failed_record_count == 8
    assert len(incident.sample_records) == 5
    assert incident.sample_records[0]["event_id"] == "EVT-0"
    assert incident.status is IncidentStatus.OPEN
    assert "fuel_non_negative" in incident.summary
    json.dumps(incident.sample_records)


def test_one_incident_per_failed_rule() -> None:
    events = [
        make_event(event_id="EVT-1", flight_id=None),
        make_event(event_id="EVT-2", engine_temp_c=None),
    ]
    incidents = create_incidents(run_quality_checks(events), detected_at=DETECTED_AT)
    assert [incident.rule_name for incident in incidents] == [
        "flight_id_not_null",
        "engine_temp_not_null",
    ]


def test_sample_limit_and_detected_at_are_validated() -> None:
    evaluations = run_quality_checks([make_event(fuel_remaining_kg=-1)])
    with pytest.raises(ValueError):
        create_incidents(evaluations, sample_limit=-1)
    with pytest.raises(ValueError):
        create_incidents(evaluations, detected_at=datetime(2026, 10, 19, 13, 30))
