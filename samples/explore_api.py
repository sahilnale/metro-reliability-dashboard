"""
Phase 1 exploration script for the LA Metro public API (api.metro.net).

Hits the real REST endpoints and the real-time WebSocket feeds and saves
sample responses to samples/*.json so we can design the data model against
real data instead of guessing at the docs.

Usage: python3 samples/explore_api.py
"""
import asyncio
import json
from pathlib import Path

import requests
import websockets

BASE = "https://api.metro.net"
BASE_WS = "wss://api.metro.net"
SAMPLES_DIR = Path(__file__).parent


def save_rest_samples() -> None:
    endpoints = {
        "route_overview_bus.json": f"{BASE}/LACMTA/route_overview",
        "route_overview_rail.json": f"{BASE}/LACMTA_Rail/route_overview",
        "canceled_service_summary.json": f"{BASE}/canceled_service_summary",
    }
    for filename, url in endpoints.items():
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        (SAMPLES_DIR / filename).write_text(json.dumps(resp.json(), indent=2))
        print(f"saved {filename} ({len(resp.content)} bytes)")


async def save_ws_samples(agency_id: str, feed: str, filename: str, seconds: int) -> None:
    url = f"{BASE_WS}/ws/{agency_id}/{feed}"
    messages = []
    async with websockets.connect(url, open_timeout=10) as ws:
        loop = asyncio.get_event_loop()
        end = loop.time() + seconds
        while loop.time() < end and len(messages) < 30:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
                messages.append(json.loads(raw))
            except asyncio.TimeoutError:
                continue
    (SAMPLES_DIR / filename).write_text(json.dumps(messages, indent=2))
    print(f"saved {filename} ({len(messages)} messages)")


async def main() -> None:
    save_rest_samples()
    await save_ws_samples("LACMTA", "vehicle_positions", "bus_vehicle_positions.json", 15)
    await save_ws_samples("LACMTA_Rail", "vehicle_positions", "rail_vehicle_positions.json", 15)
    await save_ws_samples("LACMTA", "trip_updates", "bus_trip_updates.json", 30)
    await save_ws_samples("LACMTA_Rail", "trip_updates", "rail_trip_updates.json", 30)


if __name__ == "__main__":
    asyncio.run(main())
