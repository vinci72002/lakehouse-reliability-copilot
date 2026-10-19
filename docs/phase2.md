# Phase 2

Phase 1 lands data, checks it, opens incidents, and records a human decision. Phase 2 should add retrieval, a structured root-cause step, and an API, while keeping the same rule: a model never writes production telemetry.

## Data engineering

- Add a Databricks entry point that reuses `bronze_frame`, `silver_frame`, and `gold_frame` and writes Delta with `df.write.format("delta")`.
- Replace the local full-refresh publish with an incremental bronze append and a silver merge.
- Keep the Phase 1 rules as the first quality gate, then add checks that need more than one row: position jumps, vertical-speed spikes, and fuel that increases during a flight.
- Store incidents in a Delta table with a stable schema. Keep `sample_records` as a JSON string if the sample shape varies.
- Partition larger telemetry tables by event date as well as aircraft.

## Retrieval and analysis

- Embed `data/knowledge_base` and retrieve the rule, schema, and playbook passages that match an open incident.
- Call a model from `src/ai` and validate the response as `RootCauseAnalysis`.
- Put the rule's `violation_sql` in the prompt so `validation_sql` is a query a person can run, not a free-form guess.
- Return evidence that cites the retrieved passages and the incident sample.
- Leave `recommended_action` as text. Do not add a tool that updates bronze, silver, or gold from that text.

## API and approval

- Serve incidents, the analysis, and the audit log with FastAPI.
- `POST` approval through `submit_human_decision`, with the caller identity stored as `actor`.
- Reject any route whose body would apply `recommended_action` directly to a table.
- Keep the audit log append-only.

## Still later

A review screen can wait until the API and the analysis contract are stable. The screen should display the incident, the evidence, and the approval buttons. It should not gain a control that rewrites production data.
