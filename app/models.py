from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    department: Mapped[str] = mapped_column(String(100), nullable=False)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    job: Mapped[str] = mapped_column(String(100), nullable=False)


class HiredEmployee(Base):
    """
    Hires coming from the legacy system.

    Every column except the primary key is nullable on purpose. The historical
    files carry incomplete rows -- missing name, hire date, department or job --
    and the migration has to land them instead of rejecting the whole batch.
    Completeness is reported back to the caller, not enforced by the schema.

    The challenge calls the timestamp column `datetime`; it is stored as
    `hire_datetime` so it does not shadow the stdlib type. The API accepts both
    spellings (see schemas.HiredEmployeeIn).
    """

    __tablename__ = "hired_employees"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str | None] = mapped_column(String(200))
    hire_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), index=True)
