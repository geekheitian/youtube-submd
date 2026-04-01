import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError

from api.auth.dependencies import require_api_key
from api.errors.responses import ErrorResponse
from api.models import (
    JobResponse,
    SummaryCreateRequest,
    _extract_video_id,
)
from api.models.status import JobStatus
from config import RuntimeConfig
from storage import get_session
from storage.jobs import create_job, find_active_job, find_succeeded_job
from storage.models import ApiKey
from workers.tasks import dispatch_summary_job

router = APIRouter(prefix="/api/v1/youtube", tags=["youtube"])


@router.post(
    "/summaries",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
)
async def create_summary(
    request: Request,
    body: SummaryCreateRequest,
    api_key: Annotated[ApiKey, Depends(require_api_key)],
    runtime: Annotated[RuntimeConfig, None] = None,
):
    if not body.video_id and not body.url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Either video_id or url must be provided",
                "code": "invalid-youtube-url",
            },
        )

    try:
        video_id = body.normalized_video_id()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Cannot extract video ID from URL",
                "code": "invalid-youtube-url",
            },
        )

    source_url = f"https://www.youtube.com/watch?v={video_id}"

    for session in get_session():
        existing = find_active_job(session, "summary", video_id)
        if existing:
            return JobResponse(
                job_id=str(existing.id),
                task_type=existing.task_type,
                status=existing.status.value,
                video_id=existing.video_id,
                source_url=existing.source_url,
                created_at=existing.created_at.isoformat(),
                updated_at=existing.updated_at.isoformat(),
            )

        for session in get_session():
            succeeded = find_succeeded_job(
                session,
                "summary",
                video_id,
                ttl_days=runtime.result_ttl_days if runtime else 7,
            )
            if succeeded:
                import json

                result_data = (
                    json.loads(succeeded.result_data) if succeeded.result_data else None
                )
                return JobResponse(
                    job_id=str(succeeded.id),
                    task_type=succeeded.task_type,
                    status=succeeded.status.value,
                    video_id=succeeded.video_id,
                    source_url=succeeded.source_url,
                    created_at=succeeded.created_at.isoformat(),
                    updated_at=succeeded.updated_at.isoformat(),
                    result=result_data,
                )

        job = create_job(session, "summary", video_id, source_url, api_key)
        dispatch_summary_job(str(job.id), video_id, source_url)
        return JobResponse(
            job_id=str(job.id),
            task_type=job.task_type,
            status=job.status.value,
            video_id=job.video_id,
            source_url=job.source_url,
            created_at=job.created_at.isoformat(),
            updated_at=job.updated_at.isoformat(),
        )
