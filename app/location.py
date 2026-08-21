from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_M = 6371000.0


def haversine_metres(latitude_a, longitude_a, latitude_b, longitude_b):
    delta_lat = radians(latitude_b - latitude_a)
    delta_lon = radians(longitude_b - longitude_a)
    half_chord_squared = (
        sin(delta_lat / 2) ** 2
        + cos(radians(latitude_a)) * cos(radians(latitude_b)) * sin(delta_lon / 2) ** 2
    )
    # Clamp so float rounding can never push asin's argument past 1.
    return 2 * EARTH_RADIUS_M * asin(sqrt(min(1.0, half_chord_squared)))
