"""Connect an incident to retrieval and a structured root-cause analysis.

This module returns an analysis. It does not publish Delta tables or
change the incident status.
"""

from dataclasses import dataclass

from ai.analyst import AnalysisError, AnalysisRequest, MockAnalyst, OpenAICompatibleAnalyst, UnknownRuleError
from dq.rules import QualityRule, default_rules
from models.analysis import RootCauseAnalysis
from models.datasets import validate_dataset_name
from models.incident import Incident
from rag.retriever import KnowledgeBase, RetrievedPassage


@dataclass(frozen=True)
class CompletedAnalysis:
    analysis: RootCauseAnalysis
    passages: list[RetrievedPassage]
    request: AnalysisRequest


def analyze_incident(
    incident: Incident,
    *,
    knowledge_base: KnowledgeBase,
    analyst: MockAnalyst | OpenAICompatibleAnalyst,
    rules: tuple[QualityRule, ...] | None = None,
    top_k: int = 4,
) -> CompletedAnalysis:
    """Retrieve context and validate the analyst output as RootCauseAnalysis."""
    catalog = tuple(default_rules() if rules is None else rules)
    rule = next((item for item in catalog if item.name == incident.rule_name), None)
    if rule is None:
        raise UnknownRuleError(f"unknown data-quality rule: {incident.rule_name}")
    try:
        dataset = validate_dataset_name(incident.dataset)
        violation_sql = rule.violation_sql.format(dataset=dataset)
    except (KeyError, IndexError, ValueError) as exc:
        raise AnalysisError(f"could not render validation SQL for {rule.name}") from exc
    passages = knowledge_base.retrieve_for_incident(incident, top_k=top_k)
    request = AnalysisRequest(
        incident=incident,
        rule_description=rule.description,
        violation_sql=violation_sql,
        passages=passages,
    )
    analysis = analyst.analyze(request)
    return CompletedAnalysis(analysis=analysis, passages=passages, request=request)
