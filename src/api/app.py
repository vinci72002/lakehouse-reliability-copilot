"""FastAPI routes for incident review.

Analysis stores a recommendation. Approve and reject record a human
decision. None of these routes modify telemetry tables.
"""

from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request

from ai.analyst import (
    AnalysisError,
    MockAnalyst,
    OpenAICompatibleAnalyst,
    UnknownRuleError,
    build_analyst_from_env,
)
from ai.workflow import analyze_incident
from api.schemas import (
    AnalyzeResponse,
    DecisionRequest,
    DecisionResponse,
    IncidentDetailResponse,
    IncidentListResponse,
)
from api.store import IncidentNotFound, IncidentRecord, IncidentRegistry
from audit.approval import ApprovalDecision, submit_human_decision
from audit.log import AuditLog, record_analysis
from ingestion.faults import FaultInjection, FaultKind
from ingestion.generator import generate_telemetry
from models.incident import Incident
from pipelines.medallion import run_medallion
from rag.retriever import KnowledgeBase, default_knowledge_base_dir

_DETECTED_AT = datetime(2026, 10, 19, 13, 0, tzinfo=timezone.utc)


def create_app(
    *,
    incidents: list[Incident] | None = None,
    knowledge_base: Path | None = None,
    analyst: MockAnalyst | OpenAICompatibleAnalyst | None = None,
    audit_path: Path | None = None,
) -> FastAPI:
    """Build the local incident API.

    ``analyst`` defaults to the process environment. Tests pass
    ``MockAnalyst`` so they stay offline.
    """
    app = FastAPI(
        title="Lakehouse Reliability Copilot",
        version="0.2.0",
        description=(
            "Incident analysis for aircraft telemetry. "
            "Recommendations do not write lakehouse tables. "
            "A person must approve or reject each incident."
        ),
    )
    app.state.registry = IncidentRegistry(sample_incidents() if incidents is None else incidents)
    app.state.audit = AuditLog(audit_path or default_audit_path())
    app.state.knowledge = KnowledgeBase(knowledge_base or default_knowledge_base_dir())
    app.state.analyst = analyst if analyst is not None else build_analyst_from_env()

    @app.get("/incidents", response_model=IncidentListResponse)
    def list_incidents(request: Request) -> IncidentListResponse:
        return IncidentListResponse(incidents=request.app.state.registry.list_incidents())

    @app.get("/incidents/{incident_id}", response_model=IncidentDetailResponse)
    def get_incident(incident_id: str, request: Request) -> IncidentDetailResponse:
        record = _record(request, incident_id)
        return _detail(record)

    @app.post("/incidents/{incident_id}/analyze", response_model=AnalyzeResponse)
    def analyze(incident_id: str, request: Request) -> AnalyzeResponse:
        record = _record(request, incident_id)
        try:
            completed = analyze_incident(
                record.incident,
                knowledge_base=request.app.state.knowledge,
                analyst=request.app.state.analyst,
            )
        except UnknownRuleError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except AnalysisError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        saved = IncidentRecord(
            incident=record.incident,
            analysis=completed.analysis,
            sources=tuple(completed.passages),
        )
        request.app.state.registry.save(saved)
        record_analysis(saved.incident, completed.analysis, request.app.state.audit, actor="ai-analyst")
        return AnalyzeResponse(
            incident=saved.incident,
            analysis=completed.analysis,
            sources=list(saved.sources),
        )

    @app.post("/incidents/{incident_id}/approve", response_model=DecisionResponse)
    def approve(incident_id: str, body: DecisionRequest, request: Request) -> DecisionResponse:
        return _decide(incident_id, body, request, ApprovalDecision.APPROVE)

    @app.post("/incidents/{incident_id}/reject", response_model=DecisionResponse)
    def reject(incident_id: str, body: DecisionRequest, request: Request) -> DecisionResponse:
        return _decide(incident_id, body, request, ApprovalDecision.REJECT)

    return app


def sample_incidents() -> list[Incident]:
    """Open one incident for each Phase 1 fault. Does not publish Delta tables."""
    faults = [FaultInjection(kind=kind, count=1) for kind in FaultKind]
    events = generate_telemetry(record_count=40, aircraft_count=4, seed=19, faults=faults)
    return run_medallion(events, detected_at=_DETECTED_AT).incidents


def default_audit_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "lakehouse" / "audit" / "audit_log.jsonl"


def _record(request: Request, incident_id: str) -> IncidentRecord:
    try:
        return request.app.state.registry.get(incident_id)
    except IncidentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _detail(record: IncidentRecord) -> IncidentDetailResponse:
    return IncidentDetailResponse(
        incident=record.incident,
        analysis=record.analysis,
        sources=list(record.sources),
    )


def _decide(
    incident_id: str,
    body: DecisionRequest,
    request: Request,
    decision: ApprovalDecision,
) -> DecisionResponse:
    record = _record(request, incident_id)
    try:
        updated, entry = submit_human_decision(
            record.incident,
            actor=body.actor,
            decision=decision,
            note=body.note,
            audit_log=request.app.state.audit,
        )
    except ValueError as exc:
        status_code = 409 if "already" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    request.app.state.registry.save(
        IncidentRecord(incident=updated, analysis=record.analysis, sources=record.sources)
    )
    return DecisionResponse(incident=updated, audit_id=entry.audit_id)
