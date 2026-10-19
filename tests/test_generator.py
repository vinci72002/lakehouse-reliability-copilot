"""Synthetic telemetry and fault injection."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from dq.engine import run_quality_checks
from ingestion.faults import FaultInjection, FaultKind, apply_faults
from ingestion.generator import generate_telemetry
from models.limits import ALTITUDE_MAX_FT, ALTITUDE_MIN_FT, FUEL_MIN_KG


def test_generator_is_deterministic_and_seed_changes_measurements() -> None:
    first = generate_telemetry(record_count=12, aircraft_count=3, seed=4)
    second = generate_telemetry(record_count=12, aircraft_count=3, seed=4)
    other = generate_telemetry(record_count=12, aircraft_count=3, seed=5)
    assert first == second
    assert [event.event_id for event in first] == [event.event_id for event in other]
    assert first != other


def test_clean_batch_passes_every_rule() -> None:
    for seed in (0, 1, 99):
        events = generate_telemetry(record_count=40, aircraft_count=4, seed=seed)
        failed = [item.rule_name for item in run_quality_checks(events) if not item.passed]
        assert failed == []
        assert all(ALTITUDE_MIN_FT <= event.altitude_ft <= ALTITUDE_MAX_FT for event in events)
        assert all(event.fuel_remaining_kg >= FUEL_MIN_KG for event in events)
        assert all(event.engine_temp_c is not None for event in events)
        assert all(event.flight_id for event in events)


def test_faults_are_appended_after_the_clean_prefix() -> None:
    clean = generate_telemetry(record_count=10, aircraft_count=2, seed=3)
    faulty = generate_telemetry(
        record_count=10,
        aircraft_count=2,
        seed=3,
        faults=[FaultInjection(kind=FaultKind.NEGATIVE_FUEL, count=2)],
    )
    assert faulty[:10] == clean
    assert len(faulty) == 12
    assert faulty[10].fuel_remaining_kg < 0
    assert faulty[11].fuel_remaining_kg < 0


@pytest.mark.parametrize(
    ("kind", "rule_name", "failed_count"),
    [
        (FaultKind.DUPLICATE_EVENT_ID, "event_id_unique", 2),
        (FaultKind.MISSING_FLIGHT_ID, "flight_id_not_null", 1),
        (FaultKind.NEGATIVE_FUEL, "fuel_non_negative", 1),
        (FaultKind.INVALID_ALTITUDE, "altitude_in_range", 1),
        (FaultKind.NULL_ENGINE_TEMPERATURE, "engine_temp_not_null", 1),
    ],
)
def test_each_fault_triggers_only_its_rule(kind: FaultKind, rule_name: str, failed_count: int) -> None:
    events = generate_telemetry(
        record_count=8,
        aircraft_count=2,
        seed=11,
        faults=[FaultInjection(kind=kind, count=1)],
    )
    failed = [item for item in run_quality_checks(events) if not item.passed]
    assert [item.rule_name for item in failed] == [rule_name]
    assert failed[0].failed_record_count == failed_count


def test_invalid_altitude_covers_both_sides_of_the_range() -> None:
    events = generate_telemetry(
        record_count=4,
        aircraft_count=1,
        seed=2,
        faults=[FaultInjection(kind=FaultKind.INVALID_ALTITUDE, count=2)],
    )
    injected = events[-2:]
    assert injected[0].altitude_ft == -10_000.0
    assert injected[1].altitude_ft == 120_000.0


def test_empty_batch_rejects_faults_and_naive_timestamps() -> None:
    with pytest.raises(ValueError):
        apply_faults([], [FaultInjection(kind=FaultKind.NEGATIVE_FUEL, count=1)])
    with pytest.raises(ValidationError):
        FaultInjection(kind=FaultKind.NEGATIVE_FUEL, count=-1)
    with pytest.raises(ValueError):
        generate_telemetry(
            record_count=1,
            start_time=datetime(2026, 10, 19, 12, 0),
        )
    assert generate_telemetry(record_count=0, seed=1) == []


def test_generator_rejects_negative_counts() -> None:
    with pytest.raises(ValueError):
        generate_telemetry(record_count=-1)
    with pytest.raises(ValueError):
        generate_telemetry(record_count=1, aircraft_count=0)
