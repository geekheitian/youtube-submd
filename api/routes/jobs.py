import json
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from api.auth.dependencies import require_api_key
from api.errors.responses import ErrorResponse
from api.models import JobResponse
from api.models.status import JobStatus
from config import RuntimeConfig
from storage import get_session
from storage.models import ApiKey, Job

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get(
    "/{job_id}",
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def get_job(
    job_id: str,
    api_key: Annotated[ApiKey, Depends(require_api_key)],
):
    try:
        uid = UUID(job_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Invalid job ID format", "code": "job-not-found"},
        )

    for session in get_session():
        job = (
            session.query(Job)
            .filter(Job.id == uid, Job.api_key_id == api_key.id)
            .first()
        )
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "Job not found", "code": "job-not-found"},
            )

        result_data = None
        if job.result_data:
            try:
                result_data = json.loads(job.result_data)
            except json.JSONDecodeError:
                result_data = {"raw": job.result_data}

        error_data = None
        if job.error_code:
            error_data = {"code": job.error_code, "detail": job.error_detail}

        return JobResponse(
            job_id=str(job.id),
            task_type=job.task_type,
            status=job.status.value,
            video_id=job.video_id,
            source_url=job.source_url,
            created_at=job.created_at.isoformat(),
            updated_at=job.updated_at.isoformat(),
            result=result_data,
            error=error_data,
        )
