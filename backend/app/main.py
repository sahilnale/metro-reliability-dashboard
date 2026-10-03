import requests
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app import queries
from app.config import settings
from app.db import get_session
from app.route_path import build_route_path
from app.schemas import (
    HourlyReliability,
    NearbyStop,
    RouteDirectionPath,
    RouteReliability,
    RouteSummary,
    StopDelaySummary,
)
from worker.metro_client import BUS_AGENCY, get_route_stops

app = FastAPI(
    title="Metro Reliability Dashboard API",
    description="How on-time LA Metro bus routes have been, computed from real-time data.",
)

# The frontend (Vite dev server, later a Vercel domain) runs on a different
# origin than this API, so without this the browser blocks every request.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def get_db():
    session = get_session()
    try:
        yield session
    finally:
        session.close()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/routes", response_model=list[RouteSummary])
def get_routes(db: Session = Depends(get_db)):
    return queries.list_routes(db)


@app.get("/routes/{route_id}/reliability", response_model=RouteReliability)
def get_route_reliability(
    route_id: str,
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
):
    if not queries.route_exists(db, route_id):
        raise HTTPException(status_code=404, detail=f"Unknown route_id '{route_id}'")
    return queries.route_reliability(db, route_id, days)


@app.get("/routes/{route_id}/by-hour", response_model=list[HourlyReliability])
def get_route_reliability_by_hour(
    route_id: str,
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
):
    if not queries.route_exists(db, route_id):
        raise HTTPException(status_code=404, detail=f"Unknown route_id '{route_id}'")
    return queries.route_reliability_by_hour(db, route_id, days)


@app.get("/routes/{route_id}/path", response_model=list[RouteDirectionPath])
def get_route_path(route_id: str, db: Session = Depends(get_db)):
    if not queries.route_exists(db, route_id):
        raise HTTPException(status_code=404, detail=f"Unknown route_id '{route_id}'")
    try:
        items = get_route_stops(BUS_AGENCY, route_id, "weekday")
    except requests.RequestException:
        raise HTTPException(status_code=502, detail="Metro API is unavailable right now")
    return build_route_path(items)


@app.get("/stops", response_model=list[NearbyStop])
def get_nearby_stops(
    near: str = Query(..., description="lat,lon"),
    limit: int = Query(10, ge=1, le=300),
    db: Session = Depends(get_db),
):
    try:
        lat_str, lon_str = near.split(",")
        lat, lon = float(lat_str), float(lon_str)
    except ValueError:
        raise HTTPException(status_code=422, detail="near must be formatted as 'lat,lon'")

    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        raise HTTPException(status_code=422, detail="lat must be in [-90, 90] and lon in [-180, 180]")

    return queries.nearby_stops(db, lat, lon, limit)


@app.get("/stops/{stop_id}/delays", response_model=StopDelaySummary)
def get_stop_delays(
    stop_id: str,
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
):
    if not queries.stop_exists(db, stop_id):
        raise HTTPException(status_code=404, detail=f"Unknown stop_id '{stop_id}'")
    return queries.stop_delay_summary(db, stop_id, days)
