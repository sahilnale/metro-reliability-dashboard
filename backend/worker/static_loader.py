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


def _rows_for_route_stops(route_code: str, day_type: str, items: list[dict]) -> tuple[list[dict], list[dict]]:
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


def load_stops_and_schedule(session: Session, routes: list[dict]) -> None:
    total_routes_loaded = 0
    for r in routes:
        route_code = str(r["route_code"])
        for day_type in DAY_TYPES:
            try:
                items = get_route_stops(BUS_AGENCY, route_code, day_type)
            except requests.RequestException as exc:
                logger.warning("route_stops failed for route %s/%s: %s", route_code, day_type, exc)
                continue

            stop_rows, departure_rows = _rows_for_route_stops(route_code, day_type, items)
            _bulk_upsert_stops(session, stop_rows)
            _bulk_upsert_scheduled_departures(session, departure_rows)
            session.commit()
            time_module.sleep(REQUEST_DELAY_SECONDS)

        total_routes_loaded += 1
        logger.info("loaded schedule for route %s (%d/%d)", route_code, total_routes_loaded, len(routes))

    logger.info("loaded schedule data for %d routes", total_routes_loaded)


def main() -> None:
    session = get_session()
    try:
        routes = load_routes(session)
        load_stops_and_schedule(session, routes)
    finally:
        session.close()


if __name__ == "__main__":
    main()
