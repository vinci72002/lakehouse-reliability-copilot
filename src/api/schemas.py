"""Request and response models for the incident API."""

from pydantic import BaseModel, ConfigDict, Field

from models.analysis import RootCauseAnalysis
from models.incident import Incident
from rag.retriever import RetrievedPassage


class IncidentListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incidents: list[Incident]


class IncidentDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident: Incident
    analysis: RootCauseAnalysis | None = None
    sources: list[RetrievedPassage] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident: Incident
    analysis: RootCauseAnalysis
    sources: list[RetrievedPassage]


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: str = Field(min_length=1)
    note: str = Field(min_length=1)


class DecisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident: Incident
    audit_id: str
