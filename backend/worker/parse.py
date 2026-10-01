"""Pure parsing/matching logic for the trip_updates WebSocket feed.

Kept free of any DB or network I/O so it can be unit tested directly against
real sample messages (see samples/FINDINGS.md and tests/test_parse.py).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

# GTFS stop_times are local wall-clock times for the agency, not UTC.
LOCAL_TZ = ZoneInfo("America/Los_Angeles")


@dataclass
class ParsedStopUpdate:
    trip_id: str
    route_code: str
    stop_id: str | None
    predicted_time: datetime | None  # UTC-aware; None when canceled
    canceled: bool
    day_type: str
    service_date: date


def extract_route_code(route_id: str) -> str:
    """Metro's GTFS routeId looks like "51-13201"; route_overview/route_stops
    key off the plain route_code ("51") before the dash. Rail route ids
    (e.g. "801") have no dash and pass through unchanged."""
    return route_id.split("-")[0]


def day_type_for_date(d: date) -> str:
    if d.weekday() == 5:
        return "saturday"
    if d.weekday() == 6:
        return "sunday"
    return "weekday"


def normalize_gtfs_time(raw: str) -> time:
    """GTFS allows hour >= 24 to mean "still the same service day, past
    midnight" (e.g. "25:10:00" for 1:10am). We store wall-clock time, which
    is what a real-time prediction's local time will actually match."""
    hh, mm, ss = (int(p) for p in raw.split(":"))
    return time(hour=hh % 24, minute=mm, second=ss)


def nearest_time(target: time, candidates: list[time]) -> time | None:
    """Nearest candidate to target by circular distance on a 24h clock.

    route_stops gives us every scheduled departure at a stop for a whole
    service day, not one keyed to a specific trip_id, so we match a live
    prediction to the closest scheduled clock time instead of an exact
    trip-level join (the API doesn't expose one -- see FINDINGS.md).
    """
    if not candidates:
        return None

    def seconds(t: time) -> int:
        return t.hour * 3600 + t.minute * 60 + t.second

    target_s = seconds(target)

    def distance(t: time) -> int:
        diff = abs(seconds(t) - target_s)
        return min(diff, 86400 - diff)

    return min(candidates, key=distance)


def epoch_to_utc(ts: str | int) -> datetime:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc)


def local_datetime(service_date: date, t: time) -> datetime:
    """Combine a GTFS service date and a local wall-clock time into a
    timezone-aware datetime, comparable to a predicted time (a UTC epoch)."""
    return datetime.combine(service_date, t, tzinfo=LOCAL_TZ)


def parse_trip_update(message: dict) -> list[ParsedStopUpdate]:
    """Parse one trip_updates WebSocket message into zero or more stop
    updates (zero for malformed messages, one for a cancellation, one per
    stop_time_update otherwise). Never raises -- bad input is skipped so one
    malformed message can't take down the ingestion loop.
    """
    trip_update = message.get("tripUpdate")
    if not isinstance(trip_update, dict):
        return []

    trip = trip_update.get("trip") or {}
    trip_id = trip.get("tripId")
    route_id = trip.get("routeId")
    start_date = trip.get("startDate")
    if not trip_id or not route_id or not start_date:
        return []

    try:
        service_date = datetime.strptime(start_date, "%Y%m%d").date()
    except ValueError:
        return []

    route_code = extract_route_code(route_id)
    day_type = day_type_for_date(service_date)

    if trip.get("scheduleRelationship") == "CANCELED":
        return [
            ParsedStopUpdate(
                trip_id=trip_id,
                route_code=route_code,
                stop_id=None,
                predicted_time=None,
                canceled=True,
                day_type=day_type,
                service_date=service_date,
            )
        ]

    results: list[ParsedStopUpdate] = []
    for stu in trip_update.get("stopTimeUpdate") or []:
        if not isinstance(stu, dict):
            continue
        stop_id = stu.get("stopId")
        arrival = stu.get("arrival") or {}
        departure = stu.get("departure") or {}
        ts = arrival.get("time") or departure.get("time")
        if not stop_id or not ts:
            continue
        try:
            predicted_time = epoch_to_utc(ts)
        except (TypeError, ValueError):
            continue
        results.append(
            ParsedStopUpdate(
                trip_id=trip_id,
                route_code=route_code,
                stop_id=str(stop_id),
                predicted_time=predicted_time,
                canceled=False,
                day_type=day_type,
                service_date=service_date,
            )
        )
    return results


def compute_delay_seconds(scheduled: datetime, predicted: datetime) -> int:
    return int((predicted - scheduled).total_seconds())
