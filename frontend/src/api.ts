import type {
  HourlyReliability,
  NearbyStop,
  RouteReliability,
  RouteSummary,
  StopDelaySummary,
} from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function getJson<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE_URL}${path}`);
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request to ${path} failed with ${resp.status}`);
  }
  return resp.json();
}

export function getRoutes(): Promise<RouteSummary[]> {
  return getJson("/routes");
}

export function getRouteReliability(routeId: string, days = 7): Promise<RouteReliability> {
  return getJson(`/routes/${encodeURIComponent(routeId)}/reliability?days=${days}`);
}

export function getRouteReliabilityByHour(routeId: string, days = 7): Promise<HourlyReliability[]> {
  return getJson(`/routes/${encodeURIComponent(routeId)}/by-hour?days=${days}`);
}

export function getNearbyStops(lat: number, lon: number, limit = 20): Promise<NearbyStop[]> {
  return getJson(`/stops?near=${lat},${lon}&limit=${limit}`);
}

export function getStopDelays(stopId: string, days = 7): Promise<StopDelaySummary> {
  return getJson(`/stops/${encodeURIComponent(stopId)}/delays?days=${days}`);
}
