# Lakehouse Reliability Copilot

Phase 1 is a local data-reliability pipeline for aircraft telemetry. It lands a synthetic fleet sample in a medallion layout, checks five data-quality rules, opens an incident for each failure, and records human approval in an audit log.

The batch is Databricks-shaped: the same schemas, rule SQL, and Spark filters are what a cluster job would run. Phase 1 executes them on this machine. It does not call a model, and it does not let an automated recommendation change telemetry.

## Flow

```text
synthetic telemetry
  -> bronze
  -> data-quality checks
  -> incidents
  -> silver (rows that pass every rule)
  -> gold flight summary
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
src/rag           Phase 2 retrieval
src/ai            Phase 2 root-cause analysis
src/api           Phase 2 FastAPI
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

The Docker image installs the same dependencies and runs the test suite:

```powershell
docker build -t lakehouse-reliability-copilot .
docker run --rm lakehouse-reliability-copilot
```

## Phase 1 scope

Included: telemetry models, a deterministic generator, duplicate and sensor faults, data-quality rules, incidents, a local medallion run, Delta table snapshots, Spark silver/gold transforms, and human approval with an audit log.

Not included yet: retrieval, a language model, FastAPI, and a frontend. `src/models/analysis.py` only defines the structured root-cause result those later steps must return.

See [docs/architecture.md](docs/architecture.md) and [docs/phase2.md](docs/phase2.md).
