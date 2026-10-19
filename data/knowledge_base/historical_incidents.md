# Historical incidents

Past aircraft-telemetry incidents used as analysis examples. None of these cases was repaired by an automated write to a production table.

## Negative fuel after a sensor swap

Incident `20260312` failed `fuel_non_negative` on `bronze.aircraft_telemetry`. `fuel_remaining_kg` dropped below 0 for one airframe after a fuel-sensor replacement. The mass reading was a sensor offset, not a real fuel load. The batch quarantined those rows. A person rejected a backfill and asked maintenance to recalibrate the sensor. The next batch passed the rule.

## Replayed bronze file

Incident `20260402` failed `event_id_unique`. A file replay loaded the same `event_id` values twice. The copies were not identical, so both copies were quarantined and those events were absent from gold. The feed owner stopped the replay. No row was chosen automatically.

## Missing flight assignment

Incident `20260518` failed `flight_id_not_null`. Position events arrived while the flight-assignment feed was late, so `flight_id` was null. Gold could not group those events. They stayed in quarantine until a later batch arrived with the flight id populated.

## Altitude stored in the wrong unit

Incident `20260701` failed `altitude_in_range`. A downstream adapter wrote meters into `altitude_ft`, producing values well above 65,000. The rows were quarantined. The adapter was corrected. Analysts were told not to multiply historical bronze rows in place.

## Dropped engine-temperature samples

Incident `20260809` failed `engine_temp_not_null`. `engine_temp_c` was null while the other fields were present. A zero temperature was not observed; the sample was missing. Maintenance traced it to a dropped sensor bus. The missing values stayed out of silver until the bus reported again.
