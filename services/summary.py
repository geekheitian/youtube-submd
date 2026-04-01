"""YouTube summary service - thin wrapper over libs.ai."""

from dataclasses import dataclass
from typing import Optional

from libs.ai import (
    call_minimax,
    generate_summary_with_dashscope,
    generate_summary_with_minimax,
    sanitize_summary_text,
)
from libs.config import AppConfig


@dataclass(frozen=True)
class SummaryResult:
    video_id: str
    title: str
    provider: str
    summary: str
    source_url: str


class YouTubeSummaryService:
    def __init__(self, config: AppConfig):
        self._config = config

    def generate_summary(
        self, title: str, video_id: str, subtitle_text: str
    ) -> SummaryResult:
        summary_text = generate_summary_with_minimax(
            title, subtitle_text, self._config
        )
        provider = "MiniMax"

        if not summary_text:
            summary_text = generate_summary_with_dashscope(subtitle_text)
            provider = "DashScope"

        if not summary_text:
            raise ValueError(f"No summary provider available for video {video_id}")

        return SummaryResult(
            video_id=video_id,
            title=title,
            provider=provider,
            summary=summary_text,
            source_url=f"https://www.youtube.com/watch?v={video_id}",
        )
