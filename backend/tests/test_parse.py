from datetime import date, datetime, time, timezone

from worker.parse import (
    compute_delay_seconds,
    day_type_for_date,
    epoch_to_utc,
    extract_route_code,
    local_datetime,
    nearest_time,
    normalize_gtfs_time,
    parse_trip_update,
)

# Real messages captured from wss://api.metro.net/ws/LACMTA/trip_updates and
# .../LACMTA_Rail/trip_updates (see samples/bus_trip_updates.json,
# samples/rail_trip_updates.json).
REAL_CANCELED_BUS = {
    "id": "70004003641428-JUNE26",
    "tripUpdate": {
        "trip": {
            "tripId": "70004003641428-JUNE26",
            "startTime": "14:28:00",
            "startDate": "20261004",
            "scheduleRelationship": "CANCELED",
            "routeId": "4-13201",
            "directionId": 0,
        },
        "timestamp": "1791158277",
    },
    "route_code": "",
}

REAL_NORMAL_BUS = {
    "id": "70115005591447-JUNE26_6080_53220",
    "tripUpdate": {
        "trip": {
            "tripId": "70115005591447-JUNE26",
            "startTime": "14:47:00",
            "startDate": "20261004",
            "scheduleRelationship": "SCHEDULED",
            "routeId": "115-13201",
            "directionId": 1,
        },
        "stopTimeUpdate": [
            {
                "stopSequence": 101,
                "arrival": {"time": "1791158289"},
                "stopId": "2330",
                "scheduleRelationship": "SCHEDULED",
            }
        ],
        "vehicle": {"id": "6080"},
        "timestamp": "1791158267",
    },
    "route_code": "",
}

REAL_NORMAL_RAIL = {
    "id": "64155257_1162-1179_52920",
    "tripUpdate": {
        "trip": {
            "tripId": "64155257",
            "startTime": "14:42:00",
            "startDate": "20261004",
            "scheduleRelationship": "SCHEDULED",
            "routeId": "801",
            "directionId": 0,
        },
        "stopTimeUpdate": [
            {
                "stopSequence": 46,
                "arrival": {"time": "1791158337"},
                "stopId": "801103",
                "scheduleRelationship": "SCHEDULED",
            }
        ],
        "vehicle": {"id": "1162-1179"},
        "timestamp": "1791158290",
    },
    "route_code": "",
}


def test_extract_route_code_strips_gtfs_suffix():
    assert extract_route_code("51-13201") == "51"


def test_extract_route_code_passes_through_rail_id():
    assert extract_route_code("801") == "801"


def test_day_type_for_date():
    assert day_type_for_date(date(2026, 10, 5)) == "weekday"  # Monday
    assert day_type_for_date(date(2026, 10, 10)) == "saturday"
    assert day_type_for_date(date(2026, 10, 11)) == "sunday"


def test_normalize_gtfs_time_past_midnight():
    assert normalize_gtfs_time("25:10:00") == time(1, 10, 0)


def test_normalize_gtfs_time_normal():
    assert normalize_gtfs_time("06:05:00") == time(6, 5, 0)


def test_nearest_time_picks_closest():
    candidates = [time(6, 0, 0), time(6, 15, 0), time(7, 0, 0)]
    assert nearest_time(time(6, 10, 0), candidates) == time(6, 15, 0)


def test_nearest_time_wraps_around_midnight():
    candidates = [time(23, 55, 0), time(12, 0, 0)]
    assert nearest_time(time(0, 2, 0), candidates) == time(23, 55, 0)


def test_nearest_time_empty_candidates():
    assert nearest_time(time(6, 0, 0), []) is None


def test_parse_trip_update_cancellation():
    results = parse_trip_update(REAL_CANCELED_BUS)
    assert len(results) == 1
    r = results[0]
    assert r.canceled is True
    assert r.trip_id == "70004003641428-JUNE26"
    assert r.route_code == "4"
    assert r.stop_id is None
    assert r.predicted_time is None
    assert r.day_type == "sunday"  # 2026-10-04 is a Sunday


def test_parse_trip_update_normal_bus_stop():
    results = parse_trip_update(REAL_NORMAL_BUS)
    assert len(results) == 1
    r = results[0]
    assert r.canceled is False
    assert r.route_code == "115"
    assert r.stop_id == "2330"
    assert r.predicted_time == epoch_to_utc("1791158289")


def test_parse_trip_update_normal_rail_stop():
    results = parse_trip_update(REAL_NORMAL_RAIL)
    assert len(results) == 1
    r = results[0]
    assert r.route_code == "801"
    assert r.stop_id == "801103"


def test_parse_trip_update_multiple_stop_time_updates():
    message = {
        "tripUpdate": {
            "trip": {
                "tripId": "t1",
                "routeId": "2-13172",
                "startDate": "20261005",
                "scheduleRelationship": "SCHEDULED",
            },
            "stopTimeUpdate": [
                {"stopId": "100", "arrival": {"time": "1791158000"}},
                {"stopId": "200", "departure": {"time": "1791158100"}},
            ],
        }
    }
    results = parse_trip_update(message)
    assert len(results) == 2
    assert results[0].stop_id == "100"
    assert results[1].stop_id == "200"
    assert results[1].predicted_time == epoch_to_utc("1791158100")


def test_parse_trip_update_missing_trip_update_key():
    assert parse_trip_update({"id": "x"}) == []


def test_parse_trip_update_missing_required_trip_fields():
    message = {"tripUpdate": {"trip": {"tripId": "t1"}}}  # no routeId/startDate
    assert parse_trip_update(message) == []


def test_parse_trip_update_skips_stop_update_missing_stop_id():
    message = {
        "tripUpdate": {
            "trip": {
                "tripId": "t1",
                "routeId": "2-13172",
                "startDate": "20261005",
                "scheduleRelationship": "SCHEDULED",
            },
            "stopTimeUpdate": [{"arrival": {"time": "1791158000"}}],
        }
    }
    assert parse_trip_update(message) == []


def test_parse_trip_update_skips_stop_update_missing_time():
    message = {
        "tripUpdate": {
            "trip": {
                "tripId": "t1",
                "routeId": "2-13172",
                "startDate": "20261005",
                "scheduleRelationship": "SCHEDULED",
            },
            "stopTimeUpdate": [{"stopId": "100"}],
        }
    }
    assert parse_trip_update(message) == []


def test_compute_delay_seconds_late():
    scheduled = datetime(2026, 10, 4, 12, 0, 0, tzinfo=timezone.utc)
    predicted = datetime(2026, 10, 4, 12, 5, 0, tzinfo=timezone.utc)
    assert compute_delay_seconds(scheduled, predicted) == 300


def test_compute_delay_seconds_early():
    scheduled = datetime(2026, 10, 4, 12, 0, 0, tzinfo=timezone.utc)
    predicted = datetime(2026, 10, 4, 11, 59, 0, tzinfo=timezone.utc)
    assert compute_delay_seconds(scheduled, predicted) == -60


def test_local_datetime_is_la_timezone_aware():
    dt = local_datetime(date(2026, 10, 4), time(14, 42, 0))
    assert dt.tzinfo is not None
    assert dt.utcoffset() is not None
