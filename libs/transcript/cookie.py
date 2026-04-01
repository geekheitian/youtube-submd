"""Build yt-dlp cookie arguments."""

from pathlib import Path
from typing import List, Optional


def build_cookie_args(
    cookies_file: Optional[str],
    cookies_from_browser: Optional[str],
) -> List[str]:
    """Build yt-dlp cookie arguments."""
    if cookies_file:
        return ["--cookies", str(Path(cookies_file).expanduser())]
    if cookies_from_browser:
        return ["--cookies-from-browser", cookies_from_browser]
    return []
