from __future__ import annotations

from typing import Any, Optional

from config import RuntimeConfig, load_runtime_config

try:
    from celery import Celery
except ModuleNotFoundError:
    Celery = Any
    _CELERY_IMPORT_ERROR = True
else:
    _CELERY_IMPORT_ERROR = False


def create_celery_app(config: Optional[RuntimeConfig] = None) -> Any:
    if _CELERY_IMPORT_ERROR:
        raise RuntimeError(
            "Celery is not installed. Install project dependencies from pyproject.toml first."
        )
    runtime = config or load_runtime_config(require_backends=True)
    celery_app = Celery(
        "youtube_submd",
        broker=runtime.redis_url,
        backend=runtime.redis_url,
        include=["workers.tasks_impl"],
    )
    celery_app.conf.update(
        task_default_queue="youtube-submd",
        task_ignore_result=False,
        result_expires=runtime.result_ttl_days * 24 * 60 * 60,
    )
    return celery_app


celery_app = None if _CELERY_IMPORT_ERROR else create_celery_app(load_runtime_config())
