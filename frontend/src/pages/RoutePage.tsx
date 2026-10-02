import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getRouteReliability, getRouteReliabilityByHour } from "../api";
import type { HourlyReliability, RouteReliability } from "../types";

function formatHour(hour: number): string {
  const period = hour < 12 ? "AM" : "PM";
  const display = hour % 12 === 0 ? 12 : hour % 12;
  return `${display}${period}`;
}

function formatDelay(seconds: number | null): string {
  if (seconds === null) return "—";
  const rounded = Math.round(seconds);
  if (rounded === 0) return "on schedule, on average";
  const minutes = Math.abs(rounded / 60).toFixed(1);
  return rounded > 0 ? `${minutes} min late, on average` : `${minutes} min early, on average`;
}

export default function RoutePage() {
  const { routeId } = useParams<{ routeId: string }>();
  const [reliability, setReliability] = useState<RouteReliability | null>(null);
  const [byHour, setByHour] = useState<HourlyReliability[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!routeId) return;
    setError(null);
    Promise.all([getRouteReliability(routeId, 7), getRouteReliabilityByHour(routeId, 7)])
      .then(([r, hourly]) => {
        setReliability(r);
        setByHour(hourly);
      })
      .catch((err) => setError(err.message));
  }, [routeId]);

  if (error) {
    return (
      <div className="page">
        <p className="error">{error}</p>
        <Link to="/">Back to search</Link>
      </div>
    );
  }

  const chartData = byHour.map((h) => ({
    hour: formatHour(h.hour),
    onTimePct: h.on_time_percentage ?? 0,
  }));

  return (
    <div className="page">
      <Link to="/" className="back-link">
        ← Back to search
      </Link>
      <h1>Route {routeId}</h1>

      {reliability && (
        <section className="stat-row">
          <div className="stat-card">
            <span className="stat-value">
              {reliability.on_time_percentage !== null ? `${reliability.on_time_percentage}%` : "—"}
            </span>
            <span className="stat-label">on time (last {reliability.days} days)</span>
          </div>
          <div className="stat-card">
            <span className="stat-value">{formatDelay(reliability.average_delay_seconds)}</span>
            <span className="stat-label">average delay</span>
          </div>
          <div className="stat-card">
            <span className="stat-value">{reliability.total_observations.toLocaleString()}</span>
            <span className="stat-label">arrivals tracked</span>
          </div>
          <div className="stat-card">
            <span className="stat-value">{reliability.canceled_trips}</span>
            <span className="stat-label">canceled trips</span>
          </div>
        </section>
      )}

      <section className="chart-section">
        <h2>On-time percentage by hour of day</h2>
        {chartData.length === 0 ? (
          <p className="muted">Not enough data yet for an hourly breakdown.</p>
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="hour" />
              <YAxis domain={[0, 100]} unit="%" />
              <Tooltip formatter={(value) => [`${value}%`, "On time"]} />
              <Bar dataKey="onTimePct" fill="#2a6f97" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </section>

      <footer className="how-we-measure">
        <h2>How we measure "on time"</h2>
        <p>
          A bus is counted on time if it arrives between 1 minute early and 5 minutes late,
          compared to its published schedule.
        </p>
      </footer>
    </div>
  );
}
