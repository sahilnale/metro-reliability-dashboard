import enum
from datetime import datetime, time

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class DayType(str, enum.Enum):
    weekday = "weekday"
    saturday = "saturday"
    sunday = "sunday"


class Route(Base):
    __tablename__ = "routes"

    route_id: Mapped[str] = mapped_column(String, primary_key=True)
    route_code: Mapped[str] = mapped_column(String, index=True)
    short_name: Mapped[str | None] = mapped_column(String, nullable=True)
    long_name: Mapped[str | None] = mapped_column(String, nullable=True)
    mode: Mapped[str] = mapped_column(String)  # "bus" or "rail"
    agency_id: Mapped[str] = mapped_column(String)
    color: Mapped[str | None] = mapped_column(String, nullable=True)

    stops: Mapped[list["ScheduledDeparture"]] = relationship(back_populates="route")


class Stop(Base):
    __tablename__ = "stops"

    stop_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    agency_id: Mapped[str] = mapped_column(String)


class ScheduledDeparture(Base):
    """One scheduled departure time for a route, at a stop, on a given day type.

    Loaded from Metro's route_stops endpoint, which returns a day's worth of
    departure times per (route, stop) rather than per individual trip. We
    match a real-time prediction to the nearest of these times by
    time-of-day (see worker/parse.py) since the API doesn't expose a
    scheduled time keyed by trip_id directly.
    """

    __tablename__ = "scheduled_departures"
    __table_args__ = (
        UniqueConstraint(
            "route_id", "stop_id", "day_type", "departure_time",
            name="uq_scheduled_departure",
        ),
        Index("ix_scheduled_departures_lookup", "route_id", "stop_id", "day_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    route_id: Mapped[str] = mapped_column(ForeignKey("routes.route_id"))
    stop_id: Mapped[str] = mapped_column(ForeignKey("stops.stop_id"))
    day_type: Mapped[str] = mapped_column(String)
    stop_sequence: Mapped[int] = mapped_column()
    departure_time: Mapped[time] = mapped_column(Time)

    route: Mapped[Route] = relationship(back_populates="stops")


class Observation(Base):
    """One real-time delay (or cancellation) record for a trip at a stop.

    Upserted on (trip_id, stop_id): as a trip_updates message repeats with a
    fresher prediction for the same stop, we overwrite in place rather than
    inserting duplicate rows, so the stored value is always the latest
    prediction Metro gave for that stop -- the closest proxy we have to an
    "actual" time once the vehicle has passed.
    """

    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint("trip_id", "stop_id", name="uq_observation_trip_stop"),
        Index("ix_observations_route_time", "route_id", "observed_at"),
        Index("ix_observations_stop_time", "stop_id", "observed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    route_id: Mapped[str] = mapped_column(ForeignKey("routes.route_id"))
    stop_id: Mapped[str | None] = mapped_column(ForeignKey("stops.stop_id"), nullable=True)
    trip_id: Mapped[str] = mapped_column(String)
    # timezone=True so Postgres normalizes to UTC internally regardless of
    # which zone the Python datetime was built in -- scheduled_time is
    # constructed in America/Los_Angeles local time (see worker/parse.py:
    # local_datetime) while predicted_time arrives as UTC; without this,
    # a plain DateTime column would silently store both as naive wall-clock
    # values, 7-8 hours apart from each other, corrupting any SQL-level
    # comparison between them even though the precomputed delay_seconds
    # (computed in Python with correct tz math) stays correct.
    scheduled_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    predicted_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delay_seconds: Mapped[int | None] = mapped_column(nullable=True)
    canceled: Mapped[bool] = mapped_column(default=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
