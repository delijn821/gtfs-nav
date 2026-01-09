from pydantic import BaseModel
import os

class Settings(BaseModel):
    valhalla_url: str = os.getenv("VALHALLA_URL", "http://localhost:8002")
    gtfs_dir: str = os.getenv("GTFS_DIR", "/data/gtfs")

settings = Settings()
