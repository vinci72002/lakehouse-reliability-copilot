"""Run data-quality rules against an in-memory telemetry batch."""

from collections.abc import Sequence

from dq.rules import QualityRule, default_rules
from models.datasets import BRONZE_AIRCRAFT_TELEMETRY, validate_dataset_name
from models.quality import RuleEvaluation
from models.telemetry import TelemetryEvent


def run_quality_checks(
    records: Sequence[TelemetryEvent],
    *,
    dataset: str = BRONZE_AIRCRAFT_TELEMETRY,
    rules: Sequence[QualityRule] | None = None,
) -> list[RuleEvaluation]:
    """Evaluate each rule independently against the same row order."""
    dataset_name = validate_dataset_name(dataset)
    selected = tuple(default_rules() if rules is None else rules)
    evaluations: list[RuleEvaluation] = []
    for rule in selected:
        indices = sorted(set(rule.find_failures(records)))
        failed_records = [records[index] for index in indices]
        evaluations.append(
            RuleEvaluation(
                rule_name=rule.name,
                severity=rule.severity,
                description=rule.description,
                dataset=dataset_name,
                passed=not indices,
                failed_record_count=len(indices),
                failed_indices=indices,
                failed_records=failed_records,
                violation_sql=rule.violation_sql.format(dataset=dataset_name),
            )
        )
    return evaluations
