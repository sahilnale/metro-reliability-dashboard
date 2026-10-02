from datetime import date, datetime, timedelta, timezone

from app.models import Observation, Route, Stop
from app.queries import (
    list_routes,
    nearby_stops,
    route_exists,
    route_reliability,
    route_reliability_by_hour,
    stop_delay_summary,
    stop_exists,
)
from worker.parse import local_datetime

NOW = datetime.now(timezone.utc)


def _seed_route_and_stop(session, route_id="51", stop_id="100"):
    session.add(Route(route_id=route_id, route_code=route_id, short_name=route_id, long_name="Test Route", mode="bus", agency_id="LACMTA"))
    session.add(Stop(stop_id=stop_id, name="Test Stop", lat=34.05, lon=-118.25, agency_id="LACMTA"))
    session.commit()


def _observation(route_id, stop_id, delay_seconds=None, canceled=False, observed_at=None, scheduled_time=None, trip_id="t1"):
    return Observation(
        route_id=route_id,
        stop_id=None if canceled else stop_id,
        trip_id=trip_id,
        scheduled_time=scheduled_time,
        predicted_time=(scheduled_time + timedelta(seconds=delay_seconds)) if (scheduled_time and delay_seconds is not None) else None,
        delay_seconds=delay_seconds,
        canceled=canceled,
        observed_at=observed_at or NOW,
    )


def test_route_exists_and_list_routes(session):
    _seed_route_and_stop(session, route_id="51")
    session.add(Route(route_id="2", route_code="2", short_name="2", long_name="Route 2", mode="bus", agency_id="LACMTA"))
    session.commit()

    assert route_exists(session, "51") is True
    assert route_exists(session, "999") is False

    routes = list_routes(session)
    assert {r["route_id"] for r in routes} == {"51", "2"}


def test_stop_exists(session):
    _seed_route_and_stop(session)
    assert stop_exists(session, "100") is True
    assert stop_exists(session, "999") is False


def test_route_reliability_computes_on_time_percentage_and_average_delay(session):
    _seed_route_and_stop(session)
    scheduled = NOW - timedelta(hours=1)

    delays = [-30, 0, 120, 400, -120]  # on-time: -30, 0, 120 (within -60..300); late: 400; too early: -120
    for i, d in enumerate(delays):
        session.add(_observation("51", "100", delay_seconds=d, scheduled_time=scheduled, trip_id=f"t{i}"))
    session.add(_observation("51", "100", canceled=True, trip_id="canceled-1"))
    session.commit()

    result = route_reliability(session, "51", days=7)

    assert result["total_observations"] == 6
    assert result["canceled_trips"] == 1
    assert result["on_time_percentage"] == 60.0  # 3 of 5 non-canceled
    assert result["average_delay_seconds"] == 74.0  # mean of the 5 delays


def test_route_reliability_handles_no_observations(session):
    _seed_route_and_stop(session)
    result = route_reliability(session, "51", days=7)

    assert result["total_observations"] == 0
    assert result["on_time_percentage"] is None
    assert result["average_delay_seconds"] is None


def test_route_reliability_excludes_observations_outside_window(session):
    _seed_route_and_stop(session)
    old = NOW - timedelta(days=30)
    session.add(_observation("51", "100", delay_seconds=0, scheduled_time=old, observed_at=old))
    session.commit()

    result = route_reliability(session, "51", days=7)
    assert result["total_observations"] == 0


def test_route_reliability_by_hour_groups_by_la_local_hour(session):
    _seed_route_and_stop(session)
    morning = local_datetime(date(2026, 10, 1), datetime.min.time().replace(hour=8))
    evening = local_datetime(date(2026, 10, 1), datetime.min.time().replace(hour=17))

    # Morning: 2 on-time. Evening: 1 late.
    session.add(_observation("51", "100", delay_seconds=10, scheduled_time=morning, trip_id="m1"))
    session.add(_observation("51", "100", delay_seconds=-20, scheduled_time=morning, trip_id="m2"))
    session.add(_observation("51", "100", delay_seconds=600, scheduled_time=evening, trip_id="e1"))
    session.commit()

    result = {row["hour"]: row for row in route_reliability_by_hour(session, "51", days=365)}

    assert result[8]["total_observations"] == 2
    assert result[8]["on_time_percentage"] == 100.0
    assert result[17]["total_observations"] == 1
    assert result[17]["on_time_percentage"] == 0.0


def test_stop_delay_summary_includes_recent_observations(session):
    _seed_route_and_stop(session)
    scheduled = NOW - timedelta(hours=1)
    session.add(_observation("51", "100", delay_seconds=30, scheduled_time=scheduled, trip_id="t1"))
    session.add(_observation("51", "100", delay_seconds=500, scheduled_time=scheduled, trip_id="t2"))
    session.commit()

    result = stop_delay_summary(session, "100", days=7)

    assert result["total_observations"] == 2
    assert result["on_time_percentage"] == 50.0
    assert len(result["recent_observations"]) == 2
    assert {o["trip_id"] for o in result["recent_observations"]} == {"t1", "t2"}


def test_nearby_stops_orders_by_distance(session):
    session.add(Stop(stop_id="near", name="Near Stop", lat=34.0501, lon=-118.2501, agency_id="LACMTA"))
    session.add(Stop(stop_id="far", name="Far Stop", lat=36.0, lon=-120.0, agency_id="LACMTA"))
    session.commit()

    results = nearby_stops(session, lat=34.05, lon=-118.25, limit=10)

    assert [r["stop_id"] for r in results] == ["near", "far"]
    assert results[0]["distance_km"] < results[1]["distance_km"]
