# Pipeline

Aircraft telemetry moves through a medallion layout. The analyst reads incidents from this pipeline. It does not repair tables.

## Medallion layout

Raw events land in `bronze.aircraft_telemetry`, including faulty measurements. Data-quality checks run on that bronze batch. Rows that fail any rule are copied to `quarantine.aircraft_telemetry`. Rows that pass every rule land in `silver.aircraft_telemetry`. `gold.flight_summary` aggregates silver by aircraft and flight.

## Quarantine

`event_id_unique` fails when an event id appears more than once. Every copy is quarantined, including the first, because the copies may disagree. `flight_id_not_null`, `fuel_non_negative`, `altitude_in_range`, and `engine_temp_not_null` each remove the rows that break that rule. Silver does not choose a survivor for a duplicate.

## Analysis gate

Root-cause analysis is attached to an open incident after bronze checks have already quarantined the bad rows. The recommendation is text for a person. Approval and rejection change the incident status and the audit log. They do not rewrite bronze, silver, gold, or quarantine.
