"""Root-cause analysts.

``MockAnalyst`` is deterministic and is the default. ``OpenAICompatibleAnalyst``
calls a chat-completions endpoint configured with environment variables.
Neither analyst writes lakehouse tables.
"""

import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable

from models.analysis import RootCauseAnalysis
from models.incident import Incident
from rag.retriever import RetrievedPassage

Transport = Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]]

_CAUSES = {
    "event_id_unique": (
        "The same event_id was ingested more than once, so bronze contains "
        "duplicate telemetry events that may not carry the same payload."
    ),
    "flight_id_not_null": (
        "Telemetry arrived without a flight_id, so the event cannot be "
        "assigned to a flight or included in a gold summary."
    ),
    "fuel_non_negative": (
        "fuel_remaining_kg is negative. A fuel mass cannot be below zero, "
        "so the reading points to a sensor offset or a unit fault."
    ),
    "altitude_in_range": (
        "altitude_ft is outside the contracted range of -1,500 to 65,000 feet, "
        "which points to a sensor spike or a value written in the wrong unit."
    ),
    "engine_temp_not_null": (
        "engine_temp_c was not reported. The failure is a missing sample, "
        "not a measured temperature of zero."
    ),
}

_IMPACTS = {
    "event_id_unique": "Every copy is quarantined, so the duplicated events are missing from silver and gold.",
    "flight_id_not_null": "Gold cannot group the affected events, so those flights are incomplete.",
    "fuel_non_negative": "Gold fuel figures for the affected flights are untrusted while the bad rows stay in bronze.",
    "altitude_in_range": "Gold altitude ranges would be distorted if the out-of-range readings reached silver.",
    "engine_temp_not_null": "Gold cannot report a maximum engine temperature for rows that never measured one.",
}


class AnalysisError(Exception):
    """The analyst could not produce a valid RootCauseAnalysis."""


class UnknownRuleError(AnalysisError):
    """The incident names a rule this deployment does not know."""


@dataclass(frozen=True)
class AnalysisRequest:
    """Incident context handed to an analyst. It contains no write handle."""

    incident: Incident
    rule_description: str
    violation_sql: str
    passages: list[RetrievedPassage]


class MockAnalyst:
    """Build a RootCauseAnalysis from the incident, rule SQL, and passages."""

    def analyze(self, request: AnalysisRequest) -> RootCauseAnalysis:
        incident = request.incident
        cause = _CAUSES.get(
            incident.rule_name,
            f"{incident.rule_name} failed on {incident.dataset}. {request.rule_description}",
        )
        event_ids = [
            str(row["event_id"])
            for row in incident.sample_records
            if row.get("event_id")
        ]
        evidence = [
            (
                f"{incident.failed_record_count} records in {incident.dataset} "
                f"failed {incident.rule_name} ({request.rule_description})."
            ),
            (
                "Sample event_id values: " + ", ".join(event_ids)
                if event_ids
                else incident.summary
            ),
        ]
        evidence.extend(
            f"Retrieved {passage.category} from {passage.source}: {passage.title}"
            for passage in request.passages[:3]
        )
        return RootCauseAnalysis(
            root_cause=cause,
            evidence=evidence,
            impact=_IMPACTS.get(
                incident.rule_name,
                f"The {incident.severity.value} failure leaves {incident.dataset} only partly trustworthy.",
            ),
            validation_sql=request.violation_sql,
            recommended_action=(
                "A person should review the quarantined rows before any repair. "
                "This recommendation does not change bronze, silver, gold, or quarantine."
            ),
            verification_steps=[
                (
                    f"Run the validation SQL against {incident.dataset} and confirm "
                    f"the failed row count is {incident.failed_record_count}."
                ),
                "Confirm the failing event ids are absent from silver.aircraft_telemetry.",
                "After a human decision, ingest a new batch and show this rule passes before trusting gold.",
            ],
            confidence_score=_confidence(incident, request.passages),
        )


class OpenAICompatibleAnalyst:
    """Call an OpenAI-compatible chat completions endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 60,
        json_mode: bool = True,
        transport: Transport | None = None,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise AnalysisError("LLM_BASE_URL must start with http:// or https://")
        if not api_key.strip():
            raise AnalysisError("LLM_API_KEY must be non-empty")
        if not model.strip():
            raise AnalysisError("LLM_MODEL must be non-empty")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.timeout_seconds = timeout_seconds
        self.json_mode = json_mode
        self._transport = transport or self._default_transport

    def _default_transport(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        return _urllib_transport(url, payload, headers, timeout=self.timeout_seconds)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "OpenAICompatibleAnalyst":
        values = os.environ if env is None else env
        api_key = values.get("LLM_API_KEY", "").strip()
        if not api_key:
            raise AnalysisError("LLM_API_KEY is required when LLM_PROVIDER is openai")
        timeout_text = values.get("LLM_TIMEOUT_SECONDS", "60").strip()
        try:
            timeout_seconds = float(timeout_text)
        except ValueError as exc:
            raise AnalysisError("LLM_TIMEOUT_SECONDS must be a number") from exc
        json_mode = values.get("LLM_JSON_MODE", "true").strip().lower() not in {"0", "false", "no"}
        return cls(
            base_url=values.get("LLM_BASE_URL", "https://api.openai.com/v1").strip(),
            api_key=api_key,
            model=values.get("LLM_MODEL", "gpt-4o-mini").strip(),
            timeout_seconds=timeout_seconds,
            json_mode=json_mode,
        )

    def analyze(self, request: AnalysisRequest) -> RootCauseAnalysis:
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": 0,
            "messages": _messages(request),
        }
        if self.json_mode:
            payload["response_format"] = {"type": "json_object"}
        body = self._transport(
            f"{self.base_url}/chat/completions",
            payload,
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            content = _message_content(body)
            parsed = _parse_analysis_json(content)
            return RootCauseAnalysis.model_validate(parsed)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValueError) as exc:
            raise AnalysisError(f"LLM response was not a valid root-cause analysis: {exc}") from exc


def build_analyst_from_env(env: Mapping[str, str] | None = None) -> MockAnalyst | OpenAICompatibleAnalyst:
    """Select the analyst from ``LLM_PROVIDER``. The default is ``mock``."""
    values = os.environ if env is None else env
    provider = values.get("LLM_PROVIDER", "mock").strip().lower()
    if provider in {"", "mock"}:
        return MockAnalyst()
    if provider in {"openai", "openai_compatible"}:
        return OpenAICompatibleAnalyst.from_env(values)
    raise AnalysisError(f"unsupported LLM_PROVIDER: {provider}")


def _confidence(incident: Incident, passages: list[RetrievedPassage]) -> float:
    score = 0.45
    if incident.sample_records:
        score += 0.15
    if any(incident.rule_name in passage.text for passage in passages):
        score += 0.25
    if any(passage.category == "historical_incidents" for passage in passages):
        score += 0.1
    return min(score, 0.95)


def _messages(request: AnalysisRequest) -> list[dict[str, str]]:
    passages = "\n\n".join(
        f"[{passage.category}] {passage.source} / {passage.title}\n{_clip(passage.text)}"
        for passage in request.passages
    )
    samples = _clip(json.dumps(request.incident.sample_records, default=str), limit=2000)
    incident = request.incident
    user = "\n".join(
        [
            f"incident_id: {incident.incident_id}",
            f"dataset: {incident.dataset}",
            f"rule_name: {incident.rule_name}",
            f"rule_description: {request.rule_description}",
            f"severity: {incident.severity.value}",
            f"failed_record_count: {incident.failed_record_count}",
            f"summary: {incident.summary}",
            "violation_sql:",
            request.violation_sql,
            "sample_records:",
            samples or "[]",
            "retrieved_context:",
            passages or "(none)",
        ]
    )
    return [
        {
            "role": "system",
            "content": (
                "You are a data reliability analyst for an aircraft telemetry lakehouse. "
                "Return a single JSON object with the keys root_cause, evidence, impact, "
                "validation_sql, recommended_action, verification_steps, and confidence_score. "
                "evidence and verification_steps are arrays of non-empty strings. "
                "confidence_score is a number from 0 to 1. "
                "Use the violation SQL provided by the user as validation_sql. "
                "recommended_action is advice for a person. Do not claim that any table was changed."
            ),
        },
        {"role": "user", "content": user},
    ]


def _clip(text: str, limit: int = 1200) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _message_content(body: dict[str, Any]) -> str:
    content = body["choices"][0]["message"]["content"]
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("text"):
                parts.append(str(part["text"]))
        content = "\n".join(parts)
    if not isinstance(content, str) or not content.strip():
        raise AnalysisError("LLM response did not contain text content")
    return content


def _parse_analysis_json(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise AnalysisError("LLM JSON must be an object")
    if "confidence" in data and "confidence_score" not in data:
        data["confidence_score"] = data.pop("confidence")
    allowed = set(RootCauseAnalysis.model_fields)
    return {key: value for key, value in data.items() if key in allowed}


def _urllib_transport(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: float = 60,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AnalysisError(f"LLM request failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise AnalysisError(f"LLM request failed: {exc.reason}") from exc
