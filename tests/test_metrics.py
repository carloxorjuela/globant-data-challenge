"""Section 2: the two stakeholder metrics."""

import pytest

QUARTER_DATES = {1: "2021-02-10", 2: "2021-05-10", 3: "2021-08-10", 4: "2021-11-10"}


def _hire(
    employee_id: int, department_id: int, job_id: int, quarter: int, year: int = 2021
) -> dict:
    date = QUARTER_DATES[quarter].replace("2021", str(year))
    return {
        "id": employee_id,
        "name": f"Employee {employee_id}",
        "datetime": f"{date}T12:00:00Z",
        "department_id": department_id,
        "job_id": job_id,
    }


@pytest.fixture
def hiring_history(client, reference_data):
    """
    Staff/Recruiter        -> Q1 x2, Q4 x1
    Staff/Manager          -> Q2 x1
    Supply Chain/Manager   -> Q3 x1
    Plus one 2022 hire that must never appear in a 2021 report.
    """
    rows = [
        _hire(1, department_id=2, job_id=1, quarter=1),
        _hire(2, department_id=2, job_id=1, quarter=1),
        _hire(3, department_id=2, job_id=1, quarter=4),
        _hire(4, department_id=2, job_id=2, quarter=2),
        _hire(5, department_id=1, job_id=2, quarter=3),
        _hire(6, department_id=1, job_id=2, quarter=1, year=2022),
    ]
    client.post("/api/v1/hired_employees/batch", json={"rows": rows})


def test_hires_by_quarter_pivots_and_orders_alphabetically(client, hiring_history):
    response = client.get("/api/v1/metrics/hires-by-quarter", params={"year": 2021})

    assert response.status_code == 200
    assert response.json() == [
        {"department": "Staff", "job": "Manager", "Q1": 0, "Q2": 1, "Q3": 0, "Q4": 0},
        {"department": "Staff", "job": "Recruiter", "Q1": 2, "Q2": 0, "Q3": 0, "Q4": 1},
        {"department": "Supply Chain", "job": "Manager", "Q1": 0, "Q2": 0, "Q3": 1, "Q4": 0},
    ]


def test_hires_by_quarter_excludes_other_years(client, hiring_history):
    body = client.get("/api/v1/metrics/hires-by-quarter", params={"year": 2022}).json()

    assert body == [
        {"department": "Supply Chain", "job": "Manager", "Q1": 1, "Q2": 0, "Q3": 0, "Q4": 0}
    ]


def test_departments_above_mean_returns_only_those_over_the_average(client, hiring_history):
    # 2021 hires: Staff 4, Supply Chain 1 -> mean 2.5 -> only Staff qualifies.
    body = client.get("/api/v1/metrics/departments-above-mean", params={"year": 2021}).json()

    assert body == [{"id": 2, "department": "Staff", "hired": 4}]


def test_metrics_reject_an_out_of_range_year(client):
    assert client.get("/api/v1/metrics/hires-by-quarter", params={"year": 1500}).status_code == 422


def test_data_quality_counts_incomplete_rows(client, reference_data):
    rows = [
        {
            "id": 1,
            "name": "Complete",
            "datetime": "2021-03-01T10:00:00Z",
            "department_id": 1,
            "job_id": 1,
        },
        {
            "id": 2,
            "name": None,
            "datetime": "2021-03-01T10:00:00Z",
            "department_id": 1,
            "job_id": 1,
        },
        {"id": 3, "name": "No date", "datetime": None, "department_id": 1, "job_id": None},
    ]
    client.post("/api/v1/hired_employees/batch", json={"rows": rows})

    assert client.get("/api/v1/metrics/data-quality").json() == {
        "total_rows": 3,
        "missing_name": 1,
        "missing_hire_datetime": 1,
        "missing_department": 0,
        "missing_job": 1,
        "incomplete_rows": 2,
    }
