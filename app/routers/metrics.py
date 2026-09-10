"""One endpoint per stakeholder requirement."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import DataQualityReport, DepartmentAboveMean, QuarterlyHires
from app.services import metrics

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])

Year = Query(default=2021, ge=1900, le=2100, description="Calendar year, UTC")


@router.get(
    "/hires-by-quarter",
    response_model=list[QuarterlyHires],
    summary="Hires per department and job, split by quarter",
)
def hires_by_quarter(year: int = Year, session: Session = Depends(get_db)) -> list[QuarterlyHires]:
    return metrics.hires_by_quarter(session, year)


@router.get(
    "/departments-above-mean",
    response_model=list[DepartmentAboveMean],
    summary="Departments hiring above the yearly mean",
)
def departments_above_mean(
    year: int = Year, session: Session = Depends(get_db)
) -> list[DepartmentAboveMean]:
    return metrics.departments_above_mean(session, year)


@router.get(
    "/data-quality",
    response_model=DataQualityReport,
    summary="Completeness of the migrated hires",
)
def data_quality(session: Session = Depends(get_db)) -> DataQualityReport:
    return metrics.data_quality(session)
