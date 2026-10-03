from app.route_path import build_route_path


def _stop(direction_id, stop_sequence, lat, lon, stop_id=None):
    return {
        "direction_id": direction_id,
        "stop_sequence": stop_sequence,
        "stop_id": stop_id if stop_id is not None else f"s{stop_sequence}",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    }


def test_groups_by_direction_and_sorts_by_sequence():
    items = [
        _stop(0, 2, 34.05, -118.25),
        _stop(1, 1, 34.06, -118.26),
        _stop(0, 1, 34.04, -118.24),
        _stop(1, 2, 34.07, -118.27),
    ]

    result = build_route_path(items)

    assert [d["direction_id"] for d in result] == [0, 1]
    assert result[0]["coordinates"] == [[34.04, -118.24], [34.05, -118.25]]
    assert result[1]["coordinates"] == [[34.06, -118.26], [34.07, -118.27]]
    assert result[0]["stop_ids"] == ["s1", "s2"]


def test_dedupes_consecutive_identical_points():
    items = [
        _stop(0, 1, 34.04, -118.24),
        _stop(0, 2, 34.04, -118.24),
        _stop(0, 3, 34.05, -118.25),
    ]

    result = build_route_path(items)

    assert result[0]["coordinates"] == [[34.04, -118.24], [34.05, -118.25]]


def test_skips_malformed_records():
    items = [
        _stop(0, 1, 34.04, -118.24),
        {"direction_id": 0, "stop_sequence": 2},  # missing geometry
        _stop(0, 3, 34.05, -118.25),
    ]

    result = build_route_path(items)

    assert result[0]["coordinates"] == [[34.04, -118.24], [34.05, -118.25]]


def test_empty_input_returns_empty_list():
    assert build_route_path([]) == []
