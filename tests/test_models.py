"""Contract tests for telemetry, incidents, and the analysis schema."""

import math
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from factories import make_event
from models.analysis import RootCauseAnalysis
from models.datasets import validate_dataset_name
from models.incident import Incident, IncidentStatus
from models.quality import Severity


def test_telemetry_accepts_bronze_faults() -> None:
    event = make_event(flight_id=None, engine_temp_c=None, fuel_remaining_kg=-10, altitude_ft=-50_000)
    assert event.flight_id is None
    assert event.engine_temp_c is None
    assert event.fuel_remaining_kg == -10


def test_telemetry_rejects_impossible_coordinates_and_non_finite_values() -> None:
    with pytest.raises(ValidationError):
        make_event(latitude=91)
    with pytest.raises(ValidationError):
        make_event(longitude=181)
    with pytest.raises(ValidationError):
        make_event(event_id="")
    with pytest.raises(ValidationError):
        make_event(fuel_remaining_kg=math.nan)
    with pytest.raises(ValidationError):
        make_event(event_time=datetime(2026, 10, 19, 12, 0))


def test_dataset_name_must_be_a_dotted_identifier() -> None:
    assert validate_dataset_name("bronze.aircraft_telemetry") == "bronze.aircraft_telemetry"
    with pytest.raises(ValueError):
        validate_dataset_name("bronze; drop table x")


def test_root_cause_contract_bounds_confidence() -> None:
    analysis = RootCauseAnalysis(
        root_cause="Fuel sensor stuck below zero",
        evidence=["12 bronze rows have fuel_remaining_kg < 0"],
        impact="Gold fuel burn for those flights is untrusted",
        validation_sql="SELECT * FROM bronze.aircraft_telemetry WHERE fuel_remaining_kg < 0",
        recommended_action="Quarantine the sensor stream and ask maintenance to inspect it",
        verification_steps=["Re-run fuel_non_negative after the next ingest"],
        confidence_score=0.74,
    )
    assert analysis.confidence_score == 0.74
    with pytest.raises(ValidationError):
        RootCauseAnalysis(
            root_cause="x",
            evidence=["a reading"],
            impact="x",
            validation_sql="SELECT 1",
            recommended_action="x",
            verification_steps=["check"],
            confidence_score=1.2,
        )
    with pytest.raises(ValidationError):
        RootCauseAnalysis(
            root_cause="x",
            evidence=[" "],
            impact="x",
            validation_sql="SELECT 1",
            recommended_action="x",
            verification_steps=["check"],
            confidence_score=0.2,
        )


def test_incident_requires_timezone_and_starts_open() -> None:
    incident = Incident(
        incident_id="INC-1",
        detected_at=datetime(2026, 10, 19, 13, 0, tzinfo=timezone.utc),
        dataset="bronze.aircraft_telemetry",
        rule_name="fuel_non_negative",
        severity=Severity.CRITICAL,
        failed_record_count=1,
        sample_records=[{"event_id": "EVT-1"}],
        summary="1 record failed",
    )
    assert incident.status is IncidentStatus.OPEN
    with pytest.raises(ValidationError):
        Incident(
            incident_id="INC-1",
            detected_at=datetime(2026, 10, 19, 13, 0),
            dataset="bronze.aircraft_telemetry",
            rule_name="fuel_non_negative",
            severity=Severity.CRITICAL,
            failed_record_count=1,
            sample_records=[{"event_id": "EVT-1"}],
            summary="1 record failed",
        )
