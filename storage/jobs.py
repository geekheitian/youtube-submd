import json
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from api.models.status import JobStatus
from storage.models import ApiKey, Job


def _make_idempotency_key(task_type: str, video_id: str) -> str:
    return f"{task_type}:{video_id.strip()}"


def find_job_by_idempotency(
    session: Session,
    task_type: str,
    video_id: str,
) -> Optional[Job]:
    key = _make_idempotency_key(task_type, video_id)
    return session.query(Job).filter(Job.idempotency_key == key).first()


def find_active_job(
    session: Session,
    task_type: str,
    video_id: str,
) -> Optional[Job]:
    key = _make_idempotency_key(task_type, video_id)
    return (
        session.query(Job)
        .filter(
            Job.idempotency_key == key,
            Job.status.in_([JobStatus.PENDING, JobStatus.PROCESSING]),
        )
        .first()
    )


def find_succeeded_job(
    session: Session,
    task_type: str,
    video_id: str,
    ttl_days: int = 7,
) -> Optional[Job]:
    from datetime import timedelta

    cutoff = datetime.utcnow() - timedelta(days=ttl_days)
    key = _make_idempotency_key(task_type, video_id)
    return (
        session.query(Job)
        .filter(
            Job.idempotency_key == key,
            Job.status == JobStatus.SUCCEEDED,
            Job.updated_at >= cutoff,
        )
        .first()
    )


def create_job(
    session: Session,
    task_type: str,
    video_id: str,
    source_url: str,
    api_key: ApiKey,
) -> Job:
    idempotency_key = _make_idempotency_key(task_type, video_id)
    job = Job(
        id=uuid.uuid4(),
        task_type=task_type,
        status=JobStatus.PENDING,
        video_id=video_id,
        source_url=source_url,
        idempotency_key=idempotency_key,
        api_key_id=api_key.id,
    )
    session.add(job)
    session.commit()
    return job


def update_job_result(
    session: Session,
    job: Job,
    status: JobStatus,
    result_data: Optional[dict] = None,
    error_code: Optional[str] = None,
    error_detail: Optional[str] = None,
) -> Job:
    job.status = status
    job.updated_at = datetime.utcnow()
    if result_data is not None:
        job.result_data = json.dumps(result_data)
    if error_code is not None:
        job.error_code = error_code
    if error_detail is not None:
        job.error_detail = error_detail
    session.commit()
    return job
