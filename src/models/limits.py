"""Physical bounds enforced by the telemetry data contract.

These are data-quality limits, not an aircraft-performance model.
Altitude allows operations slightly below sea level and rejects values
above the transport-category envelope. Fuel mass cannot be negative.
"""

ALTITUDE_MIN_FT = -1_500.0
ALTITUDE_MAX_FT = 65_000.0
FUEL_MIN_KG = 0.0

LATITUDE_MIN_DEG = -90.0
LATITUDE_MAX_DEG = 90.0
LONGITUDE_MIN_DEG = -180.0
LONGITUDE_MAX_DEG = 180.0
