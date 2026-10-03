import { useEffect, useState } from "react";
import { getStopDelays } from "../api";
import type { StopDelaySummary } from "../types";

function formatTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function formatDelay(seconds: number | null): string {
  if (seconds === null) return "—";
  const minutes = Math.abs(seconds / 60).toFixed(1);
  if (seconds === 0) return "on time";
  return seconds > 0 ? `${minutes} min late` : `${minutes} min early`;
}

interface Props {
  stopId: string;
  stopName: string;
  onSelectRoute: (routeId: string) => void;
}

export default function StopPanel({ stopId, stopName, onSelectRoute }: Props) {
  const [summary, setSummary] = useState<StopDelaySummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSummary(null);
    setError(null);
    getStopDelays(stopId, 7)
      .then(setSummary)
      .catch((err) => setError(err.message));
  }, [stopId]);

  if (error) {
    return <p className="error">{error}</p>;
  }

  return (
    <div className="panel-content">
      <div className="panel-title-row">
        <span className="stop-dot" />
        <h2>{stopName}</h2>
      </div>

      {summary && (
        <>
          <div className="stat-grid two-up">
            <div className="stat-chip">
              <span className="stat-chip-value">
                {summary.on_time_percentage !== null ? `${summary.on_time_percentage}%` : "—"}
              </span>
              <span className="stat-chip-label">on time, last {summary.days} days</span>
            </div>
            <div className="stat-chip">
              <span className="stat-chip-value">{formatDelay(summary.average_delay_seconds)}</span>
              <span className="stat-chip-label">average, all routes</span>
            </div>
          </div>

          <section>
            <h3>Recent arrivals</h3>
            {summary.recent_observations.length === 0 ? (
              <p className="muted">No recent data for this stop yet.</p>
            ) : (
              <ul className="arrival-list">
                {summary.recent_observations.map((o) => (
                  <li key={o.trip_id}>
                    <button
                      type="button"
                      className="route-chip small"
                      onClick={() => onSelectRoute(o.route_id)}
                    >
                      {o.route_id}
                    </button>
                    <span className="arrival-time">{formatTime(o.scheduled_time)}</span>
                    <span className={`arrival-status ${o.canceled ? "status-canceled" : ""}`}>
                      {o.canceled ? "Canceled" : formatDelay(o.delay_seconds)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
