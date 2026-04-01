import hashlib
from typing import Optional

from fastapi import Request, HTTPException, status
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from config import RuntimeConfig
from storage import get_session
from storage.keys import verify_api_key
from storage.models import ApiKey


_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _get_api_key_from_request(request: Request) -> Optional[str]:
    auth_header = request.headers.get("X-API-Key", "")
    if auth_header:
        return auth_header
    query_key = request.query_params.get("api_key", "")
    return query_key


async def require_api_key(
    request: Request,
    runtime: RuntimeConfig,
) -> ApiKey:
    raw_key = _get_api_key_from_request(request)
    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Missing API key", "code": "unauthorized"},
        )

    for session in get_session():
        api_key = verify_api_key(session, raw_key)
        if api_key is not None:
            return api_key

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": "Invalid or inactive API key", "code": "unauthorized"},
    )
