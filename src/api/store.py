"""In-memory incident records for the local API.

The registry stores incident status and an optional analysis. It has no
method that writes telemetry.
"""

from dataclasses import dataclass

from models.analysis import RootCauseAnalysis
from models.incident import Incident
from rag.retriever import RetrievedPassage


class IncidentNotFound(Exception):
    def __init__(self, incident_id: str) -> None:
        self.incident_id = incident_id
        super().__init__(f"incident {incident_id} was not found")


@dataclass(frozen=True)
class IncidentRecord:
    incident: Incident
    analysis: RootCauseAnalysis | None = None
    sources: tuple[RetrievedPassage, ...] = ()


class IncidentRegistry:
    def __init__(self, incidents: list[Incident]) -> None:
        self._items: dict[str, IncidentRecord] = {}
        for incident in incidents:
            if incident.incident_id in self._items:
                raise ValueError(f"duplicate incident id {incident.incident_id}")
            self._items[incident.incident_id] = IncidentRecord(incident=incident)

    def list_incidents(self) -> list[Incident]:
        return [record.incident for record in self._items.values()]

    def get(self, incident_id: str) -> IncidentRecord:
        try:
            return self._items[incident_id]
        except KeyError as exc:
            raise IncidentNotFound(incident_id) from exc

    def save(self, record: IncidentRecord) -> None:
        if record.incident.incident_id not in self._items:
            raise IncidentNotFound(record.incident.incident_id)
        self._items[record.incident.incident_id] = record
