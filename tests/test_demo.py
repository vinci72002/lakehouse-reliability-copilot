"""End-to-end local batch used by scripts/run_phase1.py."""

from audit.log import AuditLog
from pipelines.demo import run_demo


def test_demo_publishes_delta_and_audits_incidents(tmp_path) -> None:
    demo = run_demo(tmp_path)
    assert demo.result.incidents
    assert len(demo.result.incidents) == 5
    assert demo.tables.bronze.exists()
    assert demo.tables.gold.exists()
    entries = AuditLog(demo.audit_log).read_all()
    assert len(entries) == len(demo.result.incidents)
    assert {entry.actor for entry in entries} == {"dq-engine"}
