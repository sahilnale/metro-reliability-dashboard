"""Expires old observation rows so the DB doesn't grow forever.

Our API never queries further back than 90 days (every reliability/delay
endpoint caps `days` at 90 -- see app/main.py), so anything older than that
is dead weight. Matters in production: Neon's free tier caps out at 1GB,
and `observations` is the one table that grows continuously for as long as
ingestion keeps running (unlike scheduled_departures, which is cached once
per route and stays flat).
"""
import logging

from sqlalchemy import delete, text
from sqlalchemy.orm import Session

from app.models import Observation

logger = logging.getLogger(__name__)

RETENTION_DAYS = 90


def prune_old_observations(session: Session, days: int = RETENTION_DAYS) -> int:
    cutoff = text("now() - (interval '1 day' * :days)").bindparams(days=days)
    result = session.execute(delete(Observation).where(Observation.observed_at < cutoff))
    session.commit()
    if result.rowcount:
        logger.info("pruned %d observations older than %d days", result.rowcount, days)
    return result.rowcount
