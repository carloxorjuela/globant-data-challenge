"""
Test fixtures.

The metrics use PostgreSQL-specific syntax (COUNT ... FILTER, ON CONFLICT),
so the suite runs against a real PostgreSQL instance rather than SQLite. Point
TEST_DATABASE_URL at the compose stack locally, or at the service container in CI.
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://challenge:challenge@localhost:5432/challenge",
)


@pytest.fixture(scope="session")
def engine():
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine) -> Session:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.execute(
            text("TRUNCATE hired_employees, departments, jobs RESTART IDENTITY CASCADE")
        )
        session.commit()
        yield session


@pytest.fixture
def client(session) -> TestClient:
    app.dependency_overrides[get_db] = lambda: session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def reference_data(client) -> None:
    """Departments and jobs must exist before hires can reference them."""
    client.post("/api/v1/departments/batch", json={"rows": [
        {"id": 1, "department": "Supply Chain"},
        {"id": 2, "department": "Staff"},
    ]})
    client.post("/api/v1/jobs/batch", json={"rows": [
        {"id": 1, "job": "Recruiter"},
        {"id": 2, "job": "Manager"},
    ]})
