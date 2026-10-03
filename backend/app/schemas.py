from datetime import datetime

from pydantic import BaseModel


class RouteSummary(BaseModel):
    route_id: str
    short_name: str | None
    long_name: str | None


class RouteReliability(BaseModel):
    route_id: str
    days: int
    total_observations: int
    canceled_trips: int
    on_time_percentage: float | None
    average_delay_seconds: float | None


class HourlyReliability(BaseModel):
    hour: int
    total_observations: int
    on_time_percentage: float | None
    average_delay_seconds: float | None


class NearbyStop(BaseModel):
    stop_id: str
    name: str
    lat: float
    lon: float
    distance_km: float


class RecentObservation(BaseModel):
    route_id: str
    trip_id: str
    scheduled_time: datetime | None
    predicted_time: datetime | None
    delay_seconds: int | None
    canceled: bool


class RouteDirectionPath(BaseModel):
    direction_id: int
    coordinates: list[list[float]]
    stop_ids: list[str]


class StopDelaySummary(BaseModel):
    stop_id: str
    days: int
    total_observations: int
    canceled_trips: int
    on_time_percentage: float | None
    average_delay_seconds: float | None
    recent_observations: list[RecentObservation]
