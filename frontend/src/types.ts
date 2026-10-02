export interface RouteSummary {
  route_id: string;
  short_name: string | null;
  long_name: string | null;
}

export interface RouteReliability {
  route_id: string;
  days: number;
  total_observations: number;
  canceled_trips: number;
  on_time_percentage: number | null;
  average_delay_seconds: number | null;
}

export interface HourlyReliability {
  hour: number;
  total_observations: number;
  on_time_percentage: number | null;
  average_delay_seconds: number | null;
}

export interface NearbyStop {
  stop_id: string;
  name: string;
  lat: number;
  lon: number;
  distance_km: number;
}

export interface RecentObservation {
  route_id: string;
  trip_id: string;
  scheduled_time: string | null;
  predicted_time: string | null;
  delay_seconds: number | null;
  canceled: boolean;
}

export interface StopDelaySummary {
  stop_id: string;
  days: number;
  total_observations: number;
  canceled_trips: number;
  on_time_percentage: number | null;
  average_delay_seconds: number | null;
  recent_observations: RecentObservation[];
}
