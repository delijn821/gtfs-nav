from pydantic import BaseModel, Field
from typing import List, Optional, Literal

class LatLon(BaseModel):
    lat: float
    lon: float

ManeuverType = Literal[
    "start", "straight", "left", "right", "uturn",
    "merge", "exit", "roundabout", "arrive", "unknown"
]

class Maneuver(BaseModel):
    index: int
    type: ManeuverType
    distance_m: float = Field(..., description="Distance from previous maneuver (meters)")
    begin_shape_index: Optional[int] = None
    along_route_m: Optional[float] = Field(None, description="Distance from route start to maneuver start (meters)")
    instruction: str
    roundabout_exit: Optional[int] = None

class RouteResult(BaseModel):
    trip_id: str
    shape_id: str
    # This is the Valhalla matched route geometry (recommended for map + matching)
    route_geometry: List[LatLon]
    maneuvers: List[Maneuver]
    total_distance_m: float

class PrepareResult(BaseModel):
    trip_id: str
    shape_id: str
    route_points_count: int
    maneuvers_count: int
    total_distance_m: float

class MatchResult(BaseModel):
    gps: LatLon
    matched: dict
    off_route: bool
    next_maneuver: Optional[dict]
