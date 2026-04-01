"""Shared configuration types and defaults.

This module contains the core configuration dataclasses and constants used by
both the CLI tool (youtumd.py) and the API services.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Re-export load_dotenv from config.runtime to avoid duplication
from config.runtime import load_dotenv

# =============================================================================
# Default Constants
# =============================================================================

DEFAULT_CHANNEL = "https://www.youtube.com/@BestPartners/videos"
DEFAULT_CHANNEL_NAME = "BestPartners"
DEFAULT_LIMIT = 10
DEFAULT_BASE_DIR = Path("/Users/yangkai/Nutstore Files/mba/obsidian/第二大脑")
DEFAULT_CONTENT_SUBDIR = "01-内容"
DEFAULT_MINIMAX_BASE_URL = "https://api.minimax.chat/v1"
DEFAULT_MINIMAX_MODEL = "MiniMax-M2.7"

# ASR defaults (also referenced by libs.transcript)
DEFAULT_ASR_BROWSER_EXECUTABLE = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DEFAULT_ASR_MODEL = "small"
DEFAULT_ASR_CAPTURE_SECONDS = 45
DEFAULT_ASR_WARMUP_SECONDS = 3
DEFAULT_ASR_MAX_SECONDS = 1800
DEFAULT_ASR_NAVIGATION_TIMEOUT_SECONDS = 60
DEFAULT_ASR_CAPTURE_RETRIES = 2
DEFAULT_ASR_NETWORK_TIMEOUT_SECONDS = 15


# =============================================================================
# Configuration Dataclasses
# =============================================================================

@dataclass(frozen=True)
class AppConfig:
    """Application-level configuration with environment variable overrides."""

    base_dir: Path
    content_subdir: str
    default_channel_url: str
    default_channel_name: str
    default_limit: int
    minimax_base_url: str
    minimax_model: str

    @property
    def content_root(self) -> Path:
        return self.base_dir / self.content_subdir


@dataclass(frozen=True)
class ChannelContext:
    """Encapsulates channel-level paths and display metadata."""

    url: str
    name: str
    content_root: Path

    @property
    def display_name(self) -> str:
        if self.name.startswith('@'):
            return self.name
        return f"@{self.name}"

    @property
    def channel_dir(self) -> Path:
        return self.content_root / self.name

    @property
    def subtitles_dir(self) -> Path:
        return self.channel_dir / "字幕"

    @property
    def summaries_dir(self) -> Path:
        return self.channel_dir / "摘要"

    @property
    def tag_name(self) -> str:
        return self.name


@dataclass(frozen=True)
class SubtitleOption:
    """Represents a downloadable subtitle option."""

    code: str
    is_auto: bool = False


# =============================================================================
# Helper Functions
# =============================================================================

def sanitize_filename(name: str, max_length: int = 50) -> str:
    """Clean illegal characters from filename."""
    return re.sub(r'[<>:"/\\|?*]', '_', name)[:max_length]


def get_env_path(name: str, default: Path) -> Path:
    """Read a path from environment variable, fallback to default."""
    raw = os.environ.get(name, '').strip()
    return Path(raw).expanduser() if raw else default


def get_env_int(name: str, default: int) -> int:
    """Read an integer from environment variable, fallback to default on bad value."""
    raw = os.environ.get(name, '').strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def get_video_dates(upload_date: str) -> Dict[str, str]:
    """Return video publish date in compact/dash formats; fallback to now if missing."""
    cleaned = (upload_date or '').strip()
    if re.fullmatch(r'\d{8}', cleaned):
        date_obj = datetime.strptime(cleaned, "%Y%m%d")
        return {
            'compact': date_obj.strftime("%Y%m%d"),
            'display': date_obj.strftime("%Y-%m-%d"),
        }
    now = datetime.now()
    return {
        'compact': now.strftime("%Y%m%d"),
        'display': now.strftime("%Y-%m-%d"),
    }


def get_channel_name(channel_url: str, default_channel_name: str = DEFAULT_CHANNEL_NAME) -> str:
    """Extract channel name from YouTube URL."""
    patterns = [
        r'/@([^/?#]+)',
        r'/channel/([^/?#]+)',
        r'/c/([^/?#]+)',
        r'/user/([^/?#]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, channel_url)
        if match:
            return sanitize_filename(match.group(1), max_length=80)
    return default_channel_name


def build_channel_context(
    channel_url: str,
    config: AppConfig,
    override_name: Optional[str] = None,
) -> ChannelContext:
    """Build channel context from URL and config."""
    name = override_name or get_channel_name(channel_url, default_channel_name=config.default_channel_name)
    return ChannelContext(
        url=channel_url,
        name=name,
        content_root=config.content_root,
    )


def load_config() -> AppConfig:
    """Load application configuration from environment variables."""
    return AppConfig(
        base_dir=get_env_path('YTSUBMD_BASE_DIR', DEFAULT_BASE_DIR),
        content_subdir=os.environ.get('YTSUBMD_CONTENT_SUBDIR', DEFAULT_CONTENT_SUBDIR).strip() or DEFAULT_CONTENT_SUBDIR,
        default_channel_url=os.environ.get('YTSUBMD_DEFAULT_CHANNEL_URL', DEFAULT_CHANNEL).strip() or DEFAULT_CHANNEL,
        default_channel_name=os.environ.get('YTSUBMD_DEFAULT_CHANNEL_NAME', DEFAULT_CHANNEL_NAME).strip() or DEFAULT_CHANNEL_NAME,
        default_limit=int(os.environ.get('YTSUBMD_DEFAULT_LIMIT', str(DEFAULT_LIMIT)).strip() or DEFAULT_LIMIT),
        minimax_base_url=os.environ.get('MINIMAX_BASE_URL', DEFAULT_MINIMAX_BASE_URL).strip() or DEFAULT_MINIMAX_BASE_URL,
        minimax_model=os.environ.get('MINIMAX_MODEL', DEFAULT_MINIMAX_MODEL).strip() or DEFAULT_MINIMAX_MODEL,
    )


def find_existing_summary(video_id: str, context: ChannelContext) -> Optional[Path]:
    """Check if a video has already been processed by looking for source metadata."""
    expected_source = f"source: https://www.youtube.com/watch?v={video_id}"
    for summary_file in context.summaries_dir.glob("*.md"):
        try:
            with open(summary_file, 'r', encoding='utf-8') as handle:
                for line in handle:
                    if line.strip() == expected_source:
                        return summary_file
        except OSError as error:
            print(f"   ⚠️ 读取已有摘要失败: {summary_file.name} - {error}")
    return None


def find_existing_subtitle(video_id: str, context: ChannelContext) -> Optional[Path]:
    """Check if a video subtitle already exists by looking for source metadata."""
    expected_source = f"source: https://www.youtube.com/watch?v={video_id}"
    for subtitle_file in context.subtitles_dir.glob("*.md"):
        try:
            with open(subtitle_file, 'r', encoding='utf-8') as handle:
                for line in handle:
                    if line.strip() == expected_source:
                        return subtitle_file
        except OSError as error:
            print(f"   ⚠️ 读取已有字幕失败: {subtitle_file.name} - {error}")
    return None


def choose_subtitle_option(options: List[SubtitleOption]) -> Optional[SubtitleOption]:
    """Select the best subtitle from available options (zh-Hans > zh-Hant > en)."""
    preferred_prefixes = ("zh-Hans", "zh-Hant", "en")

    def sort_key(option: SubtitleOption) -> Tuple[int, int, int]:
        for index, prefix in enumerate(preferred_prefixes):
            if option.code == prefix:
                return (index, 0, 1 if option.is_auto else 0)
            if option.code.startswith(f"{prefix}-"):
                return (index, 1, 1 if option.is_auto else 0)
        return (len(preferred_prefixes), 99, 1 if option.is_auto else 0)

    available = sorted(options, key=sort_key)
    return available[0] if available else None
