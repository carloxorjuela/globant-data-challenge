"""Section 1: CSV ingestion and batch transactions."""

import io

import pytest

from app.schemas import MAX_BATCH_SIZE


def _hire(employee_id: int, quarter_month: int = 3) -> dict:
    return {
        "id": employee_id,
        "name": f"Employee {employee_id}",
        "datetime": f"2021-{quarter_month:02d}-15T10:00:00Z",
        "department_id": 1,
        "job_id": 1,
    }


def test_single_row_batch_is_accepted(client, reference_data):
    response = client.post("/api/v1/hired_employees/batch", json={"rows": [_hire(1)]})

    assert response.status_code == 200
    assert response.json() == {"received": 1, "inserted": 1, "rejected": 0, "errors": []}


def test_batch_accepts_the_maximum_of_1000_rows(client, reference_data):
    rows = [_hire(employee_id) for employee_id in range(1, MAX_BATCH_SIZE + 1)]

    response = client.post("/api/v1/hired_employees/batch", json={"rows": rows})

    assert response.status_code == 200
    assert response.json()["inserted"] == MAX_BATCH_SIZE


@pytest.mark.parametrize("size", [0, MAX_BATCH_SIZE + 1])
def test_batch_rejects_payloads_outside_the_allowed_range(client, reference_data, size):
    rows = [_hire(employee_id) for employee_id in range(1, size + 1)]

    response = client.post("/api/v1/hired_employees/batch", json={"rows": rows})

    assert response.status_code == 422


def test_replaying_a_batch_is_idempotent(client, reference_data):
    payload = {"rows": [_hire(1), _hire(2)]}

    client.post("/api/v1/hired_employees/batch", json=payload)
    second = client.post("/api/v1/hired_employees/batch", json=payload)

    assert second.json()["inserted"] == 2
    quarters = client.get("/api/v1/metrics/hires-by-quarter", params={"year": 2021}).json()
    assert sum(row["Q1"] for row in quarters) == 2


def test_rows_referencing_a_missing_department_are_reported_not_dropped(client, reference_data):
    good, orphan = _hire(1), _hire(2) | {"department_id": 999}

    response = client.post("/api/v1/hired_employees/batch", json={"rows": [good, orphan]})

    body = response.json()
    assert body["inserted"] == 1
    assert body["rejected"] == 1
    assert "unknown department_id 999" in body["errors"][0]["reason"]


def test_duplicate_ids_inside_one_payload_keep_the_last_row(client, reference_data):
    first = _hire(1) | {"name": "Original"}
    second = _hire(1) | {"name": "Corrected"}

    body = client.post("/api/v1/hired_employees/batch", json={"rows": [first, second]}).json()

    assert body["inserted"] == 1
    assert body["rejected"] == 1
    assert "superseded" in body["errors"][0]["reason"]


def test_csv_upload_loads_a_headerless_file(client):
    csv_bytes = b"1,Supply Chain\n2,Staff\n"

    response = client.post(
        "/api/v1/departments/upload-csv",
        files={"file": ("departments.csv", io.BytesIO(csv_bytes), "text/csv")},
    )

    assert response.status_code == 200
    assert response.json()["inserted"] == 2


def test_csv_upload_reports_malformed_rows_and_keeps_the_rest(client):
    csv_bytes = b"1,Supply Chain\n2,Staff,extra-column\n3,Engineering\n"

    body = client.post(
        "/api/v1/departments/upload-csv",
        files={"file": ("departments.csv", io.BytesIO(csv_bytes), "text/csv")},
    ).json()

    assert body["inserted"] == 2
    assert body["rejected"] == 1
    assert "expected 2 columns, got 3" in body["errors"][0]["reason"]


def test_unknown_table_is_rejected(client):
    response = client.post(
        "/api/v1/salaries/upload-csv",
        files={"file": ("x.csv", io.BytesIO(b"1,x\n"), "text/csv")},
    )

    assert response.status_code == 404
