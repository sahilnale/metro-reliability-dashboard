"""Fetches and caches a route's schedule from Metro, on demand.

Earlier this project pre-loaded the full weekday/saturday/sunday schedule
for all 120 bus routes up front (worker/static_loader.py) -- about 4M rows,
773MB. That's fine for local dev, but it's more than fits in a free-tier
Postgres plan (Neon's free tier is 1GB/project) and takes ~11 minutes to
run before the app has any data at all.

Instead, ensure_schedule_cached() fetches and stores a single route's
schedule for a single day type the first time it's actually needed --
i.e. the first time we see that (route, day_type) combination in live
traffic -- and is a no-op on every call after that. A deployment never
pays for schedule data it doesn't end up using.
"""
import ast
import logging
import time

import requests
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import Route, ScheduledDeparture, Stop
from worker.metro_client import BUS_AGENCY, get_route_overview, get_route_stops
from worker.parse import normalize_gtfs_time

logger = logging.getLogger(__name__)


def ensure_routes_cached(session: Session) -> set[str]:
    """Upserts route metadata (~120 rows, one API call) and returns the set
    of known route_ids. Cheap enough to just do eagerly on every worker
    run -- it's schedule *times* data that's expensive, not this."""
    overview = get_route_overview(BUS_AGENCY)
    routes = [r for r in overview if r.get("is_active") and r.get("route_type") == "bus"]

    for r in routes:
        route_code = str(r["route_code"])
        stmt = (
            pg_insert(Route)
            .values(
                route_id=route_code,
                route_code=route_code,
                short_name=r.get("route_short_name"),
                long_name=r.get("route_long_name"),
                mode="bus",
                agency_id=BUS_AGENCY,
                color=r.get("route_color"),
            )
            .on_conflict_do_update(
                index_elements=["route_id"],
                set_=dict(
                    short_name=r.get("route_short_name"),
                    long_name=r.get("route_long_name"),
                    color=r.get("route_color"),
                ),
            )
        )
        session.execute(stmt)
    session.commit()

    return {str(r["route_code"]) for r in routes}


def _bulk_upsert_stops(session: Session, stop_rows: list[dict]) -> None:
    if not stop_rows:
        return
    # Dedupe by stop_id within this batch -- ON CONFLICT can't target the
    # same row twice in one statement ("cannot affect row a second time").
    by_stop_id = {row["stop_id"]: row for row in stop_rows}
    stmt = pg_insert(Stop).values(list(by_stop_id.values()))
    stmt = stmt.on_conflict_do_update(
        index_elements=["stop_id"],
        set_=dict(name=stmt.excluded.name, lat=stmt.excluded.lat, lon=stmt.excluded.lon),
    )
    session.execute(stmt)


def _bulk_upsert_scheduled_departures(session: Session, departure_rows: list[dict]) -> None:
    if not departure_rows:
        return
    # Dedupe within the batch for the same reason as stops above.
    seen = set()
    unique_rows = []
    for row in departure_rows:
        key = (row["route_id"], row["stop_id"], row["day_type"], row["departure_time"])
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)

    stmt = pg_insert(ScheduledDeparture).values(unique_rows)
    stmt = stmt.on_conflict_do_nothing(constraint="uq_scheduled_departure")
    session.execute(stmt)


def rows_for_route_stops(route_code: str, day_type: str, items: list[dict]) -> tuple[list[dict], list[dict]]:
    stop_rows = []
    departure_rows = []
    for item in items:
        try:
            stop_id = str(item["stop_id"])
            lon, lat = item["geometry"]["coordinates"]
            stop_sequence = item["stop_sequence"]
            # API returns this as a Python-repr string, e.g. "['03:32:00', ...]".
            raw_times = ast.literal_eval(item["departure_times"])
        except (KeyError, ValueError, SyntaxError) as exc:
            logger.warning("skipping bad route_stops record for route %s: %s", route_code, exc)
            continue

        stop_rows.append(dict(stop_id=stop_id, name=item["stop_name"], lat=lat, lon=lon, agency_id=BUS_AGENCY))
        for raw in raw_times:
            departure_rows.append(
                dict(
                    route_id=route_code,
                    stop_id=stop_id,
                    day_type=day_type,
                    stop_sequence=stop_sequence,
                    departure_time=normalize_gtfs_time(raw),
                )
            )
    return stop_rows, departure_rows


def is_schedule_cached(session: Session, route_code: str, day_type: str) -> bool:
    return (
        session.execute(
            select(ScheduledDeparture.id)
            .where(ScheduledDeparture.route_id == route_code, ScheduledDeparture.day_type == day_type)
            .limit(1)
        ).first()
        is not None
    )


# A handful of routes (e.g. "93") have no schedule in Metro's route_stops
# data at all -- route_stops returns zero rows for them, so the DB check
# above never finds anything cached and would otherwise re-fetch from the
# live API on every single message for that route. Tracked in-memory and
# per-process (not in the DB) since "empty" isn't really cacheable data,
# just a fact worth not re-querying for during this run.
_attempted_this_process: set[tuple[str, str]] = set()


#: Optional wall-clock deadline (a `time.monotonic()`-style value) past
#: which ensure_schedule_cached() stops making *new* live fetches. Each
#: fetch is a blocking `requests` call -- fine when there's no deadline
#: (the continuous stream_worker), but a bounded burst run (scheduled_ingest)
#: needs a hard cap, since a fresh DB can hit dozens of cache-misses in a
#: row and blocking calls can't be preempted by a wall-clock check between
#: messages. Cache *hits* (the common case after the first run or two)
#: are an indexed DB lookup and stay unaffected regardless of the deadline.
fetch_deadline: float | None = None


def ensure_schedule_cached(session: Session, route_code: str, day_type: str) -> None:
    key = (route_code, day_type)
    if key in _attempted_this_process:
        return
    if is_schedule_cached(session, route_code, day_type):
        _attempted_this_process.add(key)
        return

    if fetch_deadline is not None and time.monotonic() > fetch_deadline:
        return  # out of budget this run; a later run will pick it up

    _attempted_this_process.add(key)
    try:
        items = get_route_stops(BUS_AGENCY, route_code, day_type)
    except requests.RequestException as exc:
        logger.warning("route_stops fetch failed for route %s/%s: %s", route_code, day_type, exc)
        return

    stop_rows, departure_rows = rows_for_route_stops(route_code, day_type, items)
    _bulk_upsert_stops(session, stop_rows)
    _bulk_upsert_scheduled_departures(session, departure_rows)
    session.commit()
    logger.info("cached schedule for route %s/%s (%d stops)", route_code, day_type, len(stop_rows))
