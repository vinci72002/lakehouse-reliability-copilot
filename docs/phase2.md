# Phase 2

Phase 2 is the incident-analysis workflow. Retrieval, the structured analyst, and the review API are in place. A model still cannot write telemetry.

## What runs locally

- `src/rag` loads `data/knowledge_base` and retrieves schema, SLA, pipeline, and historical-incident passages for an open incident.
- `src/ai` turns the incident, the failed sample, the data-quality rule, and those passages into a `RootCauseAnalysis`.
- `LLM_PROVIDER=mock` is the default and is what the tests use. `LLM_PROVIDER=openai` or `openai_compatible` calls `POST {LLM_BASE_URL}/chat/completions` with `LLM_API_KEY` and `LLM_MODEL`.
- `src/api` serves:
  - `GET /incidents`
  - `GET /incidents/{id}`
  - `POST /incidents/{id}/analyze`
  - `POST /incidents/{id}/approve`
  - `POST /incidents/{id}/reject`
- Approve and reject call `submit_human_decision`. The body is an actor and a note. Extra fields are rejected. A second decision on the same incident is rejected.

## Still later

- Databricks entry point that writes Delta with `df.write.format("delta")`, plus incremental bronze append and silver merge.
- Quality checks that need more than one row, such as position jumps and fuel that increases during a flight.
- A review screen. It should show the incident, the evidence, and the approval buttons, and it should not gain a control that rewrites production data.
- Streaming ingest, experiment tracking, and multi-agent orchestration are out of scope.
