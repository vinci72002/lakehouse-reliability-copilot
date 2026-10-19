"""Lexical retrieval over the reliability knowledge base.

Documents are split on markdown headings and ranked by token overlap
with the incident. The score is deterministic, so tests do not need a
network or an embedding model.
"""

import math
import re
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from models.incident import Incident

_TOKEN = re.compile(r"[a-z0-9_]+")
_HEADING = re.compile(r"^(#{1,3})[ \t]+(.+?)\s*$", re.MULTILINE)
_STOP = {
    "the",
    "and",
    "for",
    "from",
    "with",
    "that",
    "this",
    "are",
    "was",
    "were",
    "not",
    "into",
}

CATEGORIES = {
    "telemetry_schema.md": "schema",
    "sla.md": "sla",
    "pipeline.md": "pipeline",
    "historical_incidents.md": "historical_incidents",
    "dq_rules.md": "pipeline",
    "incident_playbook.md": "pipeline",
}


class RetrievedPassage(BaseModel):
    """One heading-sized passage returned to the analyst."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str = Field(min_length=1)
    category: str = Field(min_length=1)
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    score: float = Field(ge=0)


def default_knowledge_base_dir() -> Path:
    """Repository ``data/knowledge_base`` next to ``src``."""
    return Path(__file__).resolve().parents[2] / "data" / "knowledge_base"


class KnowledgeBase:
    """In-memory index of markdown passages."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else default_knowledge_base_dir()
        if not self.root.is_dir():
            raise FileNotFoundError(f"knowledge base directory not found: {self.root}")
        self.passages = _load_passages(self.root)

    def retrieve(self, query: str, *, top_k: int = 4) -> list[RetrievedPassage]:
        """Return the highest-scoring passages for a text query.

        The first pass keeps the best passage from each matching category
        so schema, SLA, pipeline notes, and historical incidents can all
        appear. Remaining slots are filled by score.
        """
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        query_tokens = _query_tokens(query)
        if not query_tokens:
            raise ValueError("query must contain at least one searchable term")

        ranked = [
            passage.model_copy(update={"score": score})
            for passage in self.passages
            if (score := _score(query_tokens, passage)) > 0
        ]
        ranked.sort(key=lambda passage: (-passage.score, passage.source, passage.title))
        if top_k == 1:
            return ranked[:1]

        selected: list[RetrievedPassage] = []
        seen_categories: set[str] = set()
        for passage in ranked:
            if passage.category in seen_categories:
                continue
            selected.append(passage)
            seen_categories.add(passage.category)
            if len(selected) == top_k:
                return selected
        chosen = {(passage.source, passage.title) for passage in selected}
        for passage in ranked:
            if (passage.source, passage.title) in chosen:
                continue
            selected.append(passage)
            if len(selected) == top_k:
                break
        return selected

    def retrieve_for_incident(self, incident: Incident, *, top_k: int = 4) -> list[RetrievedPassage]:
        """Retrieve passages for an incident, its sample, and its rule."""
        return self.retrieve(_query_for_incident(incident), top_k=top_k)


def _query_for_incident(incident: Incident) -> str:
    parts = [
        incident.rule_name,
        incident.dataset,
        incident.summary,
        incident.severity.value,
    ]
    for record in incident.sample_records[:3]:
        parts.extend(f"{key} {value}" for key, value in record.items())
    return " ".join(parts)


def _load_passages(root: Path) -> list[RetrievedPassage]:
    passages: list[RetrievedPassage] = []
    for path in sorted(root.glob("*.md")):
        category = CATEGORIES.get(path.name, "general")
        for title, body in _split_sections(path.read_text(encoding="utf-8")):
            passages.append(
                RetrievedPassage(
                    source=path.name,
                    category=category,
                    title=title,
                    text=body,
                    score=0,
                )
            )
    return passages


def _split_sections(text: str) -> list[tuple[str, str]]:
    matches = list(_HEADING.finditer(text))
    if not matches:
        stripped = text.strip()
        return [("Document", stripped)] if stripped else []
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        title = match.group(2).strip()
        body = text[match.end() : end].strip()
        chunk = f"{title}\n{body}".strip()
        if title and chunk:
            sections.append((title, chunk))
    return sections


def _query_tokens(query: str) -> list[str]:
    found: set[str] = set()
    tokens: list[str] = []
    for token in _TOKEN.findall(query.lower()):
        if len(token) <= 1 or token in _STOP or token in found:
            continue
        found.add(token)
        tokens.append(token)
    return tokens


def _score(query_tokens: list[str], passage: RetrievedPassage) -> float:
    counts = Counter(
        token
        for token in _TOKEN.findall(f"{passage.title}\n{passage.text}".lower())
        if len(token) > 1 and token not in _STOP
    )
    return sum(1.0 + math.log1p(counts[token]) for token in query_tokens if token in counts)
