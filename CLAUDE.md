# CLAUDE

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Directory Context

This is the `04-工具/` (Tools) directory within the larger **第二大脑** (Second Brain) Obsidian system. The parent directory contains a comprehensive `CLAUDE.md` with system-wide rules. This file focuses on the tools in this directory.

## Tools Overview

### youtumd - YouTube Video Summary Tool

**Purpose**: Automate fetching YouTube channel videos, extract subtitles, generate AI summaries, and store in Obsidian.

**Main file**: `youtumd.py`

**Usage**:
```bash
# Default: process 10 videos
python3 youtumd.py

# Preview mode (no subtitle download)
python3 youtumd.py --dry-run

# Process specific number
python3 youtumd.py --limit 5

# Other channel
python3 youtumd.py --channel "https://www.youtube.com/@其他频道/videos"

# Force reprocess
python3 youtumd.py --force
```

**Dependencies**:
- `yt-dlp` - YouTube video downloading
- `dashscope` - Title translation (Qwen)
- `MINIMAX_API_KEY` - For enhanced summary generation (optional)

**Output locations**:
- Subtitles: `01-内容/BestPartners/字幕/`
- Summaries: `01-内容/BestPartners/摘要/`

## Shell Scripts

- `youtumd.sh` - Wrapper script for the tool
- `run_youtumd.sh` - Another wrapper

## Directory Structure

```
youtumd/
├── youtumd.py                 # Main Python tool
├── youtumd.sh                 # Shell wrapper
├── run_youtumd.sh            # Alternative wrapper
└── youtumd_README.md         # Detailed documentation
```

## Key Implementation Details

1. **Video fetching**: Uses `yt-dlp --flat-playlist` to get video list
2. **Subtitle priority**: zh-Hans > zh-Hant > en
3. **File naming**: `{中文标题}-{YYYYMMDD}.md` (illegal chars sanitized)
4. **Duplicate check**: Skips videos already in summary directory by video_id
5. **Title translation**: Uses DashScope Qwen API (optional, falls back to original title)

## Code Architecture

```
youtumd.py
├── get_channel_videos()      # Fetch video list from channel
├── get_available_subtitles()  # Check available subtitle languages
├── download_subtitle()       # Download VTT subtitle
├── read_subtitle()           # Parse VTT to plain text
├── convert_subtitle_to_md()  # Convert to Markdown format
├── translate_to_chinese()    # Translate title via API
├── generate_summary()         # AI summary generation
├── save_summary()             # Write to file
└── process_video()           # Orchestrate single video processing
```

## Important Notes

- The tool is configured with absolute paths pointing to the parent directory
- API keys are loaded from environment variables (`DASHSCOPE_API_KEY`, `MINIMAX_API_KEY`)
- The tool automatically creates output directories if they don't exist
- Run from any directory - paths are absolute

## Related Documentation

For system-wide rules (FATAL rules, memory system, task management, etc.), see the parent directory's `CLAUDE.md`.
