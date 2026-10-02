import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
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

export default function StopPage() {
  const { stopId } = useParams<{ stopId: string }>();
  const [summary, setSummary] = useState<StopDelaySummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!stopId) return;
    setError(null);
    getStopDelays(stopId, 7)
      .then(setSummary)
      .catch((err) => setError(err.message));
  }, [stopId]);

  if (error) {
    return (
      <div className="page">
        <p className="error">{error}</p>
        <Link to="/">Back to map</Link>
      </div>
    );
  }

  return (
    <div className="page">
      <Link to="/" className="back-link">
        ← Back to map
      </Link>
      <h1>Stop {stopId}</h1>

      {summary && (
        <>
          <section className="stat-row">
            <div className="stat-card">
              <span className="stat-value">
                {summary.on_time_percentage !== null ? `${summary.on_time_percentage}%` : "—"}
              </span>
              <span className="stat-label">on time (last {summary.days} days)</span>
            </div>
            <div className="stat-card">
              <span className="stat-value">
                {summary.average_delay_seconds !== null
                  ? formatDelay(summary.average_delay_seconds)
                  : "—"}
              </span>
              <span className="stat-label">average, all routes through here</span>
            </div>
          </section>

          <section className="delay-table-section">
            <h2>Recent arrivals</h2>
            {summary.recent_observations.length === 0 ? (
              <p className="muted">No recent data for this stop yet.</p>
            ) : (
              <table className="delay-table">
                <thead>
                  <tr>
                    <th>Route</th>
                    <th>Scheduled</th>
                    <th>Predicted/actual</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.recent_observations.map((o) => (
                    <tr key={o.trip_id}>
                      <td>
                        <Link to={`/routes/${o.route_id}`}>{o.route_id}</Link>
                      </td>
                      <td>{formatTime(o.scheduled_time)}</td>
                      <td>{o.canceled ? "—" : formatTime(o.predicted_time)}</td>
                      <td className={o.canceled ? "status-canceled" : ""}>
                        {o.canceled ? "Canceled" : formatDelay(o.delay_seconds)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}
    </div>
  );
}
