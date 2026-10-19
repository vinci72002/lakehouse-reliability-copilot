"""Incident API. Routes do not apply recommendations to telemetry tables."""

from api.app import create_app, sample_incidents

__all__ = ["create_app", "sample_incidents"]
