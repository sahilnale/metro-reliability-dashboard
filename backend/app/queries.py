"""SQL aggregations behind the reliability endpoints.

Kept as plain functions over a Session (no FastAPI/request objects) so they
can be unit tested against a small seeded database -- see tests/test_queries.py.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Observation, Route, Stop


def _on_time_case():
    """True if a non-canceled observation falls inside the on-time window."""
    return case(
        (
            (~Observation.canceled)
            & (Observation.delay_seconds >= -settings.on_time_early_seconds)
            & (Observation.delay_seconds <= settings.on_time_late_seconds),
            True,
        ),
        else_=False,
    )


def _cutoff(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def list_routes(session: Session) -> list[dict]:
    rows = session.execute(
        select(Route.route_id, Route.short_name, Route.long_name).order_by(Route.route_id)
    ).all()
    return [dict(route_id=r.route_id, short_name=r.short_name, long_name=r.long_name) for r in rows]


def route_exists(session: Session, route_id: str) -> bool:
    return session.execute(select(Route.route_id).where(Route.route_id == route_id)).first() is not None


def stop_exists(session: Session, stop_id: str) -> bool:
    return session.execute(select(Stop.stop_id).where(Stop.stop_id == stop_id)).first() is not None


def route_reliability(session: Session, route_id: str, days: int) -> dict:
    on_time = _on_time_case()
    row = session.execute(
        select(
            func.count().label("total"),
            func.coalesce(func.sum(case((Observation.canceled, 1), else_=0)), 0).label("canceled"),
            func.coalesce(func.sum(case((on_time, 1), else_=0)), 0).label("on_time"),
            func.avg(Observation.delay_seconds).label("avg_delay"),
        ).where(Observation.route_id == route_id, Observation.observed_at >= _cutoff(days))
    ).one()

    non_canceled = row.total - row.canceled
    return {
        "route_id": route_id,
        "days": days,
        "total_observations": row.total,
        "canceled_trips": row.canceled,
        "on_time_percentage": round(row.on_time / non_canceled * 100, 1) if non_canceled else None,
        "average_delay_seconds": round(float(row.avg_delay), 1) if row.avg_delay is not None else None,
    }


def route_reliability_by_hour(session: Session, route_id: str, days: int) -> list[dict]:
    hour = func.extract("hour", func.timezone("America/Los_Angeles", Observation.scheduled_time))
    on_time = _on_time_case()

    rows = session.execute(
        select(
            hour.label("hour"),
            func.count().label("total"),
            func.coalesce(func.sum(case((on_time, 1), else_=0)), 0).label("on_time"),
            func.avg(Observation.delay_seconds).label("avg_delay"),
        )
        .where(
            Observation.route_id == route_id,
            Observation.observed_at >= _cutoff(days),
            ~Observation.canceled,
        )
        .group_by(hour)
        .order_by(hour)
    ).all()

    return [
        {
            "hour": int(r.hour),
            "total_observations": r.total,
            "on_time_percentage": round(r.on_time / r.total * 100, 1) if r.total else None,
            "average_delay_seconds": round(float(r.avg_delay), 1) if r.avg_delay is not None else None,
        }
        for r in rows
    ]


def stop_delay_summary(session: Session, stop_id: str, days: int) -> dict:
    on_time = _on_time_case()
    cutoff = _cutoff(days)

    summary = session.execute(
        select(
            func.count().label("total"),
            func.coalesce(func.sum(case((Observation.canceled, 1), else_=0)), 0).label("canceled"),
            func.coalesce(func.sum(case((on_time, 1), else_=0)), 0).label("on_time"),
            func.avg(Observation.delay_seconds).label("avg_delay"),
        ).where(Observation.stop_id == stop_id, Observation.observed_at >= cutoff)
    ).one()

    recent_rows = session.execute(
        select(
            Observation.route_id,
            Observation.trip_id,
            Observation.scheduled_time,
            Observation.predicted_time,
            Observation.delay_seconds,
            Observation.canceled,
        )
        .where(Observation.stop_id == stop_id, Observation.observed_at >= cutoff)
        .order_by(Observation.observed_at.desc())
        .limit(20)
    ).all()

    non_canceled = summary.total - summary.canceled
    return {
        "stop_id": stop_id,
        "days": days,
        "total_observations": summary.total,
        "canceled_trips": summary.canceled,
        "on_time_percentage": round(summary.on_time / non_canceled * 100, 1) if non_canceled else None,
        "average_delay_seconds": round(float(summary.avg_delay), 1) if summary.avg_delay is not None else None,
        "recent_observations": [
            {
                "route_id": r.route_id,
                "trip_id": r.trip_id,
                "scheduled_time": r.scheduled_time,
                "predicted_time": r.predicted_time,
                "delay_seconds": r.delay_seconds,
                "canceled": r.canceled,
            }
            for r in recent_rows
        ],
    }


def nearby_stops(session: Session, lat: float, lon: float, limit: int = 10) -> list[dict]:
    # Haversine distance in km. Clamp the acos() argument to [-1, 1] --
    # floating-point rounding can push it slightly past 1 for a point
    # right on top of a stop, which would otherwise raise a domain error.
    cos_angle = func.cos(func.radians(lat)) * func.cos(func.radians(Stop.lat)) * func.cos(
        func.radians(Stop.lon) - func.radians(lon)
    ) + func.sin(func.radians(lat)) * func.sin(func.radians(Stop.lat))
    clamped = func.greatest(-1.0, func.least(1.0, cos_angle))
    distance_km = 6371 * func.acos(clamped)

    rows = session.execute(
        select(Stop.stop_id, Stop.name, Stop.lat, Stop.lon, distance_km.label("distance_km"))
        .order_by(distance_km)
        .limit(limit)
    ).all()

    return [
        {
            "stop_id": r.stop_id,
            "name": r.name,
            "lat": r.lat,
            "lon": r.lon,
            "distance_km": round(float(r.distance_km), 3),
        }
        for r in rows
    ]
