from datetime import datetime, timedelta, timezone

from app.models import Observation, Route, Stop
from worker.retention import prune_old_observations

NOW = datetime.now(timezone.utc)


def _seed_route_and_stop(session):
    session.add(Route(route_id="51", route_code="51", short_name="51", long_name="Test Route", mode="bus", agency_id="LACMTA"))
    session.add(Stop(stop_id="100", name="Test Stop", lat=34.05, lon=-118.25, agency_id="LACMTA"))
    session.commit()


def _observation(trip_id, observed_at):
    return Observation(
        route_id="51",
        stop_id="100",
        trip_id=trip_id,
        delay_seconds=0,
        canceled=False,
        observed_at=observed_at,
    )


def test_prune_removes_only_rows_older_than_cutoff(session):
    _seed_route_and_stop(session)
    session.add(_observation("old", NOW - timedelta(days=91)))
    session.add(_observation("recent", NOW - timedelta(days=1)))
    session.commit()

    deleted = prune_old_observations(session, days=90)

    assert deleted == 1
    remaining = {o.trip_id for o in session.query(Observation).all()}
    assert remaining == {"recent"}


def test_prune_is_noop_when_nothing_is_old_enough(session):
    _seed_route_and_stop(session)
    session.add(_observation("recent", NOW - timedelta(days=1)))
    session.commit()

    deleted = prune_old_observations(session, days=90)

    assert deleted == 0
    assert session.query(Observation).count() == 1
