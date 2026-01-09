import csv
import os
from typing import Dict, List, Tuple

def _read_csv(path: str) -> List[dict]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing GTFS file: {path}")
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def load_trip_to_shape_id(gtfs_dir: str) -> Dict[str, str]:
    trips_path = os.path.join(gtfs_dir, "trips.txt")
    rows = _read_csv(trips_path)
    out: Dict[str, str] = {}
    for r in rows:
        trip_id = r.get("trip_id")
        shape_id = r.get("shape_id")
        if trip_id and shape_id:
            out[trip_id] = shape_id
    return out

def load_shape_points(gtfs_dir: str, shape_id: str) -> List[Tuple[float, float, int]]:
    """
    Returns list of (lat, lon, seq) ordered by shape_pt_sequence.
    """
    shapes_path = os.path.join(gtfs_dir, "shapes.txt")
    rows = _read_csv(shapes_path)

    pts: List[Tuple[float, float, int]] = []
    for r in rows:
        if r.get("shape_id") != shape_id:
            continue
        lat = float(r["shape_pt_lat"])
        lon = float(r["shape_pt_lon"])
        seq = int(r["shape_pt_sequence"])
        pts.append((lat, lon, seq))

    pts.sort(key=lambda x: x[2])
    return pts
