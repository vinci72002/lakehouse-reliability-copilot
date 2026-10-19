"""Canonical dataset names for the local medallion layout.

Names use catalog.table form so the same identifiers can be referenced
from Spark SQL on Databricks.
"""

import re

BRONZE_AIRCRAFT_TELEMETRY = "bronze.aircraft_telemetry"
SILVER_AIRCRAFT_TELEMETRY = "silver.aircraft_telemetry"
GOLD_FLIGHT_SUMMARY = "gold.flight_summary"
QUARANTINE_AIRCRAFT_TELEMETRY = "quarantine.aircraft_telemetry"

_DATASET_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


def validate_dataset_name(dataset: str) -> str:
    """Return dataset if it is a safe dotted SQL identifier."""
    if not _DATASET_NAME.fullmatch(dataset):
        raise ValueError(
            "dataset must be a dotted identifier such as bronze.aircraft_telemetry"
        )
    return dataset
