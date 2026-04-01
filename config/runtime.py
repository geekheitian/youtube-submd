from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_API_HOST = "127.0.0.1"
DEFAULT_API_PORT = 8000
DEFAULT_DATABASE_URL = "postgresql+psycopg://localhost:5432/youtube_submd"
DEFAULT_REDIS_URL = "redis://localhost:6379/0"
DEFAULT_API_KEY_HEADER = "X-API-Key"
DEFAULT_RESULT_TTL_DAYS = 7
DEFAULT_CREATE_RATE_LIMIT_PER_MINUTE = 10
DEFAULT_READ_RATE_LIMIT_PER_MINUTE = 60


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeConfig:
    environment: str
    api_host: str
    api_port: int
    database_url: str
    redis_url: str
    api_key_header: str
    result_ttl_days: int
    create_rate_limit_per_minute: int
    read_rate_limit_per_minute: int
    project_root: Path


def load_dotenv(dotenv_path: Optional[Path] = None) -> None:
    candidates = []
    if dotenv_path:
        candidates.append(dotenv_path)
    candidates.append(PROJECT_ROOT / ".env")
    candidates.append(Path.cwd() / ".env")

    for path in candidates:
        if not path.is_file():
            continue
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, _, value = stripped.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
        break


def _get_env(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


def _get_env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as error:
        raise ConfigError(f"Environment variable {name} must be an integer") from error


def load_runtime_config(
    *,
    dotenv_path: Optional[Path] = None,
    require_backends: bool = False,
) -> RuntimeConfig:
    load_dotenv(dotenv_path)

    database_url = _get_env("DATABASE_URL", DEFAULT_DATABASE_URL)
    redis_url = _get_env("REDIS_URL", DEFAULT_REDIS_URL)

    if require_backends:
        missing = []
        if os.environ.get("DATABASE_URL", "").strip() == "":
            missing.append("DATABASE_URL")
        if os.environ.get("REDIS_URL", "").strip() == "":
            missing.append("REDIS_URL")
        if missing:
            joined = ", ".join(missing)
            raise ConfigError(
                f"Missing required runtime environment variables: {joined}"
            )

    return RuntimeConfig(
        environment=_get_env("YTSUBMD_ENV", "development"),
        api_host=_get_env("API_HOST", DEFAULT_API_HOST),
        api_port=_get_env_int("API_PORT", DEFAULT_API_PORT),
        database_url=database_url,
        redis_url=redis_url,
        api_key_header=_get_env("API_KEY_HEADER", DEFAULT_API_KEY_HEADER),
        result_ttl_days=_get_env_int("RESULT_TTL_DAYS", DEFAULT_RESULT_TTL_DAYS),
        create_rate_limit_per_minute=_get_env_int(
            "CREATE_RATE_LIMIT_PER_MINUTE",
            DEFAULT_CREATE_RATE_LIMIT_PER_MINUTE,
        ),
        read_rate_limit_per_minute=_get_env_int(
            "READ_RATE_LIMIT_PER_MINUTE",
            DEFAULT_READ_RATE_LIMIT_PER_MINUTE,
        ),
        project_root=PROJECT_ROOT,
    )


def main() -> int:
    try:
        load_runtime_config(require_backends=True)
    except ConfigError as error:
        print(error, file=os.sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
