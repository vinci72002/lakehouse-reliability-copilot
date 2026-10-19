"""Medallion quarantine and gold aggregation."""

from datetime import datetime, timedelta, timezone

from factories import make_event
from ingestion.faults import FaultInjection, FaultKind
from ingestion.generator import generate_telemetry
from pipelines.medallion import run_medallion

DETECTED_AT = datetime(2026, 10, 19, 14, 0, tzinfo=timezone.utc)


def test_strict_silver_drops_every_failing_row() -> None:
    base = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
    events = [
        make_event(event_id="A1", flight_id="FLT-A", event_time=base, ground_speed_kts=400, fuel_remaining_kg=100),
        make_event(
            event_id="A2",
            flight_id="FLT-A",
            event_time=base + timedelta(minutes=1),
            ground_speed_kts=500,
            fuel_remaining_kg=80,
            altitude_ft=36_000,
        ),
        make_event(event_id="A3", flight_id="FLT-A", fuel_remaining_kg=-5),
        make_event(event_id="B1", flight_id=None),
        make_event(event_id="C1", flight_id="FLT-C", ground_speed_kts=410),
        make_event(event_id="C1", flight_id="FLT-C", ground_speed_kts=410),
    ]
    result = run_medallion(events, detected_at=DETECTED_AT)

    assert [event.event_id for event in result.silver] == ["A1", "A2"]
    assert [event.event_id for event in result.quarantined] == ["A3", "B1", "C1", "C1"]
    assert len(result.gold) == 1
    summary = result.gold[0]
    assert summary.flight_id == "FLT-A"
    assert summary.event_count == 2
    assert summary.avg_ground_speed_kts == 450
    assert summary.min_fuel_remaining_kg == 80
    assert summary.max_altitude_ft == 36_000
    assert summary.start_time == base
    assert {incident.rule_name for incident in result.incidents} == {
        "event_id_unique",
        "flight_id_not_null",
        "fuel_non_negative",
    }


def test_generated_faults_stay_out_of_gold() -> None:
    faults = [FaultInjection(kind=kind, count=1) for kind in FaultKind]
    events = generate_telemetry(record_count=40, aircraft_count=4, seed=5, faults=faults)
    result = run_medallion(events, detected_at=DETECTED_AT)

    # One duplicate removes both copies. The other four faults add one bad row each.
    assert len(result.bronze) == 45
    assert len(result.quarantined) == 6
    assert len(result.silver) == 39
    assert sum(item.event_count for item in result.gold) == 39
    assert {incident.rule_name for incident in result.incidents} == {
        "event_id_unique",
        "flight_id_not_null",
        "fuel_non_negative",
        "altitude_in_range",
        "engine_temp_not_null",
    }
    assert all(event.fuel_remaining_kg >= 0 for event in result.silver)
    assert all(event.flight_id for event in result.silver)
    assert all(event.engine_temp_c is not None for event in result.silver)
