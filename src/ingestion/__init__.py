"""Synthetic telemetry ingestion."""

from ingestion.faults import FaultInjection, FaultKind, apply_faults
from ingestion.generator import generate_telemetry

__all__ = [
    "FaultInjection",
    "FaultKind",
    "apply_faults",
    "generate_telemetry",
]
