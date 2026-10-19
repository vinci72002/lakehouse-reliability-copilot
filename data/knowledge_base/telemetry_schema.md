# Aircraft telemetry

Bronze stores one row per sensor event. Units are part of the column name.

| Column | Type | Required in silver | Notes |
| --- | --- | --- | --- |
| `event_id` | string | yes, unique | Source event key |
| `aircraft_id` | string | yes | Airframe identifier, for example `AC-1000` |
| `flight_id` | string | yes | Null or blank fails `flight_id_not_null` |
| `event_time` | timestamp | yes | Time zone aware. Pipeline timestamps are UTC |
| `latitude` | degrees | yes | -90 to 90 |
| `longitude` | degrees | yes | -180 to 180 |
| `altitude_ft` | feet | yes | Valid range is -1,500 to 65,000 inclusive |
| `ground_speed_kts` | knots | yes | Not range-checked in Phase 1 |
| `vertical_speed_fpm` | feet per minute | yes | Not range-checked in Phase 1 |
| `engine_temp_c` | celsius | yes | Null fails `engine_temp_not_null`. Zero is allowed |
| `fuel_remaining_kg` | kilograms | yes | Must be greater than or equal to 0 |

Bronze accepts the faulty values so the original payload can be sampled on the incident. Silver and gold do not.

Fuel is stored as a floating-point measurement in this local batch. A production feed that needs exact mass should use a decimal type before it is aggregated.
