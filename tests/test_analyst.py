"""Structured root-cause output from the mock analyst and the HTTP analyst."""

import json
from datetime import datetime, timezone

import pytest

from ai.analyst import (
    AnalysisError,
    AnalysisRequest,
    MockAnalyst,
    OpenAICompatibleAnalyst,
    build_analyst_from_env,
)
from dq.engine import run_quality_checks
from dq.incidents import create_incidents
from factories import make_event
from models.analysis import RootCauseAnalysis
from rag.retriever import RetrievedPassage

DETECTED_AT = datetime(2026, 10, 19, 18, 30, tzinfo=timezone.utc)


def _request() -> AnalysisRequest:
    events = [make_event(event_id="EVT-BAD", fuel_remaining_kg=-12)]
    incident = create_incidents(
        run_quality_checks(events),
        detected_at=DETECTED_AT,
        id_factory=lambda: "INC-FUEL",
    )[0]
    passage = RetrievedPassage(
        source="historical_incidents.md",
        category="historical_incidents",
        title="Negative fuel after a sensor swap",
        text="Incident 20260312 failed fuel_non_negative.",
        score=1.5,
    )
    return AnalysisRequest(
        incident=incident,
        rule_description="fuel_remaining_kg must be greater than or equal to 0",
        violation_sql="SELECT *\nFROM bronze.aircraft_telemetry\nWHERE fuel_remaining_kg < 0",
        passages=[passage],
    )


def _valid_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "root_cause": "Sensor offset",
        "evidence": ["fuel_remaining_kg is -12"],
        "impact": "Gold fuel is untrusted",
        "validation_sql": "SELECT * FROM bronze.aircraft_telemetry WHERE fuel_remaining_kg < 0",
        "recommended_action": "Ask a person to review the sensor",
        "verification_steps": ["Run the validation SQL"],
        "confidence_score": 0.8,
    }
    payload.update(overrides)
    return payload


def test_mock_analysis_is_deterministic_and_uses_the_rule_sql() -> None:
    request = _request()
    first = MockAnalyst().analyze(request)
    second = MockAnalyst().analyze(request)
    assert first == second
    assert isinstance(first, RootCauseAnalysis)
    assert first.validation_sql == request.violation_sql
    assert "EVT-BAD" in first.evidence[1]
    assert any("historical_incidents.md" in item for item in first.evidence)
    assert "does not change" in first.recommended_action
    assert first.confidence_score == 0.95


def test_openai_transport_sends_the_incident_and_parses_json() -> None:
    seen: dict[str, object] = {}

    def transport(url: str, payload: dict, headers: dict) -> dict:
        seen["url"] = url
        seen["payload"] = payload
        seen["authorization"] = headers["Authorization"]
        return {"choices": [{"message": {"content": json.dumps(_valid_payload())}}]}

    analyst = OpenAICompatibleAnalyst(
        base_url="https://example.test/v1",
        api_key="secret",
        model="unit-model",
        transport=transport,
    )
    analysis = analyst.analyze(_request())
    assert analysis.root_cause == "Sensor offset"
    assert seen["url"] == "https://example.test/v1/chat/completions"
    assert seen["authorization"] == "Bearer secret"
    prompt = seen["payload"]["messages"][1]["content"]  # type: ignore[index]
    assert "EVT-BAD" in prompt
    assert "fuel_remaining_kg < 0" in prompt
    assert "historical_incidents.md" in prompt


def test_openai_parser_accepts_fences_and_confidence_alias() -> None:
    body = _valid_payload()
    body.pop("confidence_score")
    body["confidence"] = 0.4
    body["extra"] = "ignore me"
    fenced = "```json\n" + json.dumps(body) + "\n```"

    def transport(url: str, payload: dict, headers: dict) -> dict:
        return {"choices": [{"message": {"content": fenced}}]}

    analysis = OpenAICompatibleAnalyst(
        base_url="http://localhost:11434/v1",
        api_key="local",
        model="local",
        transport=transport,
    ).analyze(_request())
    assert analysis.confidence_score == 0.4


def test_invalid_model_output_raises() -> None:
    def transport(url: str, payload: dict, headers: dict) -> dict:
        return {"choices": [{"message": {"content": "not-json"}}]}

    analyst = OpenAICompatibleAnalyst(
        base_url="https://example.test/v1",
        api_key="secret",
        model="unit-model",
        transport=transport,
    )
    with pytest.raises(AnalysisError):
        analyst.analyze(_request())


def test_provider_selection_uses_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert isinstance(build_analyst_from_env(), MockAnalyst)

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(AnalysisError):
        build_analyst_from_env()

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test/v1")
    analyst = build_analyst_from_env()
    assert isinstance(analyst, OpenAICompatibleAnalyst)
    assert analyst.model == "test-model"
    assert analyst.base_url == "https://example.test/v1"

    monkeypatch.setenv("LLM_PROVIDER", "other")
    with pytest.raises(AnalysisError):
        build_analyst_from_env()
