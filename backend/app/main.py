from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy.orm import Session

from app import queries
from app.db import get_session
from app.schemas import (
    HourlyReliability,
    NearbyStop,
    RouteReliability,
    RouteSummary,
    StopDelaySummary,
)

app = FastAPI(
    title="Metro Reliability Dashboard API",
    description="How on-time LA Metro bus routes have been, computed from real-time data.",
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


@app.get("/stops", response_model=list[NearbyStop])
def get_nearby_stops(
    near: str = Query(..., description="lat,lon"),
    limit: int = Query(10, ge=1, le=50),
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
