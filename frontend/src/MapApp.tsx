import { useEffect, useMemo, useState } from "react";
import { CircleMarker, MapContainer, Polyline, TileLayer } from "react-leaflet";
import { getRoutePath, getRoutes } from "./api";
import FitBounds from "./components/FitBounds";
import FlyTo from "./components/FlyTo";
import RoutePanel from "./components/RoutePanel";
import SearchBar from "./components/SearchBar";
import StopPanel from "./components/StopPanel";
import ViewportStopLoader from "./components/ViewportStopLoader";
import ZoomTracker from "./components/ZoomTracker";
import type { NearbyStop, RouteDirectionPath, RouteSummary } from "./types";

const DIRECTION_COLORS = ["#4f46e5", "#f59e0b"];
const DEFAULT_STOP_COLOR = "#0d9488";
const SELECTED_STOP_COLOR = "#f59e0b";
const INITIAL_ZOOM = 14;
// Below this zoom, the whole-city stop cloud is just visual noise -- only
// show individual stops once you've zoomed in far enough to pick a street,
// except while a route is selected (then its own stops stay visible).
const MIN_STOP_ZOOM = 14;

const LA_CENTER: [number, number] = [34.0407, -118.2468];

type Selection =
  | { type: "none" }
  | { type: "route"; routeId: string }
  | { type: "stop"; stopId: string; stopName: string };

export default function MapApp() {
  const [routes, setRoutes] = useState<RouteSummary[]>([]);
  const [stops, setStops] = useState<NearbyStop[]>([]);
  const [search, setSearch] = useState("");
  const [selection, setSelection] = useState<Selection>({ type: "none" });
  const [hoveredStopId, setHoveredStopId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [routePath, setRoutePath] = useState<RouteDirectionPath[]>([]);
  const [zoom, setZoom] = useState(INITIAL_ZOOM);

  useEffect(() => {
    getRoutes()
      .then(setRoutes)
      .catch((err) => setLoadError(err.message));
  }, []);

  useEffect(() => {
    if (selection.type !== "route") {
      setRoutePath([]);
      return;
    }
    getRoutePath(selection.routeId)
      .then(setRoutePath)
      .catch(() => setRoutePath([]));
  }, [selection]);

  // Memoized so this only gets a new reference when routePath itself
  // changes (a different route gets selected) -- not on every unrelated
  // re-render (e.g. panning the map merges newly-loaded stops into state,
  // which would otherwise recreate this array and make FitBounds re-fire
  // flyToBounds, snapping the view back to the route every time you pan).
  const pathBounds: [number, number][] = useMemo(
    () => routePath.flatMap((d) => d.coordinates),
    [routePath]
  );

  // Built straight from the path response (not the viewport stop cache) so
  // every stop on the route shows up, even ones never panned to yet.
  const routeStopPoints = useMemo(() => {
    const byId = new Map<string, { stopId: string; lat: number; lon: number; directionId: number }>();
    for (const dir of routePath) {
      dir.stop_ids.forEach((stopId, i) => {
        if (byId.has(stopId)) return;
        const [lat, lon] = dir.coordinates[i];
        byId.set(stopId, { stopId, lat, lon, directionId: dir.direction_id });
      });
    }
    return Array.from(byId.values());
  }, [routePath]);

  const visibleStops = selection.type === "route" ? [] : zoom >= MIN_STOP_ZOOM ? stops : [];

  function mergeStops(newStops: NearbyStop[]) {
    setStops((prev) => {
      const byId = new Map(prev.map((s) => [s.stop_id, s]));
      for (const s of newStops) byId.set(s.stop_id, s);
      return Array.from(byId.values());
    });
  }

  const selectedStopId = selection.type === "stop" ? selection.stopId : null;
  // Memoized on just the stop id (not `stops`/`routeStopPoints`) so this
  // only produces a new reference when the *selection* changes -- same
  // issue as pathBounds above: panning merges newly-loaded stops into
  // state on every move, which would otherwise recreate this array and
  // make FlyTo re-fire on every pan, pulling the view back to the stop.
  // Safe to skip those from the deps: you can only click a marker that's
  // already rendered, so its coordinates are already present at select time.
  const flyTarget: [number, number] | null = useMemo(() => {
    if (!selectedStopId) return null;
    const cached = stops.find((st) => st.stop_id === selectedStopId);
    if (cached) return [cached.lat, cached.lon];
    const onPath = routeStopPoints.find((p) => p.stopId === selectedStopId);
    return onPath ? [onPath.lat, onPath.lon] : null;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedStopId]);

  function selectStop(stopId: string, stopName: string) {
    setSelection({ type: "stop", stopId, stopName });
    setSearch("");
  }

  function selectRoute(routeId: string) {
    setSelection({ type: "route", routeId });
    setSearch("");
  }

  function clearSelection() {
    setSelection({ type: "none" });
  }

  const panelOpen = selection.type !== "none";

  const showZoomHint = selection.type !== "route" && zoom < MIN_STOP_ZOOM;

  return (
    <div className="app-shell">
      <div className="map-pane">
        {showZoomHint && <div className="zoom-hint">Zoom in to see stops</div>}
        <MapContainer
          center={LA_CENTER}
          zoom={INITIAL_ZOOM}
          zoomControl={false}
          style={{ height: "100%", width: "100%" }}
        >
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            maxZoom={19}
          />
          <ZoomTracker onZoomChange={setZoom} />
          <ViewportStopLoader onStopsChange={mergeStops} onError={setLoadError} />
          {flyTarget && <FlyTo position={flyTarget} />}
          {pathBounds.length > 0 && <FitBounds bounds={pathBounds} />}
          {routePath.map((dir) => (
            <Polyline
              key={dir.direction_id}
              positions={dir.coordinates}
              pathOptions={{
                color: DIRECTION_COLORS[dir.direction_id % DIRECTION_COLORS.length],
                weight: 5,
                opacity: 0.85,
                lineCap: "round",
                lineJoin: "round",
              }}
            />
          ))}
          {routeStopPoints.map((point) => {
            const isSelected = selection.type === "stop" && selection.stopId === point.stopId;
            const knownName = stops.find((s) => s.stop_id === point.stopId)?.name;
            return (
              <CircleMarker
                key={point.stopId}
                center={[point.lat, point.lon]}
                radius={isSelected ? 10 : 7}
                pathOptions={{
                  color: "#ffffff",
                  fillColor: isSelected ? SELECTED_STOP_COLOR : DIRECTION_COLORS[point.directionId % DIRECTION_COLORS.length],
                  fillOpacity: 0.95,
                  weight: 2,
                }}
                eventHandlers={{
                  click: () => selectStop(point.stopId, knownName ?? `Stop ${point.stopId}`),
                }}
              />
            );
          })}
          {visibleStops.map((stop) => {
            const isSelected = selection.type === "stop" && selection.stopId === stop.stop_id;
            const isHovered = hoveredStopId === stop.stop_id;
            return (
              <CircleMarker
                key={stop.stop_id}
                center={[stop.lat, stop.lon]}
                radius={isSelected ? 10 : isHovered ? 8 : 5}
                pathOptions={{
                  color: "#ffffff",
                  fillColor: isSelected ? SELECTED_STOP_COLOR : DEFAULT_STOP_COLOR,
                  fillOpacity: 0.95,
                  weight: isSelected ? 2 : 1.5,
                }}
                eventHandlers={{
                  click: () => selectStop(stop.stop_id, stop.name),
                  mouseover: () => setHoveredStopId(stop.stop_id),
                  mouseout: () => setHoveredStopId((id) => (id === stop.stop_id ? null : id)),
                }}
              />
            );
          })}
        </MapContainer>
      </div>

      <aside className={`sidebar ${panelOpen ? "has-panel" : ""}`}>
        <div className="sidebar-header">
          <div className="brand">
            <span className="brand-mark">M</span>
            <div>
              <h1>Metro Reliability</h1>
              <p>How on-time LA buses really are</p>
            </div>
          </div>
          <SearchBar
            routes={routes}
            search={search}
            onSearchChange={setSearch}
            onSelectRoute={selectRoute}
          />
        </div>

        {loadError && <p className="error sidebar-error">Couldn't load data: {loadError}</p>}

        {panelOpen && (
          <div className="sidebar-panel">
            <button type="button" className="panel-close" onClick={clearSelection} aria-label="Close">
              ✕
            </button>
            {selection.type === "route" && <RoutePanel routeId={selection.routeId} />}
            {selection.type === "stop" && (
              <StopPanel stopId={selection.stopId} stopName={selection.stopName} onSelectRoute={selectRoute} />
            )}
          </div>
        )}

        {!panelOpen && (
          <div className="sidebar-empty">
            <p>Search a route above, or click any stop on the map to see how on-time it's been.</p>
            <div className="how-we-measure">
              <h3>How we measure "on time"</h3>
              <p>
                A bus is counted on time if it arrives between 1 minute early and 5 minutes late,
                compared to its published schedule.
              </p>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}
