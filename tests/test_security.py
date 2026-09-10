"""Who can change the data, and who can only read it."""

import io

import pytest

from tests.conftest import TEST_API_KEY

DEPARTMENT = {"rows": [{"id": 1, "department": "Supply Chain"}]}


def test_a_batch_without_a_key_is_rejected(anonymous_client):
    response = anonymous_client.post("/api/v1/departments/batch", json=DEPARTMENT)

    assert response.status_code == 401


def test_a_batch_with_the_wrong_key_is_rejected(anonymous_client):
    response = anonymous_client.post(
        "/api/v1/departments/batch",
        json=DEPARTMENT,
        headers={"X-API-Key": "not-the-key"},
    )

    assert response.status_code == 401


def test_a_csv_upload_without_a_key_is_rejected(anonymous_client):
    response = anonymous_client.post(
        "/api/v1/departments/upload-csv",
        files={"file": ("departments.csv", io.BytesIO(b"1,Supply Chain\n"), "text/csv")},
    )

    assert response.status_code == 401


def test_a_batch_with_the_right_key_is_accepted(anonymous_client):
    response = anonymous_client.post(
        "/api/v1/departments/batch",
        json=DEPARTMENT,
        headers={"X-API-Key": TEST_API_KEY},
    )

    assert response.status_code == 200
    assert response.json()["inserted"] == 1


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/v1/metrics/hires-by-quarter",
        "/api/v1/metrics/departments-above-mean",
        "/api/v1/metrics/data-quality",
        "/health",
    ],
)
def test_reading_needs_no_key(anonymous_client, endpoint):
    assert anonymous_client.get(endpoint).status_code == 200
