import type {
  HourlyReliability,
  NearbyStop,
  RouteDirectionPath,
  RouteReliability,
  RouteSummary,
  StopDelaySummary,
} from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

// Render's free tier spins the API down after 15 min idle. The first
// request back can come back as an outright network failure or a 502/503
// while it's still booting (can take up to ~a minute), not just slow --
// without a retry here, a single request landing in that window left
// whatever it was loading permanently stuck on an error even after the
// backend finished waking up a few seconds later.
const MAX_RETRIES = 6;
const RETRY_DELAY_MS = 5000;

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isRetryable(status: number | null): boolean {
  // null = fetch() itself threw (DNS/connection failure) -- also transient
  // during a cold start. 502/503 are what Render/Cloudflare return while
  // the service is still booting. Anything else (404, 422, ...) is a real
  // application error -- retrying just delays a correct error message.
  return status === null || status === 502 || status === 503;
}

async function getJson<T>(path: string): Promise<T> {
  let lastError: Error = new Error("Request failed");

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    let resp: Response;
    try {
      resp = await fetch(`${BASE_URL}${path}`);
    } catch (err) {
      lastError = err as Error;
      if (attempt < MAX_RETRIES) {
        await sleep(RETRY_DELAY_MS);
        continue;
      }
      throw lastError;
    }

    if (resp.ok) return resp.json();

    if (!isRetryable(resp.status) || attempt === MAX_RETRIES) {
      const body = await resp.json().catch(() => ({}));
      throw new Error(body.detail ?? `Request to ${path} failed with ${resp.status}`);
    }

    await sleep(RETRY_DELAY_MS);
  }

  throw lastError;
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

export function getRoutePath(routeId: string): Promise<RouteDirectionPath[]> {
  return getJson(`/routes/${encodeURIComponent(routeId)}/path`);
}

export function getNearbyStops(lat: number, lon: number, limit = 20): Promise<NearbyStop[]> {
  return getJson(`/stops?near=${lat},${lon}&limit=${limit}`);
}

export function getStopDelays(stopId: string, days = 7): Promise<StopDelaySummary> {
  return getJson(`/stops/${encodeURIComponent(stopId)}/delays?days=${days}`);
}
