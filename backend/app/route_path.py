"""Builds a drawable path for a route from Metro's route_stops data.

Fetched live (not from our DB) because our ingested scheduled_departures
table never captured direction_id -- without it, stop_sequence numbers from
both directions are interleaved and sorting by sequence alone zigzags
between opposite-direction stops. The raw API response does include
direction_id, so we group by it here instead of re-ingesting.
"""


def build_route_path(items: list[dict]) -> list[dict]:
    by_direction: dict[int, list[tuple[int, str, float, float]]] = {}

    for item in items:
        try:
            direction_id = int(item["direction_id"])
            stop_sequence = int(item["stop_sequence"])
            stop_id = str(item["stop_id"])
            lon, lat = item["geometry"]["coordinates"]
        except (KeyError, TypeError, ValueError):
            continue
        by_direction.setdefault(direction_id, []).append((stop_sequence, stop_id, float(lat), float(lon)))

    result = []
    for direction_id, points in sorted(by_direction.items()):
        points.sort(key=lambda p: p[0])
        coordinates: list[list[float]] = []
        stop_ids: list[str] = []
        for _, stop_id, lat, lon in points:
            if coordinates and coordinates[-1] == [lat, lon]:
                continue
            coordinates.append([lat, lon])
            stop_ids.append(stop_id)
        result.append({"direction_id": direction_id, "coordinates": coordinates, "stop_ids": stop_ids})

    return result
