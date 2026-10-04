from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://metro:metro@localhost:5432/metro"
    metro_api_base_url: str = "https://api.metro.net"
    metro_ws_base_url: str = "wss://api.metro.net"

    # Plain comma-separated string rather than list[str] -- pydantic-settings
    # expects JSON array syntax for list-typed env vars, which is awkward to
    # paste into a host's env var UI (e.g. Render). "https://a.com,https://b.com"
    # is much easier to set correctly.
    cors_origins_raw: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]

    # On-time window, in seconds relative to the scheduled time.
    # Common transit industry standard: 1 minute early to 5 minutes late.
    on_time_early_seconds: int = 60
    on_time_late_seconds: int = 300


settings = Settings()
