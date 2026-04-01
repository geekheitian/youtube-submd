"""Subtitle download via yt-dlp."""

import subprocess
import time
from pathlib import Path
from typing import List, Optional

from libs.config import ChannelContext, SubtitleOption
from libs.transcript.cookie import build_cookie_args


def download_subtitle(
    video_id: str,
    context: ChannelContext,
    option: SubtitleOption,
    cookies_file: Optional[str] = None,
    cookies_from_browser: Optional[str] = None,
    retries: int = 2,
) -> Optional[str]:
    """Download subtitle via yt-dlp, with lightweight retry on 429."""
    print(f"   ⬇️ 下载字幕: {option.code}")

    for attempt in range(retries + 1):
        cmd = [
            "yt-dlp",
            *build_cookie_args(cookies_file, cookies_from_browser),
            "--write-auto-subs" if option.is_auto else "--write-subs",
            "--sub-lang", option.code,
            "--skip-download",
            "-o", str(context.subtitles_dir / f"{video_id}"),
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
            print(f"   ⚠️ 字幕下载超时（第 {attempt + 1} 次）")
            continue
        except Exception as error:
            print(f"   ⚠️ 字幕下载异常: {error}")
            return None

        output = f"{result.stdout}\n{result.stderr}"
        if result.returncode == 0 and "Writing video subtitles" in output:
            for f in context.subtitles_dir.glob(f"{video_id}.*.vtt"):
                return str(f)

        if "HTTP Error 429" in output and attempt < retries:
            wait_seconds = attempt + 2
            print(f"   ⚠️ YouTube 限流（429），{wait_seconds} 秒后重试")
            time.sleep(wait_seconds)
            continue

        break

    return None
