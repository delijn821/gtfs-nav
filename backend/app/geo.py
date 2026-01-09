import math
from typing import List, Tuple, Dict, Any

def haversine_m(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    # a,b = (lat, lon)
    R = 6371000.0
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = (math.sin(dlat / 2) ** 2 +
         math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))

def downsample_by_distance(points: List[Tuple[float, float]], min_step_m: float = 15.0) -> List[Tuple[float, float]]:
    """
    Keep first point, then keep a point only if it's at least min_step_m away from last kept.
    Always keep last point.
    """
    if not points:
        return []
    if len(points) == 1:
        return points[:]
    kept = [points[0]]
    last = points[0]
    for p in points[1:-1]:
        if haversine_m(last, p) >= min_step_m:
            kept.append(p)
            last = p
    kept.append(points[-1])
    return kept

def _to_xy_m(lat0: float, lon0: float, lat: float, lon: float) -> Tuple[float, float]:
    """
    Equirectangular approximation: convert lat/lon to local meters around (lat0, lon0).
    Accurate enough for snapping on a route.
    """
    R = 6371000.0
    x = math.radians(lon - lon0) * R * math.cos(math.radians(lat0))
    y = math.radians(lat - lat0) * R
    return x, y

def _from_xy_m(lat0: float, lon0: float, x: float, y: float) -> Tuple[float, float]:
    R = 6371000.0
    lat = lat0 + math.degrees(y / R)
    lon = lon0 + math.degrees(x / (R * math.cos(math.radians(lat0))))
    return lat, lon

def build_cumdist_m(points_latlon: List[Tuple[float, float]]) -> List[float]:
    """
    cum[i] = meters from start to vertex i
    """
    if not points_latlon:
        return []
    cum = [0.0]
    for i in range(1, len(points_latlon)):
        cum.append(cum[-1] + haversine_m(points_latlon[i - 1], points_latlon[i]))
    return cum

def snap_point_to_polyline(
    points_latlon: List[Tuple[float, float]],
    cumdist_m: List[float],
    gps_lat: float,
    gps_lon: float
) -> Dict[str, Any]:
    """
    Project GPS point onto closest polyline segment.
    Returns matched point + along-route meters + cross-track meters.
    """
    if len(points_latlon) < 2:
        raise ValueError("Polyline needs at least 2 points")
    if len(cumdist_m) != len(points_latlon):
        raise ValueError("cumdist_m length mismatch")

    lat0, lon0 = gps_lat, gps_lon
    # GPS point is origin in local xy
    px, py = 0.0, 0.0

    best = {
        "cross_track_m": float("inf"),
        "segment_index": 0,
        "t": 0.0,
        "matched_lat": points_latlon[0][0],
        "matched_lon": points_latlon[0][1],
        "along_route_m": 0.0,
    }

    for i in range(len(points_latlon) - 1):
        a_lat, a_lon = points_latlon[i]
        b_lat, b_lon = points_latlon[i + 1]

        ax, ay = _to_xy_m(lat0, lon0, a_lat, a_lon)
        bx, by = _to_xy_m(lat0, lon0, b_lat, b_lon)

        vx, vy = (bx - ax), (by - ay)
        wx, wy = (px - ax), (py - ay)

        seg_len2 = vx * vx + vy * vy
        if seg_len2 <= 1e-9:
            continue

        t = (wx * vx + wy * vy) / seg_len2
        if t < 0.0:
            t_clamped = 0.0
        elif t > 1.0:
            t_clamped = 1.0
        else:
            t_clamped = t

        mx = ax + t_clamped * vx
        my = ay + t_clamped * vy

        d = math.hypot(px - mx, py - my)

        if d < best["cross_track_m"]:
            mlat, mlon = _from_xy_m(lat0, lon0, mx, my)

            seg_len_m = haversine_m((a_lat, a_lon), (b_lat, b_lon))
            along = cumdist_m[i] + t_clamped * seg_len_m

            best = {
                "cross_track_m": d,
                "segment_index": i,
                "t": t_clamped,
                "matched_lat": mlat,
                "matched_lon": mlon,
                "along_route_m": along,
            }

    return best

def find_next_maneuver_index(maneuvers: List[dict], along_route_m: float, tolerance_m: float = 7.0) -> int:
    """
    maneuvers must include 'along_route_m' (meters from route start).
    Returns index of the next maneuver at/after current position (with small tolerance).
    """
    if not maneuvers:
        return 0

    candidates = []
    for m in maneuvers:
        am = m.get("along_route_m")
        if am is None:
            continue
        if am >= (along_route_m - tolerance_m):
            candidates.append((am, m["index"]))

    if not candidates:
        # Past all maneuvers -> last one
        return maneuvers[-1]["index"]

    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]
