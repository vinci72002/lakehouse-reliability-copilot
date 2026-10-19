"""Open one incident for each failed data-quality rule."""

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from uuid import uuid4

from models.incident import Incident
from models.quality import RuleEvaluation

DEFAULT_SAMPLE_LIMIT = 5


def new_incident_id() -> str:
    return f"INC-{uuid4().hex[:12].upper()}"


def create_incidents(
    evaluations: Sequence[RuleEvaluation],
    *,
    detected_at: datetime | None = None,
    sample_limit: int = DEFAULT_SAMPLE_LIMIT,
    id_factory: Callable[[], str] | None = None,
) -> list[Incident]:
    """Create open incidents for failing rules.

    Passing rules are skipped. The sample is a JSON-ready slice of the
    failing rows; failed_record_count still reports the full count.
    """
    if sample_limit < 0:
        raise ValueError("sample_limit must be >= 0")
    timestamp = detected_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("detected_at must be timezone-aware")

    factory = id_factory or new_incident_id
    incidents: list[Incident] = []
    for evaluation in evaluations:
        if evaluation.passed:
            continue
        sample = [
            record.model_dump(mode="json")
            for record in evaluation.failed_records[:sample_limit]
        ]
        count = evaluation.failed_record_count
        noun = "record" if count == 1 else "records"
        incidents.append(
            Incident(
                incident_id=factory(),
                detected_at=timestamp,
                dataset=evaluation.dataset,
                rule_name=evaluation.rule_name,
                severity=evaluation.severity,
                failed_record_count=count,
                sample_records=sample,
                summary=(
                    f"{count} {noun} in {evaluation.dataset} violated "
                    f"{evaluation.rule_name} ({evaluation.description})."
                ),
            )
        )
    return incidents
