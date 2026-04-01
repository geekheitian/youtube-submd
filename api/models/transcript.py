from typing import Literal, Optional

from pydantic import BaseModel, Field


class TranscriptCreateRequest(BaseModel):
    video_id: Optional[str] = Field(
        None, description="YouTube video ID (e.g. dQw4w9WgXcQ)"
    )
    url: Optional[str] = Field(None, description="Full YouTube video URL")

    def normalized_video_id(self) -> str:
        if self.video_id:
            return self.video_id.strip()
        if self.url:
            return _extract_video_id(self.url)
        raise ValueError("Either video_id or url must be provided")


class TranscriptResponse(BaseModel):
    video_id: str
    title: str
    language: str
    content: str
    source_url: str


class JobResponse(BaseModel):
    job_id: str
    task_type: str
    status: str
    video_id: str
    source_url: str
    created_at: str
    updated_at: str
    result: Optional[dict] = None
    error: Optional[dict] = None


def _extract_video_id(url: str) -> str:
    import re

    patterns = [
        r"(?:v=|/v/)([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/embed/([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    raise ValueError(f"Cannot extract video ID from: {url}")
