import json
import logging
from typing import Any

from api.models.status import JobStatus
from config import RuntimeConfig, load_runtime_config
from services.transcript import YouTubeTranscriptService
from services.summary import YouTubeSummaryService, SummaryResult
from storage import get_session
from storage.jobs import update_job_result
from storage.models import Job

logger = logging.getLogger(__name__)


def process_transcript(job_id: str, video_id: str, source_url: str) -> dict:
    config = load_runtime_config(require_backends=True)
    svc = YouTubeTranscriptService()

    session_gen = get_session()
    session = next(session_gen)

    try:
        update_job_result(session, _get_job(session, job_id), JobStatus.PROCESSING)

        result = svc.get_transcript(video_id)
        if result is None:
            update_job_result(
                session,
                _get_job(session, job_id),
                JobStatus.FAILED,
                error_code="subtitle-unavailable",
                error_detail="No subtitles available for this video",
            )
            return {"status": "failed", "error": "subtitle-unavailable"}

        update_job_result(
            session,
            _get_job(session, job_id),
            JobStatus.SUCCEEDED,
            result_data={
                "video_id": result.video_id,
                "title": result.title,
                "language": result.language,
                "content": result.content,
                "source_url": result.source_url,
            },
        )
        return {"status": "succeeded", "video_id": video_id}
    except Exception as exc:
        logger.exception("Transcript job %s failed: %s", job_id, exc)
        update_job_result(
            session,
            _get_job(session, job_id),
            JobStatus.FAILED,
            error_code="internal-error",
            error_detail=str(exc),
        )
        return {"status": "failed", "error": "internal-error"}


def process_summary(job_id: str, video_id: str, source_url: str) -> dict:
    config = load_runtime_config(require_backends=True)

    session_gen = get_session()
    session = next(session_gen)

    try:
        update_job_result(session, _get_job(session, job_id), JobStatus.PROCESSING)

        from services.transcript import YouTubeTranscriptService
        from youtumd import AppConfig
        from pathlib import Path

        app_config = AppConfig(
            base_dir=Path(config.project_root),
            content_subdir="content",
            default_channel_url="https://www.youtube.com",
            default_channel_name="api",
            default_limit=10,
            minimax_base_url="https://api.minimax.chat/v1",
            minimax_model="MiniMax-M2.7",
        )

        transcript_svc = YouTubeTranscriptService()
        transcript_result = transcript_svc.get_transcript(video_id)

        if transcript_result is None:
            update_job_result(
                session,
                _get_job(session, job_id),
                JobStatus.FAILED,
                error_code="subtitle-unavailable",
                error_detail="Cannot generate summary: no subtitles available",
            )
            return {"status": "failed", "error": "subtitle-unavailable"}

        summary_svc = YouTubeSummaryService(app_config)
        summary_result = summary_svc.generate_summary(
            transcript_result.title, video_id, transcript_result.content
        )

        update_job_result(
            session,
            _get_job(session, job_id),
            JobStatus.SUCCEEDED,
            result_data={
                "video_id": summary_result.video_id,
                "title": summary_result.title,
                "provider": summary_result.provider,
                "summary": summary_result.summary,
                "source_url": summary_result.source_url,
            },
        )
        return {"status": "succeeded", "video_id": video_id}
    except ValueError as exc:
        logger.exception("Summary job %s failed (no provider): %s", job_id, exc)
        update_job_result(
            session,
            _get_job(session, job_id),
            JobStatus.FAILED,
            error_code="summary-provider-unavailable",
            error_detail=str(exc),
        )
        return {"status": "failed", "error": "summary-provider-unavailable"}
    except Exception as exc:
        logger.exception("Summary job %s failed: %s", job_id, exc)
        update_job_result(
            session,
            _get_job(session, job_id),
            JobStatus.FAILED,
            error_code="internal-error",
            error_detail=str(exc),
        )
        return {"status": "failed", "error": "internal-error"}


def _get_job(session, job_id: str) -> Job:
    from uuid import UUID

    return session.query(Job).filter(Job.id == UUID(job_id)).first()
