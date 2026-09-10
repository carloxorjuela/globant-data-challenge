"""Endpoints that land historical data into the new database."""

from fastapi import APIRouter, Depends, File, HTTPException, Path, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import BatchResult, DepartmentBatch, HiredEmployeeBatch, JobBatch
from app.services.ingestion import TABLES, ingest, rows_from_csv

router = APIRouter(prefix="/api/v1", tags=["ingestion"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _indexed(batch) -> list[tuple[int, dict]]:
    """Adapt an already-parsed batch to the positional form the service expects."""
    return [(index, row.model_dump(mode="json")) for index, row in enumerate(batch.rows)]


@router.post(
    "/{table}/upload-csv",
    response_model=BatchResult,
    summary="Load a historical CSV file into one of the migrated tables",
)
async def upload_csv(
    table: str = Path(description="departments, jobs or hired_employees"),
    file: UploadFile = File(description="Headerless, comma-separated file"),
    session: Session = Depends(get_db),
) -> BatchResult:
    spec = TABLES.get(table)
    if spec is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"unknown table '{table}'; expected one of {sorted(TABLES)}",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="the uploaded file is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"file exceeds the {MAX_UPLOAD_BYTES} byte limit",
        )

    rows, malformed = rows_from_csv(content, spec)
    return ingest(session, spec, rows, pre_rejected=malformed)


@router.post(
    "/departments/batch", response_model=BatchResult, summary="Insert 1 to 1000 departments"
)
def insert_departments(batch: DepartmentBatch, session: Session = Depends(get_db)) -> BatchResult:
    return ingest(session, TABLES["departments"], _indexed(batch))


@router.post("/jobs/batch", response_model=BatchResult, summary="Insert 1 to 1000 jobs")
def insert_jobs(batch: JobBatch, session: Session = Depends(get_db)) -> BatchResult:
    return ingest(session, TABLES["jobs"], _indexed(batch))


@router.post("/hired_employees/batch", response_model=BatchResult, summary="Insert 1 to 1000 hires")
def insert_hired_employees(
    batch: HiredEmployeeBatch, session: Session = Depends(get_db)
) -> BatchResult:
    return ingest(session, TABLES["hired_employees"], _indexed(batch))
