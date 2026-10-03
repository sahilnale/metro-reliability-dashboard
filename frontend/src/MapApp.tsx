import { useEffect, useState } from "react";
import { CircleMarker, MapContainer, TileLayer } from "react-leaflet";
import { getNearbyStops, getRoutes } from "./api";
import FlyTo from "./components/FlyTo";
import RoutePanel from "./components/RoutePanel";
import SearchBar from "./components/SearchBar";
import StopPanel from "./components/StopPanel";
import type { NearbyStop, RouteSummary } from "./types";

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

  useEffect(() => {
    getRoutes()
      .then(setRoutes)
      .catch((err) => setLoadError(err.message));
    getNearbyStops(LA_CENTER[0], LA_CENTER[1], 200)
      .then(setStops)
      .catch((err) => setLoadError(err.message));
  }, []);

  const flyTarget: [number, number] | null =
    selection.type === "stop"
      ? (() => {
          const s = stops.find((st) => st.stop_id === selection.stopId);
          return s ? [s.lat, s.lon] : null;
        })()
      : null;

  function selectStop(stop: NearbyStop) {
    setSelection({ type: "stop", stopId: stop.stop_id, stopName: stop.name });
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

  return (
    <div className="app-shell">
      <div className="map-pane">
        <MapContainer center={LA_CENTER} zoom={13} zoomControl={false} style={{ height: "100%", width: "100%" }}>
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            maxZoom={19}
          />
          {flyTarget && <FlyTo position={flyTarget} />}
          {stops.map((stop) => {
            const isSelected = selection.type === "stop" && selection.stopId === stop.stop_id;
            const isHovered = hoveredStopId === stop.stop_id;
            return (
              <CircleMarker
                key={stop.stop_id}
                center={[stop.lat, stop.lon]}
                radius={isSelected ? 10 : isHovered ? 8 : 5}
                pathOptions={{
                  color: isSelected ? "#f59e0b" : "#4f46e5",
                  fillColor: isSelected ? "#f59e0b" : "#4f46e5",
                  fillOpacity: isSelected ? 0.9 : 0.75,
                  weight: isSelected ? 3 : 1.5,
                }}
                eventHandlers={{
                  click: () => selectStop(stop),
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
