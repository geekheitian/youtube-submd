from typing import Any, Optional

try:
    from celery import Task
    from workers.celery_app import create_celery_app

    _CELERY_ERROR = None
except Exception as e:
    Task = Any
    create_celery_app = None
    _CELERY_ERROR = e


def dispatch_transcript_job(
    job_id: str, video_id: str, source_url: str
) -> Optional[Any]:
    if create_celery_app is None:
        return None
    from workers.tasks_impl import process_transcript_task

    celery_app = create_celery_app()
    celery_app.send_task(
        "workers.tasks.process_transcript",
        args=[job_id, video_id, source_url],
        queue="youtube-submd",
    )
    return job_id


def dispatch_summary_job(job_id: str, video_id: str, source_url: str) -> Optional[Any]:
    if create_celery_app is None:
        return None
    celery_app = create_celery_app()
    celery_app.send_task(
        "workers.tasks.process_summary",
        args=[job_id, video_id, source_url],
        queue="youtube-submd",
    )
    return job_id
