"""HTTP workflow for listing, analysis, and human approval."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from ai.analyst import MockAnalyst
from api.app import create_app
from audit.log import AuditAction, AuditLog
from dq.engine import run_quality_checks
from dq.incidents import create_incidents
from factories import make_event
from models.incident import IncidentStatus

DETECTED_AT = datetime(2026, 10, 19, 20, 0, tzinfo=timezone.utc)


def _incidents():
    fuel = create_incidents(
        run_quality_checks([make_event(event_id="EVT-FUEL", fuel_remaining_kg=-8)]),
        detected_at=DETECTED_AT,
        id_factory=lambda: "INC-FUEL",
    )
    altitude = create_incidents(
        run_quality_checks([make_event(event_id="EVT-ALT", altitude_ft=120_000)]),
        detected_at=DETECTED_AT,
        id_factory=lambda: "INC-ALT",
    )
    return [fuel[0], altitude[0]]


def _client(tmp_path) -> TestClient:
    app = create_app(
        incidents=_incidents(),
        analyst=MockAnalyst(),
        audit_path=tmp_path / "audit.jsonl",
    )
    return TestClient(app)


def test_list_detail_analyze_and_approve(tmp_path) -> None:
    client = _client(tmp_path)
    listed = client.get("/incidents")
    assert listed.status_code == 200
    assert [item["incident_id"] for item in listed.json()["incidents"]] == ["INC-FUEL", "INC-ALT"]

    detail = client.get("/incidents/INC-FUEL")
    assert detail.status_code == 200
    assert detail.json()["analysis"] is None
    assert detail.json()["incident"]["status"] == IncidentStatus.OPEN.value

    analyzed = client.post("/incidents/INC-FUEL/analyze")
    assert analyzed.status_code == 200
    body = analyzed.json()
    assert body["incident"]["status"] == "open"
    assert "fuel_remaining_kg < 0" in body["analysis"]["validation_sql"]
    assert body["analysis"]["evidence"]
    assert body["analysis"]["verification_steps"]
    assert 0 <= body["analysis"]["confidence_score"] <= 1
    assert body["sources"]
    assert "does not change" in body["analysis"]["recommended_action"]

    again = client.get("/incidents/INC-FUEL")
    assert again.json()["analysis"]["root_cause"]
    assert again.json()["incident"]["status"] == "open"

    approved = client.post(
        "/incidents/INC-FUEL/approve",
        json={"actor": "morgan", "note": "Keep the rows quarantined."},
    )
    assert approved.status_code == 200
    assert approved.json()["incident"]["status"] == "approved"
    assert client.get("/incidents/INC-FUEL").json()["incident"]["status"] == "approved"

    conflict = client.post(
        "/incidents/INC-FUEL/approve",
        json={"actor": "morgan", "note": "Trying again."},
    )
    assert conflict.status_code == 409
    assert not (tmp_path / "bronze").exists()

    actions = [entry.action for entry in AuditLog(tmp_path / "audit.jsonl").read_all()]
    assert actions == [AuditAction.ANALYSIS_RECORDED, AuditAction.HUMAN_APPROVED]


def test_reject_unknown_rule_and_closed_routes(tmp_path) -> None:
    client = _client(tmp_path)
    missing = client.get("/incidents/INC-MISSING")
    assert missing.status_code == 404

    rejected = client.post(
        "/incidents/INC-ALT/reject",
        json={"actor": "sam", "note": "Expected probe from the adapter test."},
    )
    assert rejected.status_code == 200
    assert rejected.json()["incident"]["status"] == "rejected"

    blank = client.post(
        "/incidents/INC-FUEL/approve",
        json={"actor": "sam", "note": "   "},
    )
    assert blank.status_code == 400

    extra = client.post(
        "/incidents/INC-FUEL/approve",
        json={"actor": "sam", "note": "apply it", "apply_to_bronze": True},
    )
    assert extra.status_code == 422

    paths = {getattr(route, "path", "") for route in client.app.routes}
    assert "/incidents" in paths
    assert "/incidents/{incident_id}/analyze" in paths
    assert "/incidents/{incident_id}/approve" in paths
    assert "/incidents/{incident_id}/reject" in paths
    assert not any("bronze" in path or "telemetry" in path for path in paths)

    unknown = create_app(
        incidents=[
            _incidents()[0].model_copy(update={"incident_id": "INC-BAD", "rule_name": "not_a_rule"})
        ],
        analyst=MockAnalyst(),
        audit_path=tmp_path / "other-audit.jsonl",
    )
    response = TestClient(unknown).post("/incidents/INC-BAD/analyze")
    assert response.status_code == 422
