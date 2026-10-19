"""Write a medallion batch as local Delta tables.

The on-disk format is Delta Lake via delta-rs, which Databricks can read.
Phase 1 replaces the local snapshot for the batch. It does not merge into
a production table, and it is not invoked by an AI recommendation.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
from deltalake import DeltaTable, write_deltalake

from models.gold import FlightSummary
from models.telemetry import TelemetryEvent
from pipelines.medallion import MedallionResult

TELEMETRY_ARROW_SCHEMA = pa.schema(
    [
        pa.field("event_id", pa.string(), nullable=False),
        pa.field("aircraft_id", pa.string(), nullable=False),
        pa.field("flight_id", pa.string(), nullable=True),
        pa.field("event_time", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("latitude", pa.float64(), nullable=False),
        pa.field("longitude", pa.float64(), nullable=False),
        pa.field("altitude_ft", pa.float64(), nullable=False),
        pa.field("ground_speed_kts", pa.float64(), nullable=False),
        pa.field("vertical_speed_fpm", pa.float64(), nullable=False),
        pa.field("engine_temp_c", pa.float64(), nullable=True),
        pa.field("fuel_remaining_kg", pa.float64(), nullable=False),
    ]
)

FLIGHT_SUMMARY_ARROW_SCHEMA = pa.schema(
    [
        pa.field("aircraft_id", pa.string(), nullable=False),
        pa.field("flight_id", pa.string(), nullable=False),
        pa.field("event_count", pa.int64(), nullable=False),
        pa.field("start_time", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("end_time", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("min_altitude_ft", pa.float64(), nullable=False),
        pa.field("max_altitude_ft", pa.float64(), nullable=False),
        pa.field("avg_ground_speed_kts", pa.float64(), nullable=False),
        pa.field("min_fuel_remaining_kg", pa.float64(), nullable=False),
        pa.field("max_engine_temp_c", pa.float64(), nullable=False),
    ]
)


@dataclass(frozen=True)
class PublishedTables:
    bronze: Path
    silver: Path
    gold: Path
    quarantine: Path


def publish_medallion(result: MedallionResult, lake_root: Path) -> PublishedTables:
    """Replace local Delta snapshots for bronze, silver, gold, and quarantine."""
    tables = PublishedTables(
        bronze=lake_root / "bronze" / "aircraft_telemetry",
        silver=lake_root / "silver" / "aircraft_telemetry",
        gold=lake_root / "gold" / "flight_summary",
        quarantine=lake_root / "quarantine" / "aircraft_telemetry",
    )
    _write(events_table(result.bronze), tables.bronze, partition_by=["aircraft_id"])
    _write(events_table(result.silver), tables.silver, partition_by=["aircraft_id"])
    _write(events_table(result.quarantined), tables.quarantine, partition_by=["aircraft_id"])
    _write(flight_table(result.gold), tables.gold, partition_by=None)
    return tables


def read_telemetry(path: Path) -> list[TelemetryEvent]:
    return [TelemetryEvent.model_validate(row) for row in _read_rows(path)]


def read_flight_summaries(path: Path) -> list[FlightSummary]:
    return [FlightSummary.model_validate(row) for row in _read_rows(path)]


def events_table(events: list[TelemetryEvent]) -> pa.Table:
    payload = [event.model_dump() for event in events]
    return pa.Table.from_pylist(payload, schema=TELEMETRY_ARROW_SCHEMA)


def flight_table(summaries: list[FlightSummary]) -> pa.Table:
    payload = [summary.model_dump() for summary in summaries]
    return pa.Table.from_pylist(payload, schema=FLIGHT_SUMMARY_ARROW_SCHEMA)


def _write(table: pa.Table, path: Path, *, partition_by: list[str] | None) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    options: dict[str, object] = {}
    if partition_by:
        options["partition_by"] = partition_by
    write_deltalake(str(path), table, mode="overwrite", **options)


def _read_rows(path: Path) -> list[dict[str, object]]:
    return DeltaTable(str(path)).to_pyarrow_table().to_pylist()
