"""The guard that keeps the suite away from a non-disposable database."""

import pytest

from tests.conftest import _require_disposable_database


def test_guard_rejects_a_database_that_is_not_marked_disposable():
    with pytest.raises(RuntimeError, match="_test"):
        _require_disposable_database(
            "postgresql+psycopg://challenge:challenge@localhost:5432/challenge"
        )


def test_guard_accepts_a_disposable_database():
    url = "postgresql+psycopg://challenge:challenge@localhost:5432/challenge_test"

    assert _require_disposable_database(url) == "challenge_test"
