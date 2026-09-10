"""
Test fixtures.

The suite runs against a real PostgreSQL instance rather than SQLite. SQLite
would be quicker to set up and does support the syntax used here, but upsert
conflict semantics, timezone handling and planner behaviour are exactly what
these tests are meant to check against the engine the service actually runs on.

Isolation needs care. The application builds its engine from DATABASE_URL, so
redirecting only TEST_DATABASE_URL would leave the app talking to whatever
DATABASE_URL happened to hold while the fixtures below truncated a different
database. Both variables are set here, before anything imports the app, and a
guard refuses to run at all unless the target database name marks it as
disposable.
"""

import os

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://challenge:challenge@localhost:5432/challenge_test",
)

# Set before the imports below, because app.config reads the environment the
# first time it is touched and app.database caches an engine built from it.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["TEST_DATABASE_URL"] = TEST_DATABASE_URL

# Not a secret, and deliberately not the deployed one.
TEST_API_KEY = "test-key-not-a-real-secret"
os.environ["API_KEY"] = TEST_API_KEY

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, make_url, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

TRUNCATE = "TRUNCATE hired_employees, departments, jobs RESTART IDENTITY CASCADE"


def _require_disposable_database(url: str) -> str:
    """
    Refuse to touch anything that is not obviously a scratch database.

    Every test truncates all three tables. Running that against the database
    holding the loaded demo data is a mistake worth making impossible rather
    than merely unlikely.
    """
    name = make_url(url).database or ""
    if not name.endswith("_test"):
        raise RuntimeError(
            f"refusing to run the suite against database {name!r}. "
            "The fixtures truncate every table, so the name must end in '_test'. "
            "Set TEST_DATABASE_URL to a disposable database."
        )
    return name


def _create_database_if_missing(url: str) -> None:
    target = make_url(url)
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        exists = connection.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": target.database},
        )
        if not exists:
            # An identifier cannot be bound as a parameter. The name is our own
            # and has already passed the '_test' guard above.
            connection.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def engine():
    _require_disposable_database(TEST_DATABASE_URL)
    _create_database_if_missing(TEST_DATABASE_URL)

    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine) -> Session:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.execute(text(TRUNCATE))
        session.commit()
        yield session


@pytest.fixture
def client(session) -> TestClient:
    """A client authorised to write. Most tests are about behaviour, not access."""
    app.dependency_overrides[get_db] = lambda: session
    with TestClient(app, headers={"X-API-Key": TEST_API_KEY}) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def anonymous_client(session) -> TestClient:
    """A client that sends no key, for the authorisation tests."""
    app.dependency_overrides[get_db] = lambda: session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def reference_data(client) -> None:
    """Departments and jobs must exist before hires can reference them."""
    client.post(
        "/api/v1/departments/batch",
        json={
            "rows": [
                {"id": 1, "department": "Supply Chain"},
                {"id": 2, "department": "Staff"},
            ]
        },
    )
    client.post(
        "/api/v1/jobs/batch",
        json={
            "rows": [
                {"id": 1, "job": "Recruiter"},
                {"id": 2, "job": "Manager"},
            ]
        },
    )
