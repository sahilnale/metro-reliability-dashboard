import psycopg2
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import Base

TEST_DB_NAME = "metro_test"


def _admin_database_url() -> str:
    return settings.database_url.rsplit("/", 1)[0] + "/postgres"


def _test_database_url() -> str:
    return settings.database_url.rsplit("/", 1)[0] + f"/{TEST_DB_NAME}"


def _ensure_test_database_exists() -> None:
    conn = psycopg2.connect(_admin_database_url().replace("postgresql+psycopg2", "postgresql"))
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB_NAME,))
            if not cur.fetchone():
                cur.execute(f"CREATE DATABASE {TEST_DB_NAME}")
    finally:
        conn.close()


@pytest.fixture(scope="session")
def engine():
    _ensure_test_database_exists()
    eng = create_engine(_test_database_url())
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    SessionLocal = sessionmaker(bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        for table in ("observations", "scheduled_departures", "stops", "routes"):
            s.execute(text(f"TRUNCATE {table} CASCADE"))
        s.commit()
        s.close()
