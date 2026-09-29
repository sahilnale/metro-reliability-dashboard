# Phase 1 findings: the real Metro API

Explored with `samples/explore_api.py`. No API key is required for any GET
endpoint or WebSocket feed used below — confirmed by hitting them directly.

## Base URL and docs

- REST base: `https://api.metro.net` (FastAPI service, interactive docs at
  `/docs`, OpenAPI spec at `/openapi.json` — saved in `samples/openapi.json`)
- WebSocket base: `wss://api.metro.net/ws/{agency_id}/{feed}[/{route_codes}]`
- `agency_id` is one of `LACMTA` (bus) or `LACMTA_Rail` (rail)
- `route_codes` is an optional comma-separated filter (e.g. `/720,51`)

## Real-time data: WebSocket, not polling

The docs mention a REST `trip_detail` endpoint, but it returned `[]` for every
route we tried. The actual live real-time feed is the WebSocket endpoint —
confirmed receiving live messages for both `vehicle_positions` and
`trip_updates` on both agencies. This changes the ingestion design from
"poll every ~60s" to "hold an open WebSocket connection and consume a stream,
with reconnect/backoff on drop."

### `vehicle_positions` feed

One message per vehicle, every few seconds. Example (bus):

```json
{
  "id": "5817",
  "vehicle": {
    "trip": {
      "tripId": "70051003711642-JUNE26",
      "startTime": "16:42:00",
      "startDate": "20261004",
      "scheduleRelationship": "SCHEDULED",
      "routeId": "51-13201",
      "directionId": 0
    },
    "position": { "latitude": 33.870842, "longitude": -118.26603, "bearing": 360.0, "speed": 2.68224 },
    "currentStopSequence": 8,
    "currentStatus": "IN_TRANSIT_TO",
    "timestamp": "1791158009",
    "stopId": "204",
    "vehicle": { "id": "5817", "label": "5817" }
  },
  "route_code": "51"
}
```

Gives vehicle location and which stop it's currently heading to/stopped at,
but **no scheduled time and no delay** — not directly usable for reliability
math on its own.

### `trip_updates` feed

One message per trip update. This is where delay data lives:

```json
{
  "id": "64155257_1162-1179_52920",
  "tripUpdate": {
    "trip": {
      "tripId": "64155257",
      "startTime": "14:42:00",
      "startDate": "20261004",
      "scheduleRelationship": "SCHEDULED",
      "routeId": "801",
      "directionId": 0
    },
    "stopTimeUpdate": [
      { "stopSequence": 46, "arrival": { "time": "1791158162" }, "stopId": "801103", "scheduleRelationship": "SCHEDULED" }
    ],
    "vehicle": { "id": "1162-1179" },
    "timestamp": "1791158115"
  },
  "route_code": ""
}
```

`arrival.time` / `departure.time` are **predicted** Unix timestamps for a
specific stop on a specific trip — exactly what we need to compare against
the *scheduled* time for that trip/stop from static GTFS data.

Coverage in a 30-message sample from each agency:
- Rail: 30/30 messages carried a `stopTimeUpdate` with a predicted time.
- Bus: 24/30 carried a `stopTimeUpdate`; the other 6 were trip
  **cancellations** (`trip.scheduleRelationship: "CANCELED"`, no stop times).

So bus trip_updates double as both our delay source and our cancellation
source.

## Static data: REST, works as documented

`GET /{agency_id}/route_overview` returns real route metadata (short/long
name, color, terminals, PDF schedule links). Example fields: `route_id`,
`route_code`, `route_short_name`, `route_long_name`, `route_type`
(`bus`/`rail`), `agency_id`, `is_active`.

We'll also need `/{agency_id}/stop_times/route_code/{route_code}` (scheduled
stop times — the "scheduled" half of our delay calculation) and
`/{agency_id}/stops/{stop_id}` (stop lat/lon/name) — both documented in the
OpenAPI spec and structurally plain GTFS, not yet sampled with live data; to
pull in Phase 2 once we're writing the ingestion worker against them directly.

## Other endpoints noted, not used

- `/canceled_service_summary`, `/canceled_service/line/{line}` — bus-only
  cancellation counts by route. `canceled_service/all` 500'd when tried;
  `trip_updates` cancellations (above) cover this more precisely anyway (per
  trip, not just a count), so we don't plan to depend on this endpoint.
- `/login`, `/token`, `/users/` — a user-account system on this API, unrelated
  to transit data. Not needed for this project.

## Decision: how we'll compute delay

Match on `(trip_id, stop_id)`:
1. **Scheduled time** comes from static GTFS `stop_times` (loaded once,
   refreshed weekly per the docs' "weekly calendar_dates.txt" note).
2. **Predicted/actual time** comes from the `trip_updates` WebSocket feed's
   `stopTimeUpdate[].arrival.time` (fall back to `departure.time` if arrival
   is absent).
3. `delay_seconds = predicted_time - scheduled_time`.
4. A `trip_updates` message with `scheduleRelationship: CANCELED` and no
   `stopTimeUpdate` records a cancellation instead of a delay.

This confirms the `observations` table shape in the project README is right:
one row per `(route_id, stop_id, trip_id, scheduled_time, predicted_time,
delay_seconds, observed_at)`, fed by a long-lived WebSocket consumer rather
than a periodic poller.
