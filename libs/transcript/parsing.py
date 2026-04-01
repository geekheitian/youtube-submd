"""Subtitle availability parsing and discovery."""

from typing import List, Optional

from libs.config import SubtitleOption
from libs.transcript._utils import run_command
from libs.transcript.cookie import build_cookie_args


def parse_available_subtitles(output: str) -> List[SubtitleOption]:
    """Parse yt-dlp --list-subs output to extract available subtitle options."""
    options: List[SubtitleOption] = []
    current_section: Optional[str] = None
    in_table = False

    for raw_line in output.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("[info] Available subtitles"):
            current_section = "manual"
            in_table = False
            continue
        if stripped.startswith("[info] Available automatic captions"):
            current_section = "auto"
            in_table = False
            continue
        if current_section and stripped.startswith("Language"):
            in_table = True
            continue
        if not current_section or not in_table or stripped.startswith("["):
            continue

        code = stripped.split()[0]
        option = SubtitleOption(code=code, is_auto=(current_section == "auto"))
        if option not in options:
            options.append(option)

    return options


def get_available_subtitles(
    video_id: str,
    cookies_file: Optional[str] = None,
    cookies_from_browser: Optional[str] = None,
) -> List[SubtitleOption]:
    """Check available subtitles for a video via yt-dlp."""
    cmd = [
        "yt-dlp",
        *build_cookie_args(cookies_file, cookies_from_browser),
        "--list-subs",
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    output = run_command(cmd)
    if not output:
        return []
    return parse_available_subtitles(output)
