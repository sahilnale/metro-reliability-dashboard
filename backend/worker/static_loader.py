"""Loads static bus route/stop/schedule data into Postgres.

Run on its own (python -m worker.static_loader), not from the streaming
worker -- this data only needs a refresh roughly as often as Metro updates
its schedules (the API docs mention a weekly calendar_dates.txt update), not
on every worker restart.

Scoped to bus only: Metro's route_stops endpoint -- our only source of
scheduled departure times -- returns real data for every bus route we've
tried, but comes back empty for every rail line (checked rail route_code
values 1-6 and 801-807; see samples/FINDINGS.md). Rail support is future
work once we find a working schedule source for it.
"""
import ast
import logging
import time as time_module

import requests
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Route, ScheduledDeparture, Stop
from worker.metro_client import BUS_AGENCY, get_route_overview, get_route_stops
from worker.parse import normalize_gtfs_time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DAY_TYPES = ["weekday", "saturday", "sunday"]
REQUEST_DELAY_SECONDS = 0.2  # be polite: ~hundreds of routes x 3 day types


def load_routes(session: Session) -> list[dict]:
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
    logger.info("loaded %d bus routes", len(routes))
    return routes


def _upsert_stop(session: Session, item: dict) -> None:
    stop_id = str(item["stop_id"])
    lon, lat = item["geometry"]["coordinates"]
    stmt = (
        pg_insert(Stop)
        .values(stop_id=stop_id, name=item["stop_name"], lat=lat, lon=lon, agency_id=BUS_AGENCY)
        .on_conflict_do_update(
            index_elements=["stop_id"],
            set_=dict(name=item["stop_name"], lat=lat, lon=lon),
        )
    )
    session.execute(stmt)


def _upsert_scheduled_departures(
    session: Session, route_code: str, day_type: str, item: dict
) -> None:
    stop_id = str(item["stop_id"])
    stop_sequence = item["stop_sequence"]
    # API returns this as a Python-repr string, e.g. "['03:32:00', ...]".
    raw_times = ast.literal_eval(item["departure_times"])
    seen = set()
    for raw in raw_times:
        t = normalize_gtfs_time(raw)
        if t in seen:
            continue
        seen.add(t)
        stmt = (
            pg_insert(ScheduledDeparture)
            .values(
                route_id=route_code,
                stop_id=stop_id,
                day_type=day_type,
                stop_sequence=stop_sequence,
                departure_time=t,
            )
            .on_conflict_do_nothing(constraint="uq_scheduled_departure")
        )
        session.execute(stmt)


def load_stops_and_schedule(session: Session, routes: list[dict]) -> None:
    total_stops = 0
    for r in routes:
        route_code = str(r["route_code"])
        for day_type in DAY_TYPES:
            try:
                stops = get_route_stops(BUS_AGENCY, route_code, day_type)
            except requests.RequestException as exc:
                logger.warning("route_stops failed for route %s/%s: %s", route_code, day_type, exc)
                continue

            for item in stops:
                try:
                    _upsert_stop(session, item)
                    _upsert_scheduled_departures(session, route_code, day_type, item)
                    total_stops += 1
                except (KeyError, ValueError, SyntaxError) as exc:
                    logger.warning("skipping bad route_stops record for route %s: %s", route_code, exc)

            session.commit()
            time_module.sleep(REQUEST_DELAY_SECONDS)

    logger.info("loaded schedule data from %d route/stop records", total_stops)


def main() -> None:
    session = get_session()
    try:
        routes = load_routes(session)
        load_stops_and_schedule(session, routes)
    finally:
        session.close()


if __name__ == "__main__":
    main()
