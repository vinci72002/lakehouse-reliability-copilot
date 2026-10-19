"""PySpark silver and gold match the Python medallion rules."""

from datetime import datetime, timezone

import pytest

from ingestion.faults import FaultInjection, FaultKind
from ingestion.generator import generate_telemetry
from pipelines.medallion import run_medallion
from pipelines.session import build_local_spark
from pipelines.spark_medallion import bronze_frame, gold_frame, rule_names, silver_frame

DETECTED_AT = datetime(2026, 10, 19, 17, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def spark(tmp_path_factory):
    session = build_local_spark(tmp_path_factory.mktemp("spark-warehouse"))
    yield session
    session.stop()


def test_spark_filters_match_python_medallion(spark) -> None:
    faults = [FaultInjection(kind=kind, count=2) for kind in FaultKind]
    events = generate_telemetry(record_count=30, aircraft_count=3, seed=8, faults=faults)
    python_result = run_medallion(events, detected_at=DETECTED_AT)

    bronze = bronze_frame(spark, events)
    silver = silver_frame(bronze)
    gold = gold_frame(silver)

    silver_ids = sorted(row.event_id for row in silver.select("event_id").collect())
    assert silver_ids == sorted(event.event_id for event in python_result.silver)

    spark_gold = {
        (row.aircraft_id, row.flight_id): (
            row.event_count,
            row.min_fuel_remaining_kg,
            row.max_altitude_ft,
            row.avg_ground_speed_kts,
        )
        for row in gold.collect()
    }
    python_gold = {
        (item.aircraft_id, item.flight_id): (
            item.event_count,
            item.min_fuel_remaining_kg,
            item.max_altitude_ft,
            item.avg_ground_speed_kts,
        )
        for item in python_result.gold
    }
    assert spark_gold.keys() == python_gold.keys()
    for key, actual in spark_gold.items():
        expected = python_gold[key]
        assert actual[0] == expected[0]
        assert actual[1] == pytest.approx(expected[1])
        assert actual[2] == pytest.approx(expected[2])
        assert actual[3] == pytest.approx(expected[3])
    assert rule_names() == [
        "event_id_unique",
        "flight_id_not_null",
        "fuel_non_negative",
        "altitude_in_range",
        "engine_temp_not_null",
    ]


def test_spark_empty_batch(spark) -> None:
    bronze = bronze_frame(spark, [])
    assert silver_frame(bronze).count() == 0
    assert gold_frame(silver_frame(bronze)).count() == 0
