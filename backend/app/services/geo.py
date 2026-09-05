import json
import math


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def point_in_polygon(lat: float, lon: float, points: list[list[float]]) -> bool:
    """Ray casting. points is a list of [lat, lon]."""
    inside = False
    n = len(points)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        yi, xi = points[i]
        yj, xj = points[j]
        if ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi
        ):
            inside = not inside
        j = i
    return inside


def is_inside(geometry_json: str, shape: str, lat: float, lon: float) -> bool:
    geom = json.loads(geometry_json)
    if shape == "circle":
        d = haversine_m(lat, lon, geom["lat"], geom["lon"])
        return d <= geom["radius_m"]
    if shape == "polygon":
        return point_in_polygon(lat, lon, geom["points"])
    return False
