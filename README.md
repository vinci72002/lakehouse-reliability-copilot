# Lakehouse Reliability Copilot

Local data-reliability pipeline for aircraft telemetry. A batch lands in a medallion layout, checks five data-quality rules, and opens an incident for each failure. Phase 2 retrieves knowledge-base context, writes a structured root-cause analysis, and waits for a person to approve or reject it.

The batch is Databricks-shaped: the same schemas, rule SQL, and Spark filters are what a cluster job would run. Analysis never rewrites telemetry.

## Flow

```text
synthetic telemetry
  -> bronze
  -> data-quality checks
  -> incidents
  -> silver (rows that pass every rule)
  -> gold flight summary
  -> RAG context
  -> root-cause analysis
  -> human approval
  -> audit log
```

Bronze keeps the raw batch, including injected faults. Silver drops every row that fails a rule. An exact duplicate fails `event_id_unique`, so both copies stay out of silver instead of the pipeline silently keeping one. Gold aggregates silver only.

Approving an incident changes its status and appends an audit entry. It does not rewrite bronze, silver, gold, or quarantine.

## Project structure

```text
src/models        telemetry, gold, quality, incident, and analysis contracts
src/ingestion     synthetic generator and fault injection
src/pipelines     medallion run, Delta snapshots, local Spark transforms
src/dq            rules, evaluation, incident creation
src/audit         append-only audit log and human approval
src/rag           knowledge-base retrieval
src/ai            mock and OpenAI-compatible root-cause analysis
src/api           FastAPI incident, analysis, and approval routes
tests             pytest suite
docs              architecture and the Phase 2 plan
data/knowledge_base
                  source documents for later retrieval
scripts/run_phase1.py
```

## Run tests

Java 17 is required for the Spark parity test. Delta snapshots use `deltalake` and do not need Hadoop native binaries.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest
```

Run the local batch and write Delta tables under `data/lakehouse`:

```powershell
python scripts/run_phase1.py
```

Start the incident API. `LLM_PROVIDER` defaults to `mock`, which needs no network. Set `LLM_PROVIDER=openai` with `LLM_API_KEY`, and optionally `LLM_MODEL` and `LLM_BASE_URL`, to call an OpenAI-compatible chat endpoint.

```powershell
uvicorn api.asgi:app --reload
```

`GET /incidents`, `GET /incidents/{id}`, `POST /incidents/{id}/analyze`, `POST /incidents/{id}/approve`, and `POST /incidents/{id}/reject` are the Phase 2 routes. Approve and reject require an actor and a note. They change incident status only.

The Docker image installs the same dependencies and runs the test suite:

```powershell
docker build -t lakehouse-reliability-copilot .
docker run --rm lakehouse-reliability-copilot
```

## Scope

Phase 1: telemetry models, a deterministic generator, fault injection, data-quality rules, incidents, a local medallion run, Delta snapshots, and Spark silver/gold transforms.

Phase 2: retrieval over schema, SLA, pipeline, and historical-incident notes; a mock analyst plus an OpenAI-compatible analyst; FastAPI review routes; human approval with an audit log.

Still later: a review screen, streaming ingest, experiment tracking, and multi-agent orchestration. See [docs/architecture.md](docs/architecture.md) and [docs/phase2.md](docs/phase2.md).
