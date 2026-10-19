"""Data-quality rule behavior, including boundary values."""

from datetime import datetime, timedelta, timezone

from dq.engine import run_quality_checks
from dq.rules import default_rules
from factories import make_event
from models.datasets import BRONZE_AIRCRAFT_TELEMETRY
from models.limits import ALTITUDE_MAX_FT, ALTITUDE_MIN_FT


def _evaluation(events: list, rule_name: str):
    matches = [item for item in run_quality_checks(events) if item.rule_name == rule_name]
    assert len(matches) == 1
    return matches[0]


def test_rule_catalog_matches_the_phase1_contract() -> None:
    assert [rule.name for rule in default_rules()] == [
        "event_id_unique",
        "flight_id_not_null",
        "fuel_non_negative",
        "altitude_in_range",
        "engine_temp_not_null",
    ]


def test_empty_batch_passes_every_rule() -> None:
    evaluations = run_quality_checks([])
    assert evaluations
    assert all(item.passed for item in evaluations)


def test_uniqueness_reports_every_copy() -> None:
    later = datetime(2026, 10, 19, 12, 5, tzinfo=timezone.utc)
    events = [
        make_event(event_id="EVT-1", fuel_remaining_kg=10),
        make_event(event_id="EVT-1", fuel_remaining_kg=20, event_time=later),
        make_event(event_id="EVT-2"),
    ]
    result = _evaluation(events, "event_id_unique")
    assert result.failed_indices == [0, 1]
    assert result.failed_record_count == 2
    assert "bronze.aircraft_telemetry" in result.violation_sql
    assert _evaluation(events, "fuel_non_negative").passed


def test_blank_flight_id_fails_and_zero_fuel_passes() -> None:
    events = [
        make_event(event_id="EVT-1", flight_id="  "),
        make_event(event_id="EVT-2", fuel_remaining_kg=0),
        make_event(event_id="EVT-3", engine_temp_c=0),
    ]
    assert _evaluation(events, "flight_id_not_null").failed_indices == [0]
    assert _evaluation(events, "fuel_non_negative").passed
    assert _evaluation(events, "engine_temp_not_null").passed


def test_altitude_bounds_are_inclusive() -> None:
    events = [
        make_event(event_id="EVT-LOW-OK", altitude_ft=ALTITUDE_MIN_FT),
        make_event(event_id="EVT-HIGH-OK", altitude_ft=ALTITUDE_MAX_FT),
        make_event(event_id="EVT-LOW", altitude_ft=ALTITUDE_MIN_FT - 0.1),
        make_event(event_id="EVT-HIGH", altitude_ft=ALTITUDE_MAX_FT + 0.1),
    ]
    result = _evaluation(events, "altitude_in_range")
    assert result.failed_indices == [2, 3]
    assert str(ALTITUDE_MIN_FT) in result.description or "-1500" in result.description


def test_violation_sql_uses_the_requested_dataset() -> None:
    evaluation = run_quality_checks(
        [make_event(fuel_remaining_kg=-1)],
        dataset="silver.aircraft_telemetry",
    )
    fuel = next(item for item in evaluation if item.rule_name == "fuel_non_negative")
    assert "silver.aircraft_telemetry" in fuel.violation_sql
    assert fuel.dataset == "silver.aircraft_telemetry"
    assert fuel.severity.value == "critical"
    assert BRONZE_AIRCRAFT_TELEMETRY not in fuel.violation_sql


def test_duplicate_groups_do_not_hide_a_third_copy() -> None:
    base = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
    events = [
        make_event(event_id="EVT-1", event_time=base + timedelta(minutes=offset))
        for offset in range(3)
    ]
    assert _evaluation(events, "event_id_unique").failed_record_count == 3
