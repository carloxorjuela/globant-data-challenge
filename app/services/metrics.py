"""Stakeholder metrics.

The statements live in sql/ as plain files and are executed verbatim, so the
reviewable SQL and the SQL the API actually runs can never drift apart.
"""

from functools import lru_cache
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas import DepartmentAboveMean, QuarterlyHires

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


@lru_cache
def _statement(filename: str) -> str:
    return (SQL_DIR / filename).read_text(encoding="utf-8")


def hires_by_quarter(session: Session, year: int) -> list[QuarterlyHires]:
    rows = session.execute(text(_statement("01_hires_by_quarter.sql")), {"year": year})
    return [QuarterlyHires(**row._mapping) for row in rows]


def departments_above_mean(session: Session, year: int) -> list[DepartmentAboveMean]:
    rows = session.execute(text(_statement("02_departments_above_mean.sql")), {"year": year})
    return [DepartmentAboveMean(**row._mapping) for row in rows]
