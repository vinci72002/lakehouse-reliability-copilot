"""PySpark silver and gold transforms.

The filters match dq.rules. On Databricks, persist with
``df.write.format("delta")``. Phase 1 compares these frames with the
Python medallion result and stores Delta tables through delta-rs.
"""

from collections.abc import Sequence
from datetime import timezone

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DoubleType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)
from pyspark.sql.window import Window

from dq.rules import default_rules
from models.limits import ALTITUDE_MAX_FT, ALTITUDE_MIN_FT, FUEL_MIN_KG
from models.telemetry import TelemetryEvent

TELEMETRY_SPARK_SCHEMA = StructType(
    [
        StructField("event_id", StringType(), nullable=False),
        StructField("aircraft_id", StringType(), nullable=False),
        StructField("flight_id", StringType(), nullable=True),
        StructField("event_time", TimestampType(), nullable=False),
        StructField("latitude", DoubleType(), nullable=False),
        StructField("longitude", DoubleType(), nullable=False),
        StructField("altitude_ft", DoubleType(), nullable=False),
        StructField("ground_speed_kts", DoubleType(), nullable=False),
        StructField("vertical_speed_fpm", DoubleType(), nullable=False),
        StructField("engine_temp_c", DoubleType(), nullable=True),
        StructField("fuel_remaining_kg", DoubleType(), nullable=False),
    ]
)


def bronze_frame(spark: SparkSession, events: Sequence[TelemetryEvent]) -> DataFrame:
    rows = [_spark_row(event) for event in events]
    return spark.createDataFrame(rows, schema=TELEMETRY_SPARK_SCHEMA)


def silver_frame(bronze: DataFrame) -> DataFrame:
    """Keep rows that pass the same rules as the Python engine."""
    duplicate_count = F.count(F.lit(1)).over(Window.partitionBy("event_id"))
    flight_ok = F.col("flight_id").isNotNull() & (F.length(F.trim(F.col("flight_id"))) > 0)
    fuel_ok = F.col("fuel_remaining_kg") >= F.lit(FUEL_MIN_KG)
    altitude_ok = (F.col("altitude_ft") >= F.lit(ALTITUDE_MIN_FT)) & (
        F.col("altitude_ft") <= F.lit(ALTITUDE_MAX_FT)
    )
    engine_ok = F.col("engine_temp_c").isNotNull()
    return (
        bronze.withColumn("_dup_count", duplicate_count)
        .filter((F.col("_dup_count") == 1) & flight_ok & fuel_ok & altitude_ok & engine_ok)
        .drop("_dup_count")
    )


def gold_frame(silver: DataFrame) -> DataFrame:
    return silver.groupBy("aircraft_id", "flight_id").agg(
        F.count(F.lit(1)).alias("event_count"),
        F.min("event_time").alias("start_time"),
        F.max("event_time").alias("end_time"),
        F.min("altitude_ft").alias("min_altitude_ft"),
        F.max("altitude_ft").alias("max_altitude_ft"),
        F.avg("ground_speed_kts").alias("avg_ground_speed_kts"),
        F.min("fuel_remaining_kg").alias("min_fuel_remaining_kg"),
        F.max("engine_temp_c").alias("max_engine_temp_c"),
    )


def rule_names() -> list[str]:
    """Named here so a Databricks job can log the same rule set."""
    return [rule.name for rule in default_rules()]


def _spark_row(event: TelemetryEvent) -> tuple[object, ...]:
    event_time = event.event_time.astimezone(timezone.utc).replace(tzinfo=None)
    return (
        event.event_id,
        event.aircraft_id,
        event.flight_id,
        event_time,
        float(event.latitude),
        float(event.longitude),
        float(event.altitude_ft),
        float(event.ground_speed_kts),
        float(event.vertical_speed_fpm),
        None if event.engine_temp_c is None else float(event.engine_temp_c),
        float(event.fuel_remaining_kg),
    )
