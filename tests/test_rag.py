"""Retrieval over schema, SLA, pipeline notes, and historical incidents."""

from datetime import datetime, timezone

import pytest

from dq.engine import run_quality_checks
from dq.incidents import create_incidents
from factories import make_event
from rag.retriever import KnowledgeBase, default_knowledge_base_dir

DETECTED_AT = datetime(2026, 10, 19, 18, 0, tzinfo=timezone.utc)


def test_default_corpus_has_the_phase2_documents() -> None:
    names = {path.name for path in default_knowledge_base_dir().glob("*.md")}
    assert {
        "telemetry_schema.md",
        "sla.md",
        "pipeline.md",
        "historical_incidents.md",
    } <= names


def test_queries_hit_schema_sla_pipeline_and_history() -> None:
    knowledge = KnowledgeBase()
    schema = knowledge.retrieve("ground_speed_kts", top_k=1)
    sla = knowledge.retrieve("freshness", top_k=1)
    pipeline = knowledge.retrieve("medallion", top_k=1)
    history = knowledge.retrieve("20260312", top_k=1)
    assert schema[0].source == "telemetry_schema.md"
    assert schema[0].category == "schema"
    assert sla[0].source == "sla.md"
    assert sla[0].category == "sla"
    assert pipeline[0].source == "pipeline.md"
    assert pipeline[0].category == "pipeline"
    assert history[0].source == "historical_incidents.md"
    assert history[0].category == "historical_incidents"


def test_incident_retrieval_covers_each_context_category() -> None:
    events = [
        make_event(event_id="EVT-BAD", fuel_remaining_kg=-12),
        make_event(event_id="EVT-OK", fuel_remaining_kg=20),
    ]
    incident = create_incidents(run_quality_checks(events), detected_at=DETECTED_AT)[0]
    passages = KnowledgeBase().retrieve_for_incident(incident, top_k=4)
    assert {passage.category for passage in passages} == {
        "schema",
        "sla",
        "pipeline",
        "historical_incidents",
    }
    assert any("fuel_non_negative" in passage.text for passage in passages)


def test_overlap_outranks_an_unrelated_document(tmp_path) -> None:
    (tmp_path / "matched.md").write_text("# Fuel\n\nfuel_non_negative fuel_remaining_kg sensor\n")
    (tmp_path / "other.md").write_text("# Weather\n\nharbor forecast and tides\n")
    found = KnowledgeBase(tmp_path).retrieve("fuel_non_negative sensor", top_k=2)
    assert [passage.source for passage in found] == ["matched.md"]


def test_top_k_limits_results(tmp_path) -> None:
    for name in ("one.md", "two.md", "three.md"):
        (tmp_path / name).write_text("# Note\n\nfuel_remaining_kg sensor\n")
    found = KnowledgeBase(tmp_path).retrieve("fuel_remaining_kg", top_k=2)
    assert len(found) == 2
    assert all(passage.score > 0 for passage in found)


def test_blank_query_and_missing_directory_are_rejected(tmp_path) -> None:
    (tmp_path / "note.md").write_text("# Note\n\nfuel\n")
    knowledge = KnowledgeBase(tmp_path)
    with pytest.raises(ValueError):
        knowledge.retrieve("the and", top_k=1)
    with pytest.raises(ValueError):
        knowledge.retrieve("fuel", top_k=0)
    with pytest.raises(FileNotFoundError):
        KnowledgeBase(tmp_path / "missing")
