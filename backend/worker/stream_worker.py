"""Streaming ingestion worker.

Holds an open WebSocket connection to Metro's trip_updates feed (bus only)
and upserts delay/cancellation observations into Postgres as messages
arrive. Reconnects with exponential backoff if the connection drops, and
skips any single malformed message rather than crashing the whole process.

Route metadata loads eagerly on connect (cheap, ~120 rows). Each route's
schedule is cached lazily the first time we see it in live traffic -- see
worker/schedule_cache.py -- so this never requires a slow pre-load step.

Run: python -m worker.stream_worker
"""
import asyncio
import json
import logging
from datetime import datetime, timezone

import websockets
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.models import Observation, ScheduledDeparture
from worker.metro_client import BUS_AGENCY
from worker.parse import (
    ParsedStopUpdate,
    compute_delay_seconds,
    nearest_scheduled_datetime,
    parse_trip_update,
)
from worker.schedule_cache import ensure_routes_cached, ensure_schedule_cached

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MAX_BACKOFF_SECONDS = 60


def _scheduled_candidates(session: Session, route_id: str, stop_id: str, day_type: str) -> list:
    rows = session.execute(
        select(ScheduledDeparture.departure_time).where(
            ScheduledDeparture.route_id == route_id,
            ScheduledDeparture.stop_id == stop_id,
            ScheduledDeparture.day_type == day_type,
        )
    )
    return [row[0] for row in rows]


def _upsert_cancellation(session: Session, trip_id: str, route_id: str, observed_at: datetime) -> None:
    # stop_id is NULL for cancellations, and Postgres treats NULLs as
    # distinct for unique constraints -- ON CONFLICT would never match
    # a repeat cancellation message, so we dedupe by hand instead.
    existing_id = session.execute(
        select(Observation.id).where(
            Observation.trip_id == trip_id, Observation.stop_id.is_(None)
        )
    ).scalar_one_or_none()

    if existing_id is not None:
        session.execute(
            update(Observation)
            .where(Observation.id == existing_id)
            .values(canceled=True, observed_at=observed_at)
        )
    else:
        session.add(
            Observation(route_id=route_id, stop_id=None, trip_id=trip_id, canceled=True, observed_at=observed_at)
        )


def _upsert_stop_observation(session: Session, update: ParsedStopUpdate, observed_at: datetime) -> bool:
    ensure_schedule_cached(session, update.route_code, update.day_type)
    candidates = _scheduled_candidates(session, update.route_code, update.stop_id, update.day_type)
    scheduled_dt = nearest_scheduled_datetime(update.predicted_time, update.service_date, candidates)
    if scheduled_dt is None:
        return False

    delay = compute_delay_seconds(scheduled_dt, update.predicted_time)

    stmt = (
        pg_insert(Observation)
        .values(
            route_id=update.route_code,
            stop_id=update.stop_id,
            trip_id=update.trip_id,
            scheduled_time=scheduled_dt,
            predicted_time=update.predicted_time,
            delay_seconds=delay,
            canceled=False,
            observed_at=observed_at,
        )
        .on_conflict_do_update(
            constraint="uq_observation_trip_stop",
            set_=dict(
                scheduled_time=scheduled_dt,
                predicted_time=update.predicted_time,
                delay_seconds=delay,
                observed_at=observed_at,
            ),
        )
    )
    session.execute(stmt)
    return True


def handle_message(session: Session, known_route_ids: set[str], raw: str) -> None:
    try:
        message = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("skipping non-JSON message")
        return

    for update in parse_trip_update(message):
        if update.route_code not in known_route_ids:
            continue  # not a bus route we loaded static data for

        observed_at = datetime.now(timezone.utc)
        if update.canceled:
            _upsert_cancellation(session, update.trip_id, update.route_code, observed_at)
            continue

        _upsert_stop_observation(session, update, observed_at)

    session.commit()


async def consume_forever() -> None:
    url = f"{settings.metro_ws_base_url}/ws/{BUS_AGENCY}/trip_updates"
    backoff = 1

    while True:
        try:
            async with websockets.connect(url, open_timeout=10) as ws:
                logger.info("connected to %s", url)
                backoff = 1

                session = get_session()
                try:
                    known_route_ids = ensure_routes_cached(session)
                    logger.info("tracking %d bus routes", len(known_route_ids))

                    async for raw in ws:
                        try:
                            handle_message(session, known_route_ids, raw)
                        except Exception:
                            logger.exception("failed to handle message, skipping")
                            session.rollback()
                finally:
                    session.close()
        except (websockets.exceptions.WebSocketException, OSError, asyncio.TimeoutError) as exc:
            logger.warning("websocket connection dropped (%s); reconnecting in %ss", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)


if __name__ == "__main__":
    asyncio.run(consume_forever())
