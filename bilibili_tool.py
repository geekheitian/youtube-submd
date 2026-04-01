#!/usr/bin/env python3
"""
Bilibili 空间字幕摘要工具

功能：
- 获取 Bilibili 空间最新视频
- 下载字幕（需 cookies 登录态）
- 生成结构化摘要
- 存储到 Obsidian

用法：
    python3 bilibili_tool.py
    python3 bilibili_tool.py --dry-run
    python3 bilibili_tool.py --limit 3
    python3 bilibili_tool.py --space-url "https://space.bilibili.com/50247550/video"
    python3 bilibili_tool.py --cookies-from-browser chrome
    python3 bilibili_tool.py --cookies-file ~/Downloads/bilibili.cookies.txt
"""

import argparse
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import youtumd as shared


DEFAULT_SPACE_URL = "https://space.bilibili.com/50247550/video"
DEFAULT_SPACE_NAME = "清华姜学长"
DEFAULT_LIMIT = 5
VIDEO_URL_TEMPLATE = "https://www.bilibili.com/video/{video_id}"
SUPPORTED_SUBTITLE_EXTENSIONS = {".json", ".srt", ".vtt", ".lrc", ".txt"}


def load_config() -> shared.AppConfig:
    """加载 Bilibili 工具配置。"""
    return shared.AppConfig(
        base_dir=shared.get_env_path("YTSUBMD_BASE_DIR", shared.DEFAULT_BASE_DIR),
        content_subdir=os.environ.get("YTSUBMD_CONTENT_SUBDIR", shared.DEFAULT_CONTENT_SUBDIR).strip()
        or shared.DEFAULT_CONTENT_SUBDIR,
        default_channel_url=os.environ.get("BILISUBMD_DEFAULT_SPACE_URL", DEFAULT_SPACE_URL).strip() or DEFAULT_SPACE_URL,
        default_channel_name=os.environ.get("BILISUBMD_DEFAULT_SPACE_NAME", DEFAULT_SPACE_NAME).strip() or DEFAULT_SPACE_NAME,
        default_limit=int(os.environ.get("BILISUBMD_DEFAULT_LIMIT", str(DEFAULT_LIMIT)).strip() or DEFAULT_LIMIT),
        minimax_base_url=os.environ.get("MINIMAX_BASE_URL", shared.DEFAULT_MINIMAX_BASE_URL).strip()
        or shared.DEFAULT_MINIMAX_BASE_URL,
        minimax_model=os.environ.get("MINIMAX_MODEL", shared.DEFAULT_MINIMAX_MODEL).strip() or shared.DEFAULT_MINIMAX_MODEL,
    )


def normalize_space_url(space_url: str) -> str:
    """标准化空间 URL，确保以 /video 结尾。"""
    cleaned = space_url.strip().rstrip("/")
    if re.fullmatch(r"https?://space\.bilibili\.com/\d+", cleaned):
        return f"{cleaned}/video"
    return cleaned


def get_space_name(space_url: str, default_space_name: str = DEFAULT_SPACE_NAME) -> str:
    """从空间 URL 提取目录名，失败时回退到默认名。"""
    match = re.search(r"space\.bilibili\.com/(\d+)", space_url)
    if match:
        return default_space_name or match.group(1)
    return default_space_name


def build_space_context(
    space_url: str,
    config: shared.AppConfig,
    override_name: Optional[str] = None,
) -> shared.ChannelContext:
    """构建 Bilibili 频道上下文。"""
    name = override_name or get_space_name(space_url, config.default_channel_name)
    return shared.ChannelContext(
        url=normalize_space_url(space_url),
        name=name,
        content_root=config.content_root,
    )


def get_video_url(video_id: str) -> str:
    return VIDEO_URL_TEMPLATE.format(video_id=video_id)


def build_cookie_args(cookies_file: Optional[str], cookies_from_browser: Optional[str]) -> List[str]:
    """构造 yt-dlp cookies 参数。"""
    if cookies_file:
        return ["--cookies", str(Path(cookies_file).expanduser())]
    if cookies_from_browser:
        return ["--cookies-from-browser", cookies_from_browser]
    return []


def is_raw_cookie_header(content: str) -> bool:
    """判断文件内容是否是单行 Cookie header，而非 Netscape cookies 格式。"""
    stripped = content.strip()
    if not stripped:
        return False
    if stripped.startswith("# Netscape HTTP Cookie File"):
        return False
    return "=" in stripped and "\t" not in stripped


def convert_raw_cookie_header_to_netscape(content: str, domain: str = ".bilibili.com") -> str:
    """将单行 Cookie header 转为 Netscape cookies 格式。"""
    stripped = content.strip()
    if stripped.lower().startswith("cookie:"):
        stripped = stripped.split(":", 1)[1].strip()

    lines = ["# Netscape HTTP Cookie File"]
    for part in stripped.split(";"):
        item = part.strip()
        if not item or "=" not in item:
            continue
        name, value = item.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        lines.append("\t".join([domain, "TRUE", "/", "FALSE", "0", name, value]))
    return "\n".join(lines) + "\n"


def normalize_cookie_file(cookies_file: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """将原始 Cookie header 文件转成临时 Netscape 文件，返回可直接给 yt-dlp 使用的路径。"""
    if not cookies_file:
        return None, None

    source_path = Path(cookies_file).expanduser()
    try:
        content = source_path.read_text(encoding="utf-8")
    except OSError as error:
        print(f"   ⚠️ 读取 cookies 文件失败: {error}")
        return str(source_path), None

    if not is_raw_cookie_header(content):
        return str(source_path), None

    netscape_content = convert_raw_cookie_header_to_netscape(content)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".cookies.txt", delete=False) as handle:
        handle.write(netscape_content)
        return handle.name, handle.name


def prepare_cookie_inputs(
    cookies_file: Optional[str],
    cookies_from_browser: Optional[str],
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """标准化 cookies 输入，返回 cookies_file、cookies_from_browser、临时文件路径。"""
    normalized_file, temp_cookie_path = normalize_cookie_file(cookies_file)
    return normalized_file, cookies_from_browser, temp_cookie_path


def cleanup_temp_cookie_file(temp_cookie_path: Optional[str]) -> None:
    """删除临时 cookies 文件。"""
    if not temp_cookie_path:
        return
    try:
        Path(temp_cookie_path).unlink(missing_ok=True)
    except OSError as error:
        print(f"   ⚠️ 清理临时 cookies 文件失败: {error}")


def run_command(
    cmd: List[str],
    *,
    allow_partial: bool = False,
    timeout: int = 120,
) -> Tuple[str, str, int]:
    """执行命令，必要时保留部分成功的 stdout。"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        print(f"命令超时: {' '.join(cmd)}")
        return "", "", 124
    except Exception as error:
        print(f"执行错误: {error}")
        return "", str(error), 1

    stdout = result.stdout or ""
    stderr = result.stderr or ""
    if result.returncode != 0 and not allow_partial:
        print(f"命令执行失败: {' '.join(cmd)}")
        if stderr:
            print(f"错误: {stderr}")
        return "", stderr, result.returncode

    if result.returncode != 0 and allow_partial and stderr:
        first_line = stderr.strip().splitlines()[0]
        print(f"   ⚠️ 命令部分失败，但已获取部分结果: {first_line}")

    return stdout, stderr, result.returncode


def parse_playlist_line(line: str) -> Optional[Dict[str, str]]:
    """解析一行视频元数据。"""
    parts = line.rsplit("|", 2)
    if len(parts) != 3:
        return None
    title, video_id, upload_date = parts
    if not video_id.strip() or video_id.strip() == "NA":
        return None
    return {
        "title": title.strip(),
        "id": video_id.strip(),
        "upload_date": upload_date.strip(),
    }


def fetch_video_metadata(
    video_id: str,
    cookies_file: Optional[str],
    cookies_from_browser: Optional[str],
) -> Dict[str, str]:
    """在空间列表缺少标题/日期时，回退到单视频页补齐元数据。"""
    cmd = [
        "yt-dlp",
        *build_cookie_args(cookies_file, cookies_from_browser),
        "--print",
        "%(title)s|%(id)s|%(upload_date)s",
        get_video_url(video_id),
    ]
    stdout, _, returncode = run_command(cmd, allow_partial=False, timeout=180)
    if returncode != 0 or not stdout.strip():
        return {}

    metadata = parse_playlist_line(stdout.strip().splitlines()[0])
    return metadata or {}


def get_space_videos(
    space_url: str,
    limit: int,
    cookies_file: Optional[str],
    cookies_from_browser: Optional[str],
) -> List[Dict[str, str]]:
    """获取空间最新视频列表，允许在 352 风控下保留部分结果。"""
    normalized_space_url = normalize_space_url(space_url)
    print(f"📺 获取空间最新视频: {normalized_space_url}")

    cmd = [
        "yt-dlp",
        *build_cookie_args(cookies_file, cookies_from_browser),
        "--flat-playlist",
        "--ignore-errors",
        "--playlist-end",
        str(limit),
        "--print",
        "%(title)s|%(id)s|%(timestamp>%Y%m%d)s",
        normalized_space_url,
    ]

    stdout, stderr, _ = run_command(cmd, allow_partial=True, timeout=180)
    if "Request is rejected by server (352)" in stderr:
        print("   ⚠️ Bilibili 返回 352 风控，当前结果可能不完整；建议提供 cookies 提升稳定性。")

    videos: List[Dict[str, str]] = []
    for raw_line in stdout.splitlines():
        video = parse_playlist_line(raw_line.strip())
        if video:
            if video["title"] in ("", "NA") or video["upload_date"] in ("", "NA"):
                enriched = fetch_video_metadata(video["id"], cookies_file, cookies_from_browser)
                if enriched:
                    video["title"] = enriched.get("title", video["title"])
                    video["upload_date"] = enriched.get("upload_date", video["upload_date"])
            videos.append(video)

    print(f"   获取到 {len(videos)} 个视频")
    return videos


def find_existing_summary(video_url: str, context: shared.ChannelContext) -> Optional[Path]:
    """按 source 元数据检查视频是否已处理。"""
    expected_source = f"source: {video_url}"
    for summary_file in context.summaries_dir.glob("*.md"):
        try:
            with summary_file.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip() == expected_source:
                        return summary_file
        except OSError as error:
            print(f"   ⚠️ 读取已有摘要失败: {summary_file.name} - {error}")
    return None


def get_available_subtitles(
    video_url: str,
    cookies_file: Optional[str],
    cookies_from_browser: Optional[str],
) -> List[str]:
    """检查可用字幕语言，忽略 danmaku。"""
    cmd = [
        "yt-dlp",
        *build_cookie_args(cookies_file, cookies_from_browser),
        "--list-subs",
        video_url,
    ]
    stdout, stderr, _ = run_command(cmd, allow_partial=True)
    combined = f"{stdout}\n{stderr}"

    if "Subtitles are only available when logged in" in combined:
        print("   ⚠️ 当前视频字幕需要登录态 cookies；未登录只能看到弹幕（danmaku）。")

    subtitles: List[str] = []
    in_table = False
    for line in combined.splitlines():
        stripped = line.strip()
        if stripped.startswith("Language"):
            in_table = True
            continue
        if not in_table or not stripped:
            continue
        language = stripped.split()[0]
        if language.lower() == "danmaku":
            continue
        subtitles.append(language)

    return subtitles


def choose_subtitle_file(context: shared.ChannelContext, video_id: str) -> Optional[Path]:
    """选择下载下来的字幕文件。"""
    candidates = [
        path for path in context.subtitles_dir.glob(f"{video_id}*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUBTITLE_EXTENSIONS
    ]
    if not candidates:
        return None

    suffix_priority = {".json": 0, ".srt": 1, ".vtt": 2, ".lrc": 3, ".txt": 4}
    candidates.sort(key=lambda path: (suffix_priority.get(path.suffix.lower(), 99), path.name))
    return candidates[0]


def download_subtitle(
    video_id: str,
    context: shared.ChannelContext,
    lang: str,
    cookies_file: Optional[str],
    cookies_from_browser: Optional[str],
) -> Optional[str]:
    """下载字幕文件。"""
    print(f"   ⬇️ 下载字幕: {lang}")
    cmd = [
        "yt-dlp",
        *build_cookie_args(cookies_file, cookies_from_browser),
        "--write-subs",
        "--sub-langs",
        lang,
        "--skip-download",
        "-o",
        str(context.subtitles_dir / f"{video_id}"),
        get_video_url(video_id),
    ]
    _, _, returncode = run_command(cmd, allow_partial=True, timeout=180)
    if returncode not in (0, 1):
        return None

    subtitle_file = choose_subtitle_file(context, video_id)
    return str(subtitle_file) if subtitle_file else None


def transcribe_video_with_asr(
    video_url: str,
    video_id: str,
    cookies_file: Optional[str],
    cookies_from_browser: Optional[str],
) -> Optional[str]:
    """下载音频并转写为文本，作为无字幕时的兜底。"""
    audio_path = shared.download_audio_with_ytdlp(video_url, video_id, cookies_file, cookies_from_browser)
    if not audio_path:
        return None

    try:
        return shared.transcribe_audio_with_asr(audio_path)
    finally:
        shared.cleanup_temp_path(audio_path)


def extract_subtitle_lines_from_text(content: str) -> List[str]:
    """从 VTT/SRT/LRC 等文本字幕中提取正文。"""
    lines: List[str] = []
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith(("WEBVTT", "Kind:", "Language:")):
            continue
        if stripped.isdigit():
            continue
        if re.match(r"^\d{2}:\d{2}:\d{2}[,.]\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}[,.]\d{3}", stripped):
            continue
        if re.match(r"^\[\d{2}:\d{2}(?:\.\d{2,3})?\]", stripped):
            stripped = re.sub(r"^\[\d{2}:\d{2}(?:\.\d{2,3})?\]", "", stripped).strip()
            if not stripped:
                continue
        lines.append(stripped)
    return lines


def extract_subtitle_lines_from_json(content: str) -> List[str]:
    """解析 Bilibili JSON 字幕。"""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []

    if isinstance(data, dict):
        body = data.get("body")
        if isinstance(body, list):
            return [str(item.get("content", "")).strip() for item in body if str(item.get("content", "")).strip()]

    if isinstance(data, list):
        return [
            str(item.get("content", "")).strip()
            for item in data
            if isinstance(item, dict) and str(item.get("content", "")).strip()
        ]

    return []


def prepare_subtitle_text(subtitle_path: str, max_chars: int = 500000) -> str:
    """读取并清洗字幕文件。"""
    path = Path(subtitle_path)
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        print(f"   ❌ 读取字幕文件失败: {error}")
        return ""

    if path.suffix.lower() == ".json":
        text_lines = extract_subtitle_lines_from_json(content)
    else:
        text_lines = extract_subtitle_lines_from_text(content)

    if not text_lines:
        return ""
    return " ".join(text_lines)[:max_chars]


def convert_subtitle_to_md(
    video_url: str,
    title: str,
    subtitle_text: str,
    lang: str,
    context: shared.ChannelContext,
    publish_dates: Dict[str, str],
) -> str:
    """将字幕文本转换为 Markdown。"""
    safe_title = shared.sanitize_filename(title)
    md_filename = f"{safe_title}-{publish_dates['compact']}-字幕.md"
    md_path = context.subtitles_dir / md_filename
    md_content = f"""---
title: {title}
source: {video_url}
channel: {context.name}
channel_url: {context.url}
type: subtitle
platform: bilibili
language: {lang}
created: {publish_dates['compact']}
---

# {title}

{subtitle_text}

---
*字幕由 {context.name} 工具自动提取*"""
    try:
        md_path.write_text(md_content, encoding="utf-8")
    except OSError as error:
        print(f"   ❌ 保存字幕 Markdown 失败: {error}")
        return ""

    print(f"   ✅ 字幕已保存为 Markdown: {md_filename}")
    return str(md_path)


def build_summary_markdown(
    title: str,
    video_url: str,
    video_id: str,
    summary_text: str,
    provider_name: str,
    context: shared.ChannelContext,
    publish_dates: Dict[str, str],
) -> str:
    """构建摘要 Markdown。"""
    date_str = publish_dates["display"]
    return f"""---
title: {title}
source: {video_url}
channel: {context.name}
channel_url: {context.url}
author: {context.name}
published: {date_str}
created: {date_str}
tags:
  - bilibili
  - {context.name}
---

# {title}

## 视频信息

- **频道**：{context.name}
- **发布时间**：{date_str}
- **视频ID**：{video_id}
- **字幕**：已存储

---

## 结构化摘要

{summary_text}

---

*此摘要由 {context.name} 视频摘要工具自动生成（{provider_name}）*
"""


def generate_summary_with_minimax(title: str, subtitle_text: str, config: shared.AppConfig) -> Optional[str]:
    """使用 MiniMax 生成 Bilibili 摘要正文。"""
    prompt = f"""请根据以下 Bilibili 视频字幕生成一份适合保存到 Obsidian 的结构化中文笔记。

输出要求：
1. 总长度控制在 500-900 字
2. 使用 Markdown，严格包含以下四个三级标题：
   - ### 核心主题
   - ### 关键观点
   - ### 重要结论
   - ### 可行动点
3. “关键观点”使用 3-5 条 bullet points
4. “可行动点”使用 2-4 条 bullet points
5. 内容要去除口语重复和冗余表达，保留真正有信息量的观点
6. 不要输出 YAML、不要重复视频标题、不要写额外前言或结尾说明
7. 不要输出 <think>、推理过程、草稿或中间分析

视频标题：{title}

字幕内容：
{subtitle_text[:120000]}
"""

    summary_text = shared.call_minimax(
        prompt=prompt,
        config=config,
        system_prompt="你是一个专业的视频内容分析师。",
        max_tokens=1200,
        temperature=0.4,
    )
    if not summary_text:
        return None

    summary_text = shared.sanitize_summary_text(summary_text)
    if not summary_text:
        print("   ⚠️ MiniMax 返回的摘要清洗后为空")
        return None

    print(f"   🤖 已使用 {config.minimax_model} 生成摘要")
    return summary_text


def generate_basic_summary(
    title: str,
    video_url: str,
    video_id: str,
    subtitle_text: str,
    context: shared.ChannelContext,
    publish_dates: Dict[str, str],
) -> str:
    """在 AI 不可用时生成基础摘要。"""
    preview = subtitle_text[:2000]
    date_str = publish_dates["display"]
    return f"""---
title: {title}
source: {video_url}
channel: {context.name}
channel_url: {context.url}
author: {context.name}
published: {date_str}
created: {date_str}
tags:
  - bilibili
  - {context.name}
---

# {title}

## 视频信息

- **频道**：{context.name}
- **发布时间**：{date_str}
- **视频ID**：{video_id}
- **字幕**：已存储

---

## 内容摘要

（请使用 MINIMAX_API_KEY 或 DASHSCOPE_API_KEY 环境变量启用智能摘要）

---

## 字幕预览

{preview}...

---

*此摘要由 {context.name} 视频摘要工具自动生成*
"""


def generate_summary(
    title: str,
    video_url: str,
    video_id: str,
    subtitle_text: str,
    context: shared.ChannelContext,
    config: shared.AppConfig,
    publish_dates: Dict[str, str],
) -> str:
    """生成摘要，优先 MiniMax，其次 DashScope。"""
    summary_text = generate_summary_with_minimax(title, subtitle_text, config)
    if summary_text:
        return build_summary_markdown(title, video_url, video_id, summary_text, "MiniMax", context, publish_dates)

    summary_text = shared.generate_summary_with_dashscope(subtitle_text)
    if summary_text:
        return build_summary_markdown(title, video_url, video_id, summary_text, "DashScope Qwen", context, publish_dates)

    print("   ⚠️ 未找到可用的 AI 摘要服务，使用基础摘要")
    return generate_basic_summary(title, video_url, video_id, subtitle_text, context, publish_dates)


def save_summary(
    title: str,
    content: str,
    context: shared.ChannelContext,
    publish_dates: Dict[str, str],
    existing_summary: Optional[Path] = None,
) -> str:
    """保存摘要文件。"""
    filename = f"{shared.sanitize_filename(title)}-{publish_dates['compact']}.md"
    filepath = context.summaries_dir / filename
    try:
        filepath.write_text(content, encoding="utf-8")
    except OSError as error:
        print(f"   ❌ 保存失败: {error}")
        return ""

    if existing_summary and existing_summary != filepath and existing_summary.exists():
        try:
            existing_summary.unlink()
            print(f"   🧹 已清理旧摘要文件: {existing_summary.name}")
        except OSError as error:
            print(f"   ⚠️ 清理旧摘要文件失败: {existing_summary.name} - {error}")

    print(f"   ✅ 摘要已保存: {filename}")
    return str(filepath)


def process_video(
    video: Dict[str, str],
    context: shared.ChannelContext,
    config: shared.AppConfig,
    cookies_file: Optional[str],
    cookies_from_browser: Optional[str],
    *,
    dry_run: bool = False,
    force: bool = False,
) -> bool:
    """处理单个 Bilibili 视频。"""
    video_id = video["id"]
    video_url = get_video_url(video_id)
    title = video["title"]
    publish_dates = shared.get_video_dates(video.get("upload_date", ""))

    print(f"\n📹 处理: {title}")
    chinese_title = shared.translate_to_chinese(title)
    if chinese_title != title:
        print(f"   📝 翻译: {title} → {chinese_title}")
    else:
        print("   📝 使用原标题")

    existing_summary = find_existing_summary(video_url, context)
    if existing_summary and not force:
        print(f"   ⏭️ 已存在，跳过: {existing_summary.name}")
        return False
    if existing_summary and force:
        print(f"   ♻️ 已存在，按 --force 重新处理: {existing_summary.name}")

    subtitles = get_available_subtitles(video_url, cookies_file, cookies_from_browser)
    if not subtitles:
        print("   ⚠️ 无可用字幕，尝试 ASR 兜底")
        if dry_run:
            print("   🔍 预览模式，跳过 ASR 转写")
            return True

        asr_text = transcribe_video_with_asr(video_url, video_id, cookies_file, cookies_from_browser)
        if not asr_text:
            print("   ❌ ASR 转写失败")
            return False

        corrected_text = shared.correct_asr_text(chinese_title, asr_text, config)
        formatted_subtitle_text = shared.enhance_subtitle_text(chinese_title, corrected_text, config)
        convert_subtitle_to_md(video_url, chinese_title, formatted_subtitle_text, "asr-zh", context, publish_dates)
        summary = generate_summary(chinese_title, video_url, video_id, formatted_subtitle_text, context, config, publish_dates)
        save_summary(chinese_title, summary, context, publish_dates, existing_summary=existing_summary)
        return True

    preferred_languages = ("zh-CN", "zh-Hans", "zh-Hant", "ai-zh", "en")
    lang = next((item for item in preferred_languages if item in subtitles), subtitles[0])
    print(f"   使用字幕: {lang}")

    if dry_run:
        print("   🔍 预览模式，跳过下载")
        return True

    subtitle_path = download_subtitle(video_id, context, lang, cookies_file, cookies_from_browser)
    if not subtitle_path:
        print("   ❌ 字幕下载失败")
        return False

    try:
        subtitle_text = prepare_subtitle_text(subtitle_path)
    finally:
        shared.cleanup_downloaded_subtitle(subtitle_path)

    if not subtitle_text:
        print("   ❌ 字幕清洗失败")
        return False

    formatted_subtitle_text = shared.enhance_subtitle_text(chinese_title, subtitle_text, config)
    convert_subtitle_to_md(video_url, chinese_title, formatted_subtitle_text, lang, context, publish_dates)

    summary = generate_summary(chinese_title, video_url, video_id, formatted_subtitle_text, context, config, publish_dates)
    save_summary(chinese_title, summary, context, publish_dates, existing_summary=existing_summary)
    return True


def main() -> None:
    shared.load_dotenv()
    config = load_config()

    parser = argparse.ArgumentParser(description="Bilibili 空间字幕摘要工具")
    parser.add_argument("--space-url", "-s", default=config.default_channel_url, help="Bilibili 空间 URL")
    parser.add_argument("--name", help="覆盖输出目录名称")
    parser.add_argument("--limit", "-l", type=int, default=config.default_limit, help="处理视频数量")
    parser.add_argument("--base-dir", help="覆盖输出根目录")
    parser.add_argument("--content-subdir", help="覆盖内容子目录")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不下载字幕")
    parser.add_argument("--force", "-f", action="store_true", help="强制重新处理已存在的视频")
    parser.add_argument("--cookies-file", help="Bilibili cookies 文件路径")
    parser.add_argument("--cookies-from-browser", help="从浏览器读取 cookies，例如 chrome、safari")
    args = parser.parse_args()

    if args.base_dir:
        config = shared.AppConfig(
            base_dir=Path(args.base_dir).expanduser(),
            content_subdir=args.content_subdir or config.content_subdir,
            default_channel_url=config.default_channel_url,
            default_channel_name=config.default_channel_name,
            default_limit=config.default_limit,
            minimax_base_url=config.minimax_base_url,
            minimax_model=config.minimax_model,
        )
    elif args.content_subdir:
        config = shared.AppConfig(
            base_dir=config.base_dir,
            content_subdir=args.content_subdir,
            default_channel_url=config.default_channel_url,
            default_channel_name=config.default_channel_name,
            default_limit=config.default_limit,
            minimax_base_url=config.minimax_base_url,
            minimax_model=config.minimax_model,
        )

    cookies_file = args.cookies_file or os.environ.get("BILISUBMD_COOKIES_FILE", "").strip() or None
    cookies_from_browser = (
        args.cookies_from_browser or os.environ.get("BILISUBMD_COOKIES_FROM_BROWSER", "").strip() or None
    )
    cookies_file, temp_cookie_file = normalize_cookie_file(cookies_file)

    context = build_space_context(args.space_url, config, override_name=args.name)
    context.subtitles_dir.mkdir(parents=True, exist_ok=True)
    context.summaries_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 50)
    print(f"🎬 {context.name} Bilibili 视频摘要工具")
    print("=" * 50)

    try:
        videos = get_space_videos(args.space_url, args.limit, cookies_file, cookies_from_browser)
        if not videos:
            print("❌ 无法获取视频列表")
            return

        processed = 0
        for video in videos:
            if process_video(
                video,
                context,
                config,
                cookies_file,
                cookies_from_browser,
                dry_run=args.dry_run,
                force=args.force,
            ):
                processed += 1

        print("\n" + "=" * 50)
        print(f"✅ 完成！处理了 {processed} 个视频")
        print(f"📂 字幕目录: {context.subtitles_dir}")
        print(f"📂 摘要目录: {context.summaries_dir}")
        print("=" * 50)
    finally:
        if temp_cookie_file:
            try:
                Path(temp_cookie_file).unlink(missing_ok=True)
            except OSError:
                pass


if __name__ == "__main__":
    main()
