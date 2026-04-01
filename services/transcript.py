"""YouTube transcript service - thin wrapper over libs.transcript."""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from libs.config import AppConfig, SubtitleOption, choose_subtitle_option
from libs.transcript import (
    build_cookie_args,
    cleanup_downloaded_subtitle,
    get_available_subtitles,
    prepare_subtitle_text,
)


@dataclass(frozen=True)
class TranscriptResult:
    video_id: str
    title: str
    language: str
    content: str
    source_url: str


def _run_command(cmd: List[str], timeout: int = 120) -> str:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            return ""
        return result.stdout
    except Exception:
        return ""


def _get_video_info(
    video_id: str,
    cookies_file: Optional[str] = None,
    cookies_from_browser: Optional[str] = None,
) -> Tuple[str, str]:
    cmd = [
        "yt-dlp",
        *build_cookie_args(cookies_file, cookies_from_browser),
        "--print",
        "%(title)s|%(upload_date)s",
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    output = _run_command(cmd)
    if not output:
        return "", ""
    parts = output.strip().split("|")
    title = parts[0].strip() if parts else ""
    upload_date = parts[1].strip() if len(parts) > 1 else ""
    return title, upload_date


def _download_subtitle(
    video_id: str,
    option: SubtitleOption,
    cookies_file: Optional[str] = None,
    cookies_from_browser: Optional[str] = None,
    retries: int = 2,
) -> Optional[str]:
    """Download subtitle to temp dir (used by API service, not CLI)."""
    import tempfile
    import time as _time

    work_dir = Path(tempfile.gettempdir()) / "ytsubmd-subs"
    work_dir.mkdir(parents=True, exist_ok=True)

    for attempt in range(retries + 1):
        cmd = [
            "yt-dlp",
            *build_cookie_args(cookies_file, cookies_from_browser),
            "--write-auto-subs" if option.is_auto else "--write-subs",
            "--sub-lang",
            option.code,
            "--skip-download",
            "-o",
            str(work_dir / video_id),
            f"https://www.youtube.com/watch?v={video_id}",
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
            )
        except subprocess.TimeoutExpired:
            continue
        except Exception:
            return None

        output = f"{result.stdout}\n{result.stderr}"
        if result.returncode == 0 and "Writing video subtitles" in output:
            for f in work_dir.glob(f"{video_id}.*.vtt"):
                return str(f)

        if "HTTP Error 429" in output and attempt < retries:
            _time.sleep(attempt + 2)
            continue
        break

    return None


class YouTubeTranscriptService:
    def __init__(self, config: Optional[AppConfig] = None):
        self._config = config

    def get_video_info(
        self,
        video_id: str,
        cookies_file: Optional[str] = None,
        cookies_from_browser: Optional[str] = None,
    ) -> Tuple[str, str]:
        return _get_video_info(video_id, cookies_file, cookies_from_browser)

    def get_available_subtitles(
        self,
        video_id: str,
        cookies_file: Optional[str] = None,
        cookies_from_browser: Optional[str] = None,
    ) -> List[SubtitleOption]:
        return get_available_subtitles(video_id, cookies_file, cookies_from_browser)

    def choose_subtitle_option(
        self, options: List[SubtitleOption]
    ) -> Optional[SubtitleOption]:
        return choose_subtitle_option(options)

    def download_and_read_subtitle(
        self,
        video_id: str,
        option: SubtitleOption,
        cookies_file: Optional[str] = None,
        cookies_from_browser: Optional[str] = None,
    ) -> Optional[str]:
        subtitle_path = _download_subtitle(
            video_id, option, cookies_file, cookies_from_browser
        )
        if not subtitle_path:
            return None
        try:
            text = prepare_subtitle_text(subtitle_path)
            return text if text else None
        finally:
            cleanup_downloaded_subtitle(subtitle_path)

    def get_transcript(
        self,
        video_id: str,
        cookies_file: Optional[str] = None,
        cookies_from_browser: Optional[str] = None,
    ) -> Optional[TranscriptResult]:
        title, _ = self.get_video_info(video_id, cookies_file, cookies_from_browser)
        if not title:
            return None

        options = self.get_available_subtitles(
            video_id, cookies_file, cookies_from_browser
        )
        if not options:
            return None

        chosen = self.choose_subtitle_option(options)
        if not chosen:
            return None

        content = self.download_and_read_subtitle(
            video_id, chosen, cookies_file, cookies_from_browser
        )
        if not content:
            return None

        return TranscriptResult(
            video_id=video_id,
            title=title,
            language=chosen.code,
            content=content,
            source_url=f"https://www.youtube.com/watch?v={video_id}",
        )
