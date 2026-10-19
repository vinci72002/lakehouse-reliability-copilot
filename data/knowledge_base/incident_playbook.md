# Incident playbook

An incident means one data-quality rule failed for a dataset. It is not itself a repair.

## What to read

- `rule_name` and `severity` say which contract broke.
- `failed_record_count` is the size of the failure.
- `sample_records` shows a few original bronze rows, capped at five.
- `summary` is a one-line description for the audit log.
- The matching SQL in the data-quality notes lists every violating row.

## What not to do

Do not backfill, delete, or overwrite production telemetry because a model suggested it. Quarantine of rows that fail a deterministic rule is done by the pipeline. Anything beyond that, including a recommended root-cause action, waits for a person.

Approval records the person, the decision, and a note. It does not change bronze, silver, gold, or quarantine. Rejection is also a decision and is audited. An incident that is already approved or rejected cannot be decided again.

## After a decision

1. Run the rule SQL against the dataset named on the incident.
2. Confirm silver no longer contains the failing rows.
3. Confirm gold flight summaries only count silver events.
4. If the source feed is fixed, ingest a new batch and show that the rule passes.
