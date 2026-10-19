"""Local batch used by the Phase 1 demo script."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from audit.log import AuditLog, record_incident_creation
from ingestion.faults import FaultInjection, FaultKind
from ingestion.generator import generate_telemetry
from pipelines.delta_store import PublishedTables, publish_medallion
from pipelines.medallion import MedallionResult, run_medallion


@dataclass(frozen=True)
class DemoRun:
    result: MedallionResult
    tables: PublishedTables
    audit_log: Path


def run_demo(lake_root: Path) -> DemoRun:
    """Generate a faulty fleet sample, publish Delta tables, and open incidents."""
    faults = [
        FaultInjection(kind=FaultKind.DUPLICATE_EVENT_ID, count=2),
        FaultInjection(kind=FaultKind.MISSING_FLIGHT_ID, count=2),
        FaultInjection(kind=FaultKind.NEGATIVE_FUEL, count=2),
        FaultInjection(kind=FaultKind.INVALID_ALTITUDE, count=2),
        FaultInjection(kind=FaultKind.NULL_ENGINE_TEMPERATURE, count=2),
    ]
    events = generate_telemetry(
        record_count=80,
        aircraft_count=4,
        seed=19,
        faults=faults,
    )
    detected_at = datetime(2026, 10, 19, 13, 0, tzinfo=timezone.utc)
    result = run_medallion(events, detected_at=detected_at)
    tables = publish_medallion(result, lake_root)
    audit_path = lake_root / "audit" / "audit_log.jsonl"
    record_incident_creation(
        result.incidents,
        AuditLog(audit_path),
        actor="dq-engine",
        recorded_at=detected_at,
    )
    return DemoRun(result=result, tables=tables, audit_log=audit_path)
