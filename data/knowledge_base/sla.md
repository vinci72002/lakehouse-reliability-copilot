# Service level

These are the reliability targets for the aircraft telemetry lakehouse. An analysis does not close an incident and does not stop the review clock.

## Freshness

Bronze aircraft telemetry is expected within 15 minutes of the source event. Data-quality checks finish within 5 minutes of the bronze batch landing. Gold flight summaries are published from the silver rows of that same batch.

## Review windows

Severity sets the human review target:

- critical, including `fuel_non_negative`: a person decides within 60 minutes
- high, including `event_id_unique` and `flight_id_not_null`: a person decides within 4 hours
- medium, including `altitude_in_range` and `engine_temp_not_null`: a person decides within one business day

The analyst may prepare a recommendation before that deadline. Only the human decision meets the review window.
