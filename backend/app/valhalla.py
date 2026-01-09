from typing import List, Tuple, Dict, Any
import requests
import polyline

def trace_route(valhalla_url: str, points: List[Tuple[float, float]], costing: str = "auto") -> Dict[str, Any]:
    """
    Calls Valhalla /trace_route with shape points.
    points: list of (lat, lon)
    """
    shape = [{"lat": lat, "lon": lon} for lat, lon in points]
    payload = {
        "shape": shape,
        "costing": costing,
        "shape_match": "map_snap",
        "narrative": True,
        "directions_options": {"units": "kilometers"}
    }
    url = valhalla_url.rstrip("/") + "/trace_route"
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()

def _map_valhalla_type(m: Dict[str, Any]) -> str:
    """
    We map by instruction keywords to keep it stable across Valhalla versions.
    You will later ignore instruction and use your own NL texts for UI/audio.
    """
    instr = (m.get("instruction") or "").lower()

    if "roundabout" in instr or "rotonde" in instr:
        return "roundabout"
    if "arrive" in instr or "bestemming" in instr:
        return "arrive"
    if "u-turn" in instr or "keer om" in instr:
        return "uturn"
    if "left" in instr or "links" in instr:
        return "left"
    if "right" in instr or "rechts" in instr:
        return "right"
    if "merge" in instr or "voeg" in instr:
        return "merge"
    if "exit" in instr or "afrit" in instr:
        return "exit"
    if "start" in instr:
        return "start"
    if "straight" in instr or "rechtdoor" in instr:
        return "straight"
    return "unknown"

def parse_trace_route(trace_json: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], float, List[Tuple[float, float]]]:
    """
    Returns (maneuvers, total_distance_m, route_points)

    route_points is Valhalla's matched route geometry decoded from legs[].shape.
    Maneuver begin_shape_index refers to that route geometry -> consistent and safe.
    """
    trip = trace_json.get("trip", {})
    legs = trip.get("legs", [])

    maneuvers_out: List[Dict[str, Any]] = []
    total_km = 0.0

    # Matched geometry
    route_points: List[Tuple[float, float]] = []
    for leg in legs:
        enc = leg.get("shape")
        if enc:
            route_points.extend(polyline.decode(enc))

    idx = 0
    for leg in legs:
        total_km += float(leg.get("summary", {}).get("length", 0.0))
        mans = leg.get("maneuvers", [])
        for m in mans:
            dist_m = float(m.get("length", 0.0)) * 1000.0
            begin_shape_index = m.get("begin_shape_index")
            instr = m.get("instruction") or ""
            rr_exit = m.get("roundabout_exit_count")

            maneuvers_out.append({
                "index": idx,
                "type": _map_valhalla_type(m),
                "distance_m": dist_m,
                "begin_shape_index": int(begin_shape_index) if begin_shape_index is not None else None,
                "along_route_m": None,  # filled later
                "instruction": instr,
                "roundabout_exit": int(rr_exit) if rr_exit is not None else None,
            })
            idx += 1

    return maneuvers_out, total_km * 1000.0, route_points
