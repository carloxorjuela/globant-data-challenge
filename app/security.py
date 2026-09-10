"""API key guard for the endpoints that change data."""

import secrets

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.config import Settings, get_settings

API_KEY_HEADER = "X-API-Key"

_api_key_header = APIKeyHeader(
    name=API_KEY_HEADER,
    auto_error=False,
    description="Shared key required to load or modify data. Reports need no key.",
)


def require_api_key(
    provided: str | None = Security(_api_key_header),
    settings: Settings = Depends(get_settings),
) -> None:
    """
    Let anyone read the reports; let nobody rewrite the data behind them.

    The deployed instance is public so the metrics can be inspected from the
    link alone. That same link would otherwise let any passer-by overwrite the
    dataset those metrics describe, so ingestion sits behind a shared key.

    This fails closed. With no key configured the write endpoints refuse
    outright instead of quietly falling back to open access, because the
    failure mode of the opposite choice is an unprotected production service.
    """
    expected = settings.api_key
    if not expected:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API_KEY is not configured, so write endpoints are disabled",
        )

    # Constant-time comparison: a plain == leaks how much of the key matched.
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail=f"missing or invalid {API_KEY_HEADER} header",
        )
