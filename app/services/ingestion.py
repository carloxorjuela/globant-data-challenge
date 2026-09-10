"""Validation and persistence shared by the CSV and JSON ingestion endpoints."""

import csv
import io
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Department, HiredEmployee, Job
from app.schemas import (
    BatchResult,
    DepartmentIn,
    HiredEmployeeIn,
    JobIn,
    RejectedRow,
)


@dataclass(frozen=True)
class TableSpec:
    """Everything the generic ingestion pipeline needs to know about a table."""

    model: type
    schema: type[BaseModel]
    columns: tuple[str, ...]


# The source files are headerless, so column order is part of the contract.
TABLES: dict[str, TableSpec] = {
    "departments": TableSpec(Department, DepartmentIn, ("id", "department")),
    "jobs": TableSpec(Job, JobIn, ("id", "job")),
    "hired_employees": TableSpec(
        HiredEmployee,
        HiredEmployeeIn,
        ("id", "name", "datetime", "department_id", "job_id"),
    ),
}

IndexedRow = tuple[int, dict[str, Any]]


def _is_header(values: list[str], spec: TableSpec) -> bool:
    """
    Recognise a header only when it actually names the expected columns.

    The supplied files are headerless, but tolerating one is cheap. What is
    not cheap is guessing: an earlier version skipped any first row whose id
    did not look numeric, which meant a genuinely malformed first record
    disappeared without ever showing up among the rejections.
    """
    return [value.strip().lower() for value in values] == [
        column.lower() for column in spec.columns
    ]


def rows_from_csv(content: bytes, spec: TableSpec) -> tuple[list[IndexedRow], list[RejectedRow]]:
    """
    Turn raw CSV bytes into positional dicts.

    Empty fields become None so downstream validation sees a real absence
    instead of an empty string. Rows whose column count does not match the
    table contract are rejected here and never reach the database.
    """
    text = content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))

    rows: list[IndexedRow] = []
    rejected: list[RejectedRow] = []

    for index, values in enumerate(reader):
        if not values or all(value.strip() == "" for value in values):
            continue

        if index == 0 and _is_header(values, spec):
            continue

        if len(values) != len(spec.columns):
            rejected.append(
                RejectedRow(
                    index=index,
                    reason=f"expected {len(spec.columns)} columns, got {len(values)}",
                    row={"raw": values},
                )
            )
            continue

        row = {
            column: (value.strip() or None)
            for column, value in zip(spec.columns, values, strict=True)
        }
        rows.append((index, row))

    return rows, rejected


def _validate(
    rows: list[IndexedRow], spec: TableSpec
) -> tuple[list[tuple[int, BaseModel]], list[RejectedRow]]:
    valid: list[tuple[int, BaseModel]] = []
    rejected: list[RejectedRow] = []

    for index, row in rows:
        try:
            valid.append((index, spec.schema.model_validate(row)))
        except ValidationError as exc:
            reasons = "; ".join(
                f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in exc.errors()
            )
            rejected.append(RejectedRow(index=index, reason=reasons, row=row))

    return valid, rejected


def _reject_unknown_references(
    session: Session, rows: list[tuple[int, BaseModel]]
) -> tuple[list[tuple[int, BaseModel]], list[RejectedRow]]:
    """
    Drop hires pointing at departments or jobs that do not exist.

    Letting the database raise the foreign-key error would abort the whole
    transaction and lose the good rows with it; checking up front lets the
    caller see exactly which records failed and why.
    """
    department_ids = set(session.scalars(select(Department.id)))
    job_ids = set(session.scalars(select(Job.id)))

    valid: list[tuple[int, BaseModel]] = []
    rejected: list[RejectedRow] = []

    for index, record in rows:
        problems = []
        if record.department_id is not None and record.department_id not in department_ids:
            problems.append(f"unknown department_id {record.department_id}")
        if record.job_id is not None and record.job_id not in job_ids:
            problems.append(f"unknown job_id {record.job_id}")

        if problems:
            rejected.append(
                RejectedRow(
                    index=index, reason="; ".join(problems), row=record.model_dump(mode="json")
                )
            )
        else:
            valid.append((index, record))

    return valid, rejected


def _deduplicate(rows: list[tuple[int, BaseModel]]) -> tuple[list[BaseModel], list[RejectedRow]]:
    """
    Keep the last record per id.

    PostgreSQL refuses an ON CONFLICT DO UPDATE that touches the same row twice
    in a single statement, so duplicates inside one payload have to be resolved
    before they reach the database. Superseded rows are reported, not dropped
    silently.
    """
    last_position: dict[int, int] = {}
    for position, (_, record) in enumerate(rows):
        last_position[record.id] = position

    kept: list[BaseModel] = []
    rejected: list[RejectedRow] = []

    for position, (index, record) in enumerate(rows):
        if last_position[record.id] == position:
            kept.append(record)
        else:
            rejected.append(
                RejectedRow(
                    index=index,
                    reason=(
                        f"duplicate id {record.id} within the payload, "
                        "superseded by a later row"
                    ),
                    row=record.model_dump(mode="json"),
                )
            )

    return kept, rejected


def _upsert(
    session: Session, spec: TableSpec, records: list[BaseModel], chunk_size: int = 1000
) -> int:
    """Insert records, overwriting any row that already carries the same id."""
    if not records:
        return 0

    columns = [column.name for column in spec.model.__table__.columns]
    payload = [record.model_dump() for record in records]

    for start in range(0, len(payload), chunk_size):
        chunk = payload[start : start + chunk_size]
        statement = insert(spec.model).values(chunk)
        statement = statement.on_conflict_do_update(
            index_elements=["id"],
            set_={name: statement.excluded[name] for name in columns if name != "id"},
        )
        session.execute(statement)

    return len(payload)


def ingest(
    session: Session,
    spec: TableSpec,
    rows: list[IndexedRow],
    pre_rejected: list[RejectedRow] | None = None,
) -> BatchResult:
    """Validate, de-duplicate and persist a batch, reporting every rejected row."""
    rejected = list(pre_rejected or [])

    valid, invalid = _validate(rows, spec)
    rejected.extend(invalid)

    if spec.model is HiredEmployee:
        valid, unknown_references = _reject_unknown_references(session, valid)
        rejected.extend(unknown_references)

    records, duplicates = _deduplicate(valid)
    rejected.extend(duplicates)

    inserted = _upsert(session, spec, records)
    session.commit()

    rejected.sort(key=lambda row: row.index)
    return BatchResult(
        received=len(rows) + len(pre_rejected or []),
        inserted=inserted,
        rejected=len(rejected),
        errors=rejected,
    )
