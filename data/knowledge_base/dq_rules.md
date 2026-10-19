# Data-quality rules

Run these checks on `bronze.aircraft_telemetry` before building gold. A row enters `silver.aircraft_telemetry` only when every rule passes.

## event_id_unique

Severity: high.

`event_id` must occur once in the batch. Every copy is quarantined, including the first. Phase 1 does not choose a survivor, because two copies can disagree.

```sql
SELECT event_id, COUNT(*) AS duplicate_count
FROM bronze.aircraft_telemetry
GROUP BY event_id
HAVING COUNT(*) > 1
```

## flight_id_not_null

Severity: high.

`flight_id` must be present. Null and blank strings both fail. Gold groups by aircraft and flight, so a missing flight id cannot be aggregated safely.

```sql
SELECT *
FROM bronze.aircraft_telemetry
WHERE flight_id IS NULL OR TRIM(flight_id) = ''
```

## fuel_non_negative

Severity: critical.

`fuel_remaining_kg` below 0 is physically impossible and usually means a sensor or a unit error. Zero is valid.

```sql
SELECT *
FROM bronze.aircraft_telemetry
WHERE fuel_remaining_kg < 0
```

## altitude_in_range

Severity: medium.

`altitude_ft` must be between -1,500 and 65,000 inclusive. The lower bound allows operations below sea level. The upper bound is above the transport-category envelope, so a larger value is treated as a bad reading.

```sql
SELECT *
FROM bronze.aircraft_telemetry
WHERE altitude_ft < -1500 OR altitude_ft > 65000
```

## engine_temp_not_null

Severity: medium.

`engine_temp_c` must be present. The rule does not impose a temperature range in Phase 1. A value of 0 is a reported temperature, not a missing one.

```sql
SELECT *
FROM bronze.aircraft_telemetry
WHERE engine_temp_c IS NULL
```

Each failed rule opens one incident. The incident sample is not the full failed set; use `failed_record_count` and the SQL above for the full population.
