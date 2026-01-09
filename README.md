# GTFS-Nav (GTFS shape -> Valhalla maneuvers -> live matching)

## Vereisten
- Docker + Docker Compose (aanrader), of Python 3.11+
- Een werkende Valhalla instance (zelf gehost of extern)

## GTFS plaatsen
Zet je GTFS data uitgepakt in:
`gtfs-nav/gtfs/`

Minimaal nodig:
- trips.txt
- shapes.txt
Optioneel (later):
- routes.txt, stop_times.txt, calendar.txt, calendar_dates.txt

## Config
De backend leest:
- GTFS_DIR (default: /data/gtfs)
- VALHALLA_URL (default: http://localhost:8002)

## Starten met Docker
In repo root:
```bash
docker compose up --build
