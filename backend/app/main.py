from fastapi import FastAPI, HTTPException, Query
from typing import Dict, Any, List, Tuple

from .config import settings
from .gtfs import load_trip_to_shape_id, load_shape_points
from .geo import (
    downsample_by_distance,
    build_cumdist_m,
    snap_point_to_polyline,
    find_next_maneuver_index
)
from .valhalla import trace_route, parse_trace_route
from .models import RouteResult, LatLon, Maneuver, PrepareResult

app = FastAPI(title="GTFS Shapes Navigation API", version="0.2.0")

# In-memory cache (MVP). Later: Redis/db.
ROUTE_CACHE: Dict[str, Dict[str, Any]] = {}

@app.get("/health")
def health():
    return {"ok": True}

def _ensure_gtfs_files():
    # Gives clear error early
    import os
    needed = ["trips.txt", "shapes.txt"]
    missing = []
    for f in needed:
        p = os.path.join(settings.gtfs_dir, f)
        if not os.path.exists(p):
            missing.append(p)
    if missing:
        raise HTTPException(status_code=500, detail=f"Missing GTFS files: {missing}")

def _prepare_trip_internal(trip_id: str, min_step_m: float, costing: str) -> Dict[str, Any]:
    _ensure_gtfs_files()

    trip_to_shape = load_trip_to_shape_id(settings.gtfs_dir)
    shape_id = trip_to_shape.get(trip_id)
    if not shape_id:
        raise HTTPException(status_code=404, detail=f"trip_id not found or has no shape_id: {trip_id}")

    pts = load_shape_points(settings.gtfs_dir, shape_id)
    if len(pts) < 2:
        raise HTTPException(status_code=400, detail=f"shape_id has insufficient points: {shape_id}")

    # Downsample GTFS shape points for Valhalla request
    pts_latlon: List[Tuple[float, float]] = [(p[0], p[1]) for p in pts]
    pts_ds = downsample_by_distance(pts_latlon, min_step_m=min_step_m)

    try:
        trace = trace_route(settings.valhalla_url, pts_ds, costing=costing)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Valhalla error: {e}")

    maneuvers, total_m, route_points = parse_trace_route(trace)
    if len(route_points) < 2:
        raise HTTPException(status_code=502, detail="Valhalla returned no usable route geometry")

    route_cum = build_cumdist_m(route_points)

    # Fill along_route_m for maneuvers using begin_shape_index on Valhalla geometry (correct & safe)
    for m in maneuvers:
        bsi = m.get("begin_shape_index")
        if bsi is None or bsi < 0 or bsi >= len(route_cum):
            m["along_route_m"] = None
        else:
            m["along_route_m"] = float(route_cum[bsi])

    data = {
        "trip_id": trip_id,
        "shape_id": shape_id,
        "route_points": route_points,   # list[(lat, lon)]
        "route_cum": route_cum,         # list[float] meters
        "maneuvers": maneuvers,         # list[dict]
        "total_distance_m": float(total_m),
    }
    ROUTE_CACHE[trip_id] = data
    return data

@app.get("/api/trips/{trip_id}/prepare", response_model=PrepareResult)
def prepare_trip(
    trip_id: str,
    min_step_m: float = Query(15.0, ge=5.0, le=50.0),
    costing: str = Query("auto")
):
    data = _prepare_trip_internal(trip_id, min_step_m=min_step_m, costing=costing)
    return PrepareResult(
        trip_id=trip_id,
        shape_id=data["shape_id"],
        route_points_count=len(data["route_points"]),
        maneuvers_count=len(data["maneuvers"]),
        total_distance_m=data["total_distance_m"]
    )

@app.get("/api/trips/{trip_id}/route_geometry")
def route_geometry(trip_id: str):
    data = ROUTE_CACHE.get(trip_id)
    if not data:
        raise HTTPException(status_code=400, detail="Trip not prepared. Call /prepare first.")
    return {
        "trip_id": trip_id,
        "shape_id": data["shape_id"],
        "route_geometry": [{"lat": lat, "lon": lon} for (lat, lon) in data["route_points"]],
        "total_distance_m": data["total_distance_m"]
    }

@app.get("/api/trips/{trip_id}/match")
def match_position(
    trip_id: str,
    lat: float = Query(...),
    lon: float = Query(...),
    offroute_threshold_m: float = Query(40.0, ge=5.0, le=200.0)
):
    data = ROUTE_CACHE.get(trip_id)
    if not data:
        raise HTTPException(status_code=400, detail="Trip not prepared. Call /prepare first.")

    route_points = data["route_points"]
    route_cum = data["route_cum"]
    maneuvers = data["maneuvers"]

    snap = snap_point_to_polyline(route_points, route_cum, lat, lon)
    along = float(snap["along_route_m"])
    cross = float(snap["cross_track_m"])

    next_idx = find_next_maneuver_index(maneuvers, along_route_m=along, tolerance_m=7.0)
    next_man = next((m for m in maneuvers if m["index"] == next_idx), None)

    if next_man and next_man.get("along_route_m") is not None:
        dist_to_next = float(next_man["along_route_m"]) - along
        if dist_to_next < 0:
            dist_to_next = 0.0
    else:
        dist_to_next = None

    return {
        "gps": {"lat": lat, "lon": lon},
        "matched": {
            "lat": snap["matched_lat"],
            "lon": snap["matched_lon"],
            "cross_track_m": cross,
            "along_route_m": along,
            "segment_index": snap["segment_index"],
            "t": snap["t"]
        },
        "off_route": (cross > offroute_threshold_m),
        "next_maneuver": {
            "index": next_man["index"],
            "type": next_man["type"],
            "roundabout_exit": next_man.get("roundabout_exit"),
            "distance_to_maneuver_m": dist_to_next,
            "along_route_m": next_man.get("along_route_m"),
        } if next_man else None
    }

@app.get("/api/trips/{trip_id}/route", response_model=RouteResult)
def route_full(
    trip_id: str,
    min_step_m: float = Query(15.0, ge=5.0, le=50.0),
    costing: str = Query("auto")
):
    """
    Debug-friendly endpoint: prepares trip and returns geometry + maneuvers in one call.
    Also caches it.
    """
    data = _prepare_trip_internal(trip_id, min_step_m=min_step_m, costing=costing)

    maneuvers = [Maneuver(**m) for m in data["maneuvers"]]
    route_geometry = [LatLon(lat=lat, lon=lon) for (lat, lon) in data["route_points"]]

    return RouteResult(
        trip_id=trip_id,
        shape_id=data["shape_id"],
        route_geometry=route_geometry,
        maneuvers=maneuvers,
        total_distance_m=data["total_distance_m"]
    )
