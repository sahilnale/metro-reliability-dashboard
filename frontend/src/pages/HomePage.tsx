import { useEffect, useMemo, useState } from "react";
import { MapContainer, Marker, Popup, TileLayer } from "react-leaflet";
import { Link, useNavigate } from "react-router-dom";
import { getNearbyStops, getRoutes } from "../api";
import type { NearbyStop, RouteSummary } from "../types";

const LA_CENTER: [number, number] = [34.0407, -118.2468];

export default function HomePage() {
  const [routes, setRoutes] = useState<RouteSummary[]>([]);
  const [stops, setStops] = useState<NearbyStop[]>([]);
  const [search, setSearch] = useState("");
  const [loadError, setLoadError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    getRoutes()
      .then(setRoutes)
      .catch((err) => setLoadError(err.message));
    getNearbyStops(LA_CENTER[0], LA_CENTER[1], 40)
      .then(setStops)
      .catch((err) => setLoadError(err.message));
  }, []);

  const filteredRoutes = useMemo(() => {
    if (!search.trim()) return [];
    const q = search.trim().toLowerCase();
    return routes
      .filter(
        (r) =>
          r.route_id.toLowerCase().includes(q) ||
          r.short_name?.toLowerCase().includes(q) ||
          r.long_name?.toLowerCase().includes(q)
      )
      .slice(0, 8);
  }, [routes, search]);

  return (
    <div className="page">
      <header className="hero">
        <h1>LA Metro Reliability Dashboard</h1>
        <p>
          See which Metro bus lines run on time, and when they tend to run late.
          Numbers are computed from Metro's live arrival data.
        </p>
      </header>

      <section className="search-box">
        <label htmlFor="route-search">Find a bus route</label>
        <input
          id="route-search"
          type="text"
          placeholder="Search by route number or name (e.g. 720)"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          autoComplete="off"
        />
        {filteredRoutes.length > 0 && (
          <ul className="search-results">
            {filteredRoutes.map((r) => (
              <li key={r.route_id}>
                <Link to={`/routes/${r.route_id}`}>
                  <strong>{r.short_name ?? r.route_id}</strong> — {r.long_name ?? "Metro Bus"}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      {loadError && <p className="error">Couldn't load data: {loadError}</p>}

      <section className="map-section">
        <h2>Stops near Downtown LA</h2>
        <p className="muted">Click a stop to see its recent arrival delays.</p>
        <div className="map-container">
          <MapContainer center={LA_CENTER} zoom={12} style={{ height: "420px", width: "100%" }}>
            <TileLayer
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            />
            {stops.map((stop) => (
              <Marker key={stop.stop_id} position={[stop.lat, stop.lon]}>
                <Popup>
                  <strong>{stop.name}</strong>
                  <br />
                  <button type="button" onClick={() => navigate(`/stops/${stop.stop_id}`)}>
                    View delays
                  </button>
                </Popup>
              </Marker>
            ))}
          </MapContainer>
        </div>
      </section>

      <footer className="how-we-measure">
        <h2>How we measure "on time"</h2>
        <p>
          A bus is counted <strong>on time</strong> if it arrives between 1 minute early and 5 minutes
          late, compared to its published schedule. That's a common standard used across the transit
          industry. Everything else counts as early or late.
        </p>
      </footer>
    </div>
  );
}
