"""Run the Phase 1 medallion batch and print the incidents it opens."""

import sys
from pathlib import Path

from pipelines.demo import run_demo


def main() -> None:
    lake_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/lakehouse")
    demo = run_demo(lake_root)
    result = demo.result
    print(
        f"Bronze: {len(result.bronze)}  "
        f"Silver: {len(result.silver)}  "
        f"Gold flights: {len(result.gold)}  "
        f"Quarantine: {len(result.quarantined)}"
    )
    for incident in result.incidents:
        print(
            f"{incident.incident_id}  {incident.severity.value}  "
            f"{incident.rule_name}  failed={incident.failed_record_count}  "
            f"{incident.summary}"
        )
    print(f"Delta bronze: {demo.tables.bronze}")
    print(f"Audit log: {demo.audit_log}")


if __name__ == "__main__":
    main()
