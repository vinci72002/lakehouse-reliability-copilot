"""Phase 1 data-quality rules for aircraft telemetry.

Each rule exposes the rows that fail and a Spark SQL statement that
selects the same violations. Silver keeps a row only when every rule
passes, including uniqueness, so an exact duplicate does not silently
survive by dropping one copy.
"""

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from models.limits import ALTITUDE_MAX_FT, ALTITUDE_MIN_FT, FUEL_MIN_KG
from models.quality import Severity
from models.telemetry import TelemetryEvent


class QualityRule(Protocol):
    name: str
    severity: Severity
    description: str
    violation_sql: str

    def find_failures(self, records: Sequence[TelemetryEvent]) -> list[int]:
        """Return indexes of rows that violate this rule."""


@dataclass(frozen=True)
class UniqueEventIdRule:
    name: str = "event_id_unique"
    severity: Severity = Severity.HIGH
    description: str = "event_id must be unique within the dataset"
    violation_sql: str = """
SELECT event_id, COUNT(*) AS duplicate_count
FROM {dataset}
GROUP BY event_id
HAVING COUNT(*) > 1
""".strip()

    def find_failures(self, records: Sequence[TelemetryEvent]) -> list[int]:
        counts = Counter(record.event_id for record in records)
        return [
            index
            for index, record in enumerate(records)
            if counts[record.event_id] > 1
        ]


def flight_id_missing(event: TelemetryEvent) -> bool:
    return event.flight_id is None or event.flight_id.strip() == ""


def fuel_negative(event: TelemetryEvent) -> bool:
    return event.fuel_remaining_kg < FUEL_MIN_KG


def altitude_out_of_range(event: TelemetryEvent) -> bool:
    return event.altitude_ft < ALTITUDE_MIN_FT or event.altitude_ft > ALTITUDE_MAX_FT


def engine_temp_missing(event: TelemetryEvent) -> bool:
    return event.engine_temp_c is None


@dataclass(frozen=True)
class RowQualityRule:
    name: str
    severity: Severity
    description: str
    violation_sql: str
    fails: Callable[[TelemetryEvent], bool]

    def find_failures(self, records: Sequence[TelemetryEvent]) -> list[int]:
        return [index for index, record in enumerate(records) if self.fails(record)]


def default_rules() -> tuple[QualityRule, ...]:
    """Rules required for the Phase 1 telemetry contract."""
    altitude_sql = f"""
SELECT *
FROM {{dataset}}
WHERE altitude_ft < {ALTITUDE_MIN_FT:g} OR altitude_ft > {ALTITUDE_MAX_FT:g}
""".strip()
    return (
        UniqueEventIdRule(),
        RowQualityRule(
            name="flight_id_not_null",
            severity=Severity.HIGH,
            description="flight_id must be present",
            violation_sql="""
SELECT *
FROM {dataset}
WHERE flight_id IS NULL OR TRIM(flight_id) = ''
""".strip(),
            fails=flight_id_missing,
        ),
        RowQualityRule(
            name="fuel_non_negative",
            severity=Severity.CRITICAL,
            description="fuel_remaining_kg must be greater than or equal to 0",
            violation_sql=f"""
SELECT *
FROM {{dataset}}
WHERE fuel_remaining_kg < {FUEL_MIN_KG:g}
""".strip(),
            fails=fuel_negative,
        ),
        RowQualityRule(
            name="altitude_in_range",
            severity=Severity.MEDIUM,
            description=(
                f"altitude_ft must be between {ALTITUDE_MIN_FT:g} and {ALTITUDE_MAX_FT:g}"
            ),
            violation_sql=altitude_sql,
            fails=altitude_out_of_range,
        ),
        RowQualityRule(
            name="engine_temp_not_null",
            severity=Severity.MEDIUM,
            description="engine_temp_c must be present",
            violation_sql="""
SELECT *
FROM {dataset}
WHERE engine_temp_c IS NULL
""".strip(),
            fails=engine_temp_missing,
        ),
    )
