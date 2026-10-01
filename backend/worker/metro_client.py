import requests

from app.config import settings

BUS_AGENCY = "LACMTA"
RAIL_AGENCY = "LACMTA_Rail"


def get_route_overview(agency_id: str) -> list[dict]:
    resp = requests.get(f"{settings.metro_api_base_url}/{agency_id}/route_overview", timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_route_stops(agency_id: str, route_code: str, day_type: str) -> list[dict]:
    """Per-stop schedule for a route on a given day type.

    Each item covers one stop and includes every departure_time scheduled
    at that stop that day -- not a per-trip scheduled time, which this API
    doesn't expose. See samples/FINDINGS.md for why we match on nearest
    time-of-day instead of an exact trip_id join.
    """
    url = f"{settings.metro_api_base_url}/{agency_id}/route_stops/{route_code}"
    resp = requests.get(url, params={"daytype": day_type}, timeout=15)
    resp.raise_for_status()
    return resp.json()
