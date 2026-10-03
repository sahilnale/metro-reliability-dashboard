import { useEffect, useState } from "react";
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

function scoreClass(pct: number | null): string {
  if (pct === null) return "";
  if (pct >= 80) return "score-good";
  if (pct >= 60) return "score-ok";
  return "score-bad";
}

export default function RoutePanel({ routeId }: { routeId: string }) {
  const [reliability, setReliability] = useState<RouteReliability | null>(null);
  const [byHour, setByHour] = useState<HourlyReliability[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setReliability(null);
    setByHour([]);
    setError(null);
    Promise.all([getRouteReliability(routeId, 7), getRouteReliabilityByHour(routeId, 7)])
      .then(([r, hourly]) => {
        setReliability(r);
        setByHour(hourly);
      })
      .catch((err) => setError(err.message));
  }, [routeId]);

  if (error) {
    return <p className="error">{error}</p>;
  }

  const chartData = byHour.map((h) => ({
    hour: formatHour(h.hour),
    onTimePct: h.on_time_percentage ?? 0,
  }));

  return (
    <div className="panel-content">
      <div className="panel-title-row">
        <span className="route-chip big">{routeId}</span>
        <h2>Route {routeId}</h2>
      </div>

      {reliability && (
        <>
          <div className={`score-ring ${scoreClass(reliability.on_time_percentage)}`}>
            <span className="score-value">
              {reliability.on_time_percentage !== null ? `${reliability.on_time_percentage}%` : "—"}
            </span>
            <span className="score-label">on time, last {reliability.days} days</span>
          </div>

          <div className="stat-grid">
            <div className="stat-chip">
              <span className="stat-chip-value">{formatDelay(reliability.average_delay_seconds)}</span>
              <span className="stat-chip-label">average delay</span>
            </div>
            <div className="stat-chip">
              <span className="stat-chip-value">{reliability.total_observations.toLocaleString()}</span>
              <span className="stat-chip-label">arrivals tracked</span>
            </div>
            <div className="stat-chip">
              <span className="stat-chip-value">{reliability.canceled_trips}</span>
              <span className="stat-chip-label">canceled trips</span>
            </div>
          </div>
        </>
      )}

      <section className="chart-section">
        <h3>On-time % by hour of day</h3>
        {chartData.length === 0 ? (
          <p className="muted">Not enough data yet for an hourly breakdown.</p>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="hour" tickLine={false} axisLine={false} />
              <YAxis domain={[0, 100]} unit="%" tickLine={false} axisLine={false} width={40} />
              <Tooltip formatter={(value) => [`${value}%`, "On time"]} cursor={{ fill: "rgba(79,70,229,0.06)" }} />
              <Bar
                dataKey="onTimePct"
                fill="var(--accent)"
                radius={[6, 6, 0, 0]}
                isAnimationActive={false}
              />
            </BarChart>
          </ResponsiveContainer>
        )}
      </section>

      <footer className="how-we-measure">
        <h3>How we measure "on time"</h3>
        <p>Arrives between 1 minute early and 5 minutes late, vs. the published schedule.</p>
      </footer>
    </div>
  );
}
