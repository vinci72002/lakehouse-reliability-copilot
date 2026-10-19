"""Local Delta snapshots for a medallion batch."""

from datetime import datetime, timezone

from factories import make_event
from models.gold import FlightSummary
from pipelines.delta_store import publish_medallion, read_flight_summaries, read_telemetry
from pipelines.medallion import MedallionResult, run_medallion

DETECTED_AT = datetime(2026, 10, 19, 15, 0, tzinfo=timezone.utc)


def _event_key(event: object) -> tuple:
    row = event
    return (row.event_id, row.event_time, row.fuel_remaining_kg, row.altitude_ft, row.engine_temp_c)  # type: ignore[attr-defined]


def test_publish_round_trips_bronze_silver_and_gold(tmp_path) -> None:
    events = [
        make_event(event_id="EVT-OK", aircraft_id="AC-1000", flight_id="FLT-OK", fuel_remaining_kg=50),
        make_event(event_id="EVT-1", aircraft_id="AC-1000", fuel_remaining_kg=100),
        make_event(event_id="EVT-1", aircraft_id="AC-1000", fuel_remaining_kg=100),
        make_event(event_id="EVT-2", aircraft_id="AC-1001", flight_id="FLT-2", fuel_remaining_kg=-4),
        make_event(event_id="EVT-3", aircraft_id="AC-1001", flight_id="FLT-2", engine_temp_c=None),
    ]
    result = run_medallion(events, detected_at=DETECTED_AT)
    tables = publish_medallion(result, tmp_path)

    bronze = read_telemetry(tables.bronze)
    silver = read_telemetry(tables.silver)
    quarantine = read_telemetry(tables.quarantine)
    gold = read_flight_summaries(tables.gold)

    assert sorted(bronze, key=_event_key) == sorted(result.bronze, key=_event_key)
    assert sorted(silver, key=_event_key) == sorted(result.silver, key=_event_key)
    assert sorted(quarantine, key=_event_key) == sorted(result.quarantined, key=_event_key)
    assert gold == result.gold
    assert all(item.min_fuel_remaining_kg >= 0 for item in gold)
    assert not any(event.fuel_remaining_kg < 0 for event in silver)


def test_publish_replaces_the_previous_snapshot(tmp_path) -> None:
    first = run_medallion([make_event(event_id="EVT-1"), make_event(event_id="EVT-2")], detected_at=DETECTED_AT)
    second = run_medallion([make_event(event_id="EVT-9", aircraft_id="AC-9", flight_id="FLT-9")], detected_at=DETECTED_AT)
    tables = publish_medallion(first, tmp_path)
    publish_medallion(second, tmp_path)
    assert [event.event_id for event in read_telemetry(tables.bronze)] == ["EVT-9"]


def test_empty_batch_still_creates_delta_tables(tmp_path) -> None:
    result = MedallionResult(
        bronze=[],
        silver=[],
        gold=[],
        quarantined=[],
        evaluations=[],
        incidents=[],
    )
    tables = publish_medallion(result, tmp_path)
    assert read_telemetry(tables.bronze) == []
    assert read_flight_summaries(tables.gold) == []


def test_flight_summary_schema_round_trip(tmp_path) -> None:
    start = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
    end = datetime(2026, 10, 19, 13, 0, tzinfo=timezone.utc)
    summary = FlightSummary(
        aircraft_id="AC-1000",
        flight_id="FLT-1",
        event_count=2,
        start_time=start,
        end_time=end,
        min_altitude_ft=1_000,
        max_altitude_ft=35_000,
        avg_ground_speed_kts=420.5,
        min_fuel_remaining_kg=800,
        max_engine_temp_c=790.25,
    )
    result = MedallionResult(
        bronze=[],
        silver=[],
        gold=[summary],
        quarantined=[],
        evaluations=[],
        incidents=[],
    )
    tables = publish_medallion(result, tmp_path)
    assert read_flight_summaries(tables.gold) == [summary]
