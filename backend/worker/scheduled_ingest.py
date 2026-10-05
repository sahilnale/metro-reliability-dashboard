"""Short-burst ingestion, meant to be run on a schedule (GitHub Actions).

worker/stream_worker.py holds a WebSocket connection open forever, which
is the right model for local dev but doesn't fit any free hosting tier --
nobody gives away a free always-on background worker (Render's free tier
is request-driven web services only; background workers start at $7/mo).

GitHub Actions, on the other hand, is free and unmetered for public repos.
So in production this script runs instead: connect to Metro's trip_updates
feed for a bounded window, upsert whatever arrives, exit. A workflow
(.github/workflows/ingest.yml) re-runs it every few minutes. Data is less
dense than a continuous connection would produce, but costs nothing.

RUN_DURATION_SECONDS is a *target*, not a hard guarantee: Metro's feed
sometimes delivers a huge burst (observed 10k+ messages in ~10s) rather
than a steady trickle, and under that kind of load asyncio's cooperative
cancellation can't always preempt promptly -- a flood of ready callbacks
can delay even a timeout-based cancellation, and a currently-running
synchronous call (a DB commit, a requests.get) can't be interrupted
mid-flight at all. We still aim for ~90s internally, but the workflow's
`timeout-minutes` is what actually guarantees this can't run away --
treat that as the authoritative cutoff, not this script's own logic.

Run: python -m worker.scheduled_ingest
"""
import asyncio
import logging
import time

import websockets

from app.config import settings
from app.db import get_session
from worker.metro_client import BUS_AGENCY
from worker.retention import prune_old_observations
from worker.schedule_cache import ensure_routes_cached
from worker.stream_worker import handle_message
from worker import schedule_cache

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

RUN_DURATION_SECONDS = 90
MESSAGE_TIMEOUT_SECONDS = 5
# Stop making *new* live schedule fetches once this much of the budget is
# spent, leaving the rest for processing messages against what's already
# cached. Without this, a fresh DB hitting many cache-misses in a row can
# chain enough blocking HTTP calls to blow well past RUN_DURATION_SECONDS
# before the loop ever gets a chance to check the clock again.
NEW_FETCH_CUTOFF_FRACTION = 0.6


async def _consume(session, known_route_ids: set[str]) -> int:
    url = f"{settings.metro_ws_base_url}/ws/{BUS_AGENCY}/trip_updates"
    message_count = 0

    async with websockets.connect(url, open_timeout=10) as ws:
        logger.info("connected to %s", url)
        end = asyncio.get_event_loop().time() + RUN_DURATION_SECONDS

        while asyncio.get_event_loop().time() < end:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=MESSAGE_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                continue
            try:
                handle_message(session, known_route_ids, raw)
                message_count += 1
            except Exception:
                logger.exception("failed to handle message, skipping")
                session.rollback()

    return message_count


async def run_once() -> None:
    session = get_session()
    message_count = 0
    schedule_cache.fetch_deadline = time.monotonic() + RUN_DURATION_SECONDS * NEW_FETCH_CUTOFF_FRACTION

    try:
        known_route_ids = ensure_routes_cached(session)
        logger.info("tracking %d bus routes", len(known_route_ids))

        # Belt-and-suspenders hard deadline: guarantees termination close to
        # budget even if something inside _consume ends up blocking longer
        # than expected, regardless of root cause.
        message_count = await asyncio.wait_for(
            _consume(session, known_route_ids), timeout=RUN_DURATION_SECONDS + 30
        )
    except asyncio.TimeoutError:
        logger.warning("hit the hard deadline, stopping")
    except (websockets.exceptions.WebSocketException, OSError) as exc:
        # Not fatal -- the next scheduled run picks up a few minutes later.
        logger.warning("connection issue during this burst: %s", exc)
    finally:
        schedule_cache.fetch_deadline = None
        try:
            pruned = prune_old_observations(session)
        except Exception:
            logger.exception("retention cleanup failed, skipping this run")
            pruned = 0
        session.close()
        logger.info("processed %d messages, pruned %d old observations this run", message_count, pruned)


if __name__ == "__main__":
    asyncio.run(run_once())
