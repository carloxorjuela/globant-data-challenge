from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import models  # noqa: F401  -- registers the ORM metadata
from app.database import Base, get_db, get_engine
from app.routers import ingestion, metrics


@asynccontextmanager
async def lifespan(_: FastAPI):
    # The schema is small and fully described by the ORM metadata, so it is
    # created at startup. A longer-lived system would move this to Alembic;
    # see "Design decisions" in the README.
    Base.metadata.create_all(bind=get_engine())
    yield


app = FastAPI(
    title="Globant Data Engineering Challenge",
    description=(
        "REST API for migrating three legacy tables into a SQL database "
        "and reporting the hiring metrics requested by stakeholders."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(ingestion.router)
app.include_router(metrics.router)


@app.get("/health", tags=["operations"], summary="Liveness and database connectivity")
def health(session: Session = Depends(get_db)) -> dict[str, str]:
    # Goes through the dependency rather than reaching for a session factory
    # directly, so a test overriding get_db actually redirects this too.
    session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "reachable"}
