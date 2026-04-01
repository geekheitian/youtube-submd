from typing import Optional

from pydantic import BaseModel, Field


class SummaryCreateRequest(BaseModel):
    video_id: Optional[str] = Field(None, description="YouTube video ID")
    url: Optional[str] = Field(None, description="Full YouTube video URL")

    def normalized_video_id(self) -> str:
        if self.video_id:
            return self.video_id.strip()
        if self.url:
            from api.models.transcript import _extract_video_id

            return _extract_video_id(self.url)
        raise ValueError("Either video_id or url must be provided")


class SummaryResponse(BaseModel):
    video_id: str
    title: str
    provider: str
    summary: str
    source_url: str
