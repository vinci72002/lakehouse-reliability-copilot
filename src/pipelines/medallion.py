"""Bronze, silver, and gold for one local telemetry batch.

Silver is the subset of bronze rows that pass every data-quality rule.
A duplicate event_id fails uniqueness, so every copy stays out of silver.
Gold aggregates silver only. Quarantine is deterministic pipeline logic,
not an AI write to production.
"""

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from dq.engine import run_quality_checks
from dq.incidents import create_incidents
from models.datasets import BRONZE_AIRCRAFT_TELEMETRY
from models.gold import FlightSummary
from models.incident import Incident
from models.quality import RuleEvaluation
from models.telemetry import TelemetryEvent


class MedallionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    bronze: list[TelemetryEvent]
    silver: list[TelemetryEvent]
    gold: list[FlightSummary]
    quarantined: list[TelemetryEvent]
    evaluations: list[RuleEvaluation]
    incidents: list[Incident]


def run_medallion(
    events: Sequence[TelemetryEvent],
    *,
    dataset: str = BRONZE_AIRCRAFT_TELEMETRY,
    detected_at: datetime | None = None,
    sample_limit: int = 5,
) -> MedallionResult:
    """Check bronze, quarantine failures, and aggregate the passing rows."""
    bronze = list(events)
    evaluations = run_quality_checks(bronze, dataset=dataset)
    failing = {
        index
        for evaluation in evaluations
        for index in evaluation.failed_indices
    }
    silver = [
        record
        for index, record in enumerate(bronze)
        if index not in failing
    ]
    silver.sort(key=lambda record: (record.event_time, record.aircraft_id, record.event_id))
    quarantined = [record for index, record in enumerate(bronze) if index in failing]
    return MedallionResult(
        bronze=bronze,
        silver=silver,
        gold=_build_gold(silver),
        quarantined=quarantined,
        evaluations=evaluations,
        incidents=create_incidents(
            evaluations,
            detected_at=detected_at,
            sample_limit=sample_limit,
        ),
    )


def _build_gold(silver: Sequence[TelemetryEvent]) -> list[FlightSummary]:
    grouped: dict[tuple[str, str], list[TelemetryEvent]] = defaultdict(list)
    for record in silver:
        if record.flight_id is None:
            raise ValueError("silver row is missing flight_id")
        grouped[(record.aircraft_id, record.flight_id)].append(record)

    summaries: list[FlightSummary] = []
    for (aircraft_id, flight_id), rows in sorted(grouped.items()):
        temperatures = [row.engine_temp_c for row in rows]
        if any(temperature is None for temperature in temperatures):
            raise ValueError("silver row is missing engine_temp_c")
        summaries.append(
            FlightSummary(
                aircraft_id=aircraft_id,
                flight_id=flight_id,
                event_count=len(rows),
                start_time=min(row.event_time for row in rows),
                end_time=max(row.event_time for row in rows),
                min_altitude_ft=min(row.altitude_ft for row in rows),
                max_altitude_ft=max(row.altitude_ft for row in rows),
                avg_ground_speed_kts=sum(row.ground_speed_kts for row in rows) / len(rows),
                min_fuel_remaining_kg=min(row.fuel_remaining_kg for row in rows),
                max_engine_temp_c=max(temperature for temperature in temperatures if temperature is not None),
            )
        )
    return summaries
