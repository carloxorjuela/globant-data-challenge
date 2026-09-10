from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# The challenge caps a single transaction at 1000 rows.
MAX_BATCH_SIZE = 1000


class DepartmentIn(BaseModel):
    id: int = Field(gt=0)
    department: str = Field(min_length=1, max_length=100)


class JobIn(BaseModel):
    id: int = Field(gt=0)
    job: str = Field(min_length=1, max_length=100)


class HiredEmployeeIn(BaseModel):
    # `datetime` is the field name used by the source files; `hire_datetime` is
    # the column name. populate_by_name lets callers send either one.
    model_config = ConfigDict(populate_by_name=True)

    id: int = Field(gt=0)
    name: str | None = Field(default=None, max_length=200)
    hire_datetime: datetime | None = Field(default=None, alias="datetime")
    department_id: int | None = Field(default=None, gt=0)
    job_id: int | None = Field(default=None, gt=0)


class DepartmentBatch(BaseModel):
    rows: list[DepartmentIn] = Field(min_length=1, max_length=MAX_BATCH_SIZE)


class JobBatch(BaseModel):
    rows: list[JobIn] = Field(min_length=1, max_length=MAX_BATCH_SIZE)


class HiredEmployeeBatch(BaseModel):
    rows: list[HiredEmployeeIn] = Field(min_length=1, max_length=MAX_BATCH_SIZE)


class RejectedRow(BaseModel):
    """A source row that could not be persisted, and why."""

    index: int = Field(description="Zero-based position in the submitted payload")
    reason: str
    row: dict[str, Any]


class BatchResult(BaseModel):
    received: int
    inserted: int
    rejected: int
    errors: list[RejectedRow] = Field(default_factory=list)


class QuarterlyHires(BaseModel):
    department: str
    job: str
    Q1: int
    Q2: int
    Q3: int
    Q4: int


class DepartmentAboveMean(BaseModel):
    id: int
    department: str
    hired: int


class DataQualityReport(BaseModel):
    """Completeness of the migrated hires."""

    total_rows: int
    missing_name: int
    missing_hire_datetime: int
    missing_department: int
    missing_job: int
    incomplete_rows: int
