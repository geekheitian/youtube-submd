import hashlib
import time
from typing import Callable, Optional

try:
    import redis

    _REDIS_ERROR = None
except Exception:
    redis = None
    _REDIS_ERROR = True


RATE_LIMIT_WINDOW = 60


def _make_rate_limit_key(api_key_id: str, endpoint: str, action: str) -> str:
    return f"ratelimit:{api_key_id}:{endpoint}:{action}"


def check_rate_limit(
    redis_url: str,
    api_key_id: str,
    endpoint: str,
    action: str,
    limit_per_minute: int,
) -> tuple[bool, int]:
    if redis is None:
        return True, limit_per_minute

    try:
        r = redis.from_url(redis_url)
        key = _make_rate_limit_key(api_key_id, endpoint, action)
        now = int(time.time())
        window_start = now - RATE_LIMIT_WINDOW

        pipe = r.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, RATE_LIMIT_WINDOW)
        counts = pipe.execute()
        current_count = counts[2]

        if current_count > limit_per_minute:
            return False, limit_per_minute - current_count
        return True, limit_per_minute - current_count
    except Exception:
        return True, limit_per_minute


def rate_limit_middleware(redis_url: str, limit_create: int, limit_read: int):
    from fastapi import Request, HTTPException, status
    from starlette.middleware.base import BaseHTTPMiddleware

    class RateLimitMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: Callable):
            api_key = request.headers.get("X-API-Key", "")
            if not api_key:
                return await call_next(request)

            key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            api_key_id = key_hash[:16]

            path = request.url.path
            if path.startswith("/api/v1/youtube") and request.method == "POST":
                ok, remaining = check_rate_limit(
                    redis_url, api_key_id, path, "create", limit_create
                )
                if not ok:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={
                            "error": "Rate limit exceeded",
                            "code": "rate-limited",
                            "retry_after": RATE_LIMIT_WINDOW,
                        },
                    )
            elif path.startswith("/api/v1/jobs") and request.method == "GET":
                ok, remaining = check_rate_limit(
                    redis_url, api_key_id, path, "read", limit_read
                )
                if not ok:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={
                            "error": "Rate limit exceeded",
                            "code": "rate-limited",
                            "retry_after": RATE_LIMIT_WINDOW,
                        },
                    )

            return await call_next(request)

    return RateLimitMiddleware
