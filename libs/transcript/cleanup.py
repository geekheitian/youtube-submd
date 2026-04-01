"""Subtitle text preparation and cleanup."""

from pathlib import Path
from typing import List


def load_subtitle_file(subtitle_path: str) -> str:
    """Read raw subtitle file content."""
    try:
        with open(subtitle_path, 'r', encoding='utf-8') as handle:
            return handle.read()
    except OSError as error:
        print(f"   ❌ 读取字幕文件失败: {error}")
        return ""


def extract_subtitle_lines(vtt_content: str) -> List[str]:
    """Extract plain text lines from VTT content."""
    text_lines = []
    for line in vtt_content.split('\n'):
        if '-->' in line or line.startswith('WEBVTT') or line.startswith('Kind:') or line.startswith('Language:'):
            continue
        if line.isdigit():
            continue
        stripped = line.strip()
        if stripped:
            text_lines.append(stripped)
    return text_lines


def build_subtitle_text(text_lines: List[str], max_chars: int = 500000) -> str:
    """Merge subtitle lines into cleaned continuous text."""
    return ' '.join(text_lines)[:max_chars]


def prepare_subtitle_text(subtitle_path: str, max_chars: int = 500000) -> str:
    """Read VTT and produce cleaned subtitle text."""
    raw_content = load_subtitle_file(subtitle_path)
    if not raw_content:
        return ""
    text_lines = extract_subtitle_lines(raw_content)
    return build_subtitle_text(text_lines, max_chars=max_chars)


def cleanup_downloaded_subtitle(subtitle_path: str) -> None:
    """Delete temporary VTT file to avoid leaving artifacts in Obsidian dir."""
    try:
        Path(subtitle_path).unlink(missing_ok=True)
    except OSError as error:
        print(f"   ⚠️ 清理原始字幕失败: {error}")
