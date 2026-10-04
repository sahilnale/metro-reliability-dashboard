"""Eagerly loads the full bus schedule for every route into Postgres.

Not used by the deployed app -- the streaming worker caches each route's
schedule on demand instead (see worker/schedule_cache.py), so a deployment
never pays to store schedule data it doesn't end up using. This script is
useful for local dev when you want full coverage immediately instead of
waiting for live traffic to populate the cache route by route.

Scoped to bus only: Metro's route_stops endpoint -- our only source of
scheduled departure times -- returns real data for every bus route we've
tried, but comes back empty for every rail line (checked rail route_code
values 1-6 and 801-807; see samples/FINDINGS.md). Rail support is future
work once we find a working schedule source for it.

Run: python -m worker.static_loader
"""
import logging
import time as time_module

from app.db import get_session
from worker.schedule_cache import ensure_routes_cached, ensure_schedule_cached

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DAY_TYPES = ["weekday", "saturday", "sunday"]
REQUEST_DELAY_SECONDS = 0.2  # be polite: ~hundreds of routes x 3 day types


def main() -> None:
    session = get_session()
    try:
        route_ids = sorted(ensure_routes_cached(session))
        logger.info("loaded %d bus routes", len(route_ids))

        for i, route_code in enumerate(route_ids, start=1):
            for day_type in DAY_TYPES:
                ensure_schedule_cached(session, route_code, day_type)
                time_module.sleep(REQUEST_DELAY_SECONDS)
            logger.info("loaded schedule for route %s (%d/%d)", route_code, i, len(route_ids))

        logger.info("loaded schedule data for %d routes", len(route_ids))
    finally:
        session.close()


if __name__ == "__main__":
    main()
