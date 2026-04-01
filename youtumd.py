#!/usr/bin/env python3
"""
youtumd - YouTube Video Summary Tool

功能：
- 获取 YouTube 频道最新视频
- 下载字幕
- 生成内容摘要
- 存储到第二大脑

用法：
    python youtumd.py                    # 获取最新视频并处理
    python youtumd.py --dry-run           # 预览模式（不下字幕）
    python youtumd.py --limit 5           # 限制处理数量
    python youtumd.py --channel CHANNEL   # 处理其他频道
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Import shared libraries (extracted from this file)
# ---------------------------------------------------------------------------
from libs.config import (
    AppConfig,
    ChannelContext,
    SubtitleOption,
    DEFAULT_CHANNEL,
    DEFAULT_CHANNEL_NAME,
    DEFAULT_LIMIT,
    DEFAULT_BASE_DIR,
    DEFAULT_CONTENT_SUBDIR,
    DEFAULT_MINIMAX_BASE_URL,
    DEFAULT_MINIMAX_MODEL,
    DEFAULT_ASR_BROWSER_EXECUTABLE,
    DEFAULT_ASR_MODEL,
    DEFAULT_ASR_CAPTURE_SECONDS,
    DEFAULT_ASR_WARMUP_SECONDS,
    DEFAULT_ASR_MAX_SECONDS,
    DEFAULT_ASR_NAVIGATION_TIMEOUT_SECONDS,
    DEFAULT_ASR_CAPTURE_RETRIES,
    DEFAULT_ASR_NETWORK_TIMEOUT_SECONDS,
    build_channel_context,
    choose_subtitle_option,
    find_existing_subtitle,
    find_existing_summary,
    get_channel_name,
    get_env_int,
    get_env_path,
    get_video_dates,
    load_config,
    sanitize_filename,
)
from libs.transcript import (
    build_cookie_args,
    download_subtitle,
    get_available_subtitles,
    prepare_subtitle_text,
    cleanup_downloaded_subtitle,
    parse_available_subtitles,
)
from libs.transcript._utils import run_command
from libs.ai import (
    call_minimax,
    generate_summary_with_dashscope,
    generate_summary_with_minimax,
    sanitize_summary_text,
    preserves_enough_content,
    split_text_for_model,
    strip_reasoning_markup,
)

from subscriptions import Glossary


# ===========================================================================
# ASR (Automatic Speech Recognition) Support Functions
# ===========================================================================

def get_asr_work_root() -> Path:
    """返回 ASR 临时工作目录。"""
    raw = os.environ.get('YTSUBMD_ASR_WORK_DIR', '').strip()
    if raw:
        return Path(raw).expanduser()
    return Path(tempfile.gettempdir()) / 'ytsubmd-asr'


def get_asr_browser_executable() -> str:
    """返回浏览器可执行文件路径。"""
    return os.environ.get('YTSUBMD_BROWSER_EXECUTABLE', '').strip() or DEFAULT_ASR_BROWSER_EXECUTABLE


def get_playwright_require_target() -> str:
    """返回 Node require 的 playwright 模块路径。"""
    return os.environ.get('YTSUBMD_PLAYWRIGHT_REQUIRE', '').strip() or 'playwright-core'


def is_playwright_dependency_missing(error_output: str) -> bool:
    """判断浏览器抓音失败是否由 playwright 依赖缺失引起。"""
    normalized = error_output.lower()
    return (
        "cannot find module 'playwright-core'" in normalized
        or 'cannot find module "playwright-core"' in normalized
        or 'err_module_not_found' in normalized
        or 'playwright-core' in normalized and 'module' in normalized and 'not found' in normalized
    )


def get_asr_python_executable() -> str:
    """返回运行 faster-whisper 的 Python 解释器。"""
    return os.environ.get('YTSUBMD_ASR_PYTHON', '').strip() or sys.executable


def get_asr_model_name() -> str:
    """返回默认 ASR 模型名。"""
    return os.environ.get('YTSUBMD_ASR_MODEL', '').strip() or DEFAULT_ASR_MODEL


def get_asr_capture_seconds() -> int:
    """返回单段 ASR 抓音频时长。"""
    return max(10, get_env_int('YTSUBMD_ASR_CAPTURE_SECONDS', DEFAULT_ASR_CAPTURE_SECONDS))


def get_asr_max_seconds() -> int:
    """返回单视频 ASR 最大处理时长，避免超长视频无限录制。"""
    return max(get_asr_capture_seconds(), get_env_int('YTSUBMD_ASR_MAX_SECONDS', DEFAULT_ASR_MAX_SECONDS))


def get_asr_navigation_timeout_seconds() -> int:
    """返回浏览器访问 YouTube 页面时的超时时间。"""
    return max(30, get_env_int('YTSUBMD_ASR_NAVIGATION_TIMEOUT_SECONDS', DEFAULT_ASR_NAVIGATION_TIMEOUT_SECONDS))


def get_asr_capture_retries() -> int:
    """返回单段浏览器抓音失败后的重试次数。"""
    return max(1, get_env_int('YTSUBMD_ASR_CAPTURE_RETRIES', DEFAULT_ASR_CAPTURE_RETRIES))


def get_asr_network_timeout_seconds() -> int:
    """返回 YouTube 的网络预检超时时间。"""
    return max(5, get_env_int('YTSUBMD_ASR_NETWORK_TIMEOUT_SECONDS', DEFAULT_ASR_NETWORK_TIMEOUT_SECONDS))


def can_reach_youtube(timeout_seconds: Optional[int] = None) -> bool:
    """快速检查当前环境是否能访问 YouTube。"""
    probe_url = os.environ.get('YTSUBMD_ASR_PROBE_URL', '').strip() or 'https://www.youtube.com/robots.txt'
    request = urllib.request.Request(
        probe_url,
        headers={'User-Agent': 'Mozilla/5.0'},
        method='GET',
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds or get_asr_network_timeout_seconds()) as response:
            return int(getattr(response, 'status', 200) or 200) < 500
    except urllib.error.URLError as error:
        print(f"   ❌ YouTube 网络预检失败: {error.reason}")
    except TimeoutError:
        print("   ❌ YouTube 网络预检失败: timeout")
    except OSError as error:
        print(f"   ❌ YouTube 网络预检失败: {error}")
    return False


def cleanup_temp_path(path: Optional[Path]) -> None:
    """删除临时文件。"""
    if not path:
        return
    try:
        if path.exists():
            path.unlink()
    except OSError as error:
        print(f"   ⚠️ 清理临时文件失败: {path} - {error}")


# ===========================================================================
# Title Translation
# ===========================================================================

def translate_to_chinese(title: str) -> str:
    """将英文标题翻译为中文"""
    api_key = os.environ.get('DASHSCOPE_API_KEY', '')
    if not api_key:
        return title

    try:
        import dashscope
        from dashscope import Generation
    except ImportError:
        print("   ⚠️ 未安装 dashscope，跳过标题翻译")
        return title

    dashscope.api_key = api_key

    prompt = f"""请将以下视频标题翻译成中文，只返回翻译后的标题，不要其他内容：

{title}

翻译："""

    try:
        response = Generation.call(
            model='qwen-turbo',
            prompt=prompt,
            max_tokens=500,
            temperature=0.3
        )

        if response.status_code == 200:
            if hasattr(response.output, 'text'):
                translated = response.output.text.strip()
            elif response.output and response.output.choices:
                translated = response.output.choices[0].message.content.strip()
            else:
                translated = str(response.output).strip()
            translated = translated.strip('"\' ')
            return translated

    except Exception as e:
        print(f"   ⚠️ 翻译失败: {e}")

    return title


# ===========================================================================
# Channel Videos
# ===========================================================================

def get_channel_videos(
    channel_url: str,
    limit: int = 10,
    cookies_file: Optional[str] = None,
    cookies_from_browser: Optional[str] = None,
) -> List[Dict]:
    """获取频道最新视频列表"""
    print(f"📺 获取频道最新视频: {channel_url}")

    cmd = [
        "yt-dlp",
        *build_cookie_args(cookies_file, cookies_from_browser),
        "--flat-playlist",
        "--print", "%(title)s|%(id)s|%(upload_date)s",
        channel_url
    ]

    output = run_command(cmd)
    if not output:
        return []

    videos = []
    for i, line in enumerate(output.strip().split('\n')):
        if i >= limit:
            break
        parts = line.rsplit('|', 2)
        if len(parts) >= 2:
            title = '|'.join(parts[:-2]) if len(parts) > 2 else parts[0]
            video_id = parts[-2].strip()
            upload_date = parts[-1].strip() if len(parts) > 1 else ""
            videos.append({
                'title': title,
                'id': video_id,
                'upload_date': upload_date
            })

    print(f"   获取到 {len(videos)} 个视频")
    return videos


# ===========================================================================
# Subtitle Text Processing
# ===========================================================================

def load_subtitle_file(subtitle_path: str) -> str:
    """读取原始字幕文件内容"""
    try:
        with open(subtitle_path, 'r', encoding='utf-8') as handle:
            return handle.read()
    except OSError as error:
        print(f"   ❌ 读取字幕文件失败: {error}")
        return ""


def extract_subtitle_lines(vtt_content: str) -> List[str]:
    """从 VTT 内容提取纯文本行"""
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
    """将字幕文本行合并为清洗后的连续文本"""
    return ' '.join(text_lines)[:max_chars]


def read_subtitle(subtitle_path: str, max_chars: int = 500000) -> str:
    """兼容入口：读取并清洗字幕内容"""
    subtitle_text = prepare_subtitle_text(subtitle_path, max_chars=max_chars)
    if not subtitle_text:
        print("   ❌ 读取字幕失败")
    return subtitle_text


def convert_subtitle_to_md(
    video_id: str,
    title: str,
    subtitle_text: str,
    lang: str,
    context: ChannelContext,
    publish_dates: Dict[str, str],
    existing_subtitle: Optional[Path] = None,
) -> str:
    """将清洗后的字幕文本转换为 Markdown"""
    try:
        md_content = f"""---
title: {title}
source: https://www.youtube.com/watch?v={video_id}
channel: {context.name}
channel_url: {context.url}
type: subtitle
language: {lang}
created: {publish_dates['compact']}
---

# {title}

{subtitle_text}

---
*字幕由 {context.display_name} 工具自动提取*"""

        md_path = context.subtitles_dir / f"{sanitize_filename(title)}-{publish_dates['compact']}-字幕.md"
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        if existing_subtitle and existing_subtitle != md_path:
            try:
                existing_subtitle.unlink()
                print(f"   🧹 已清理旧字幕文件: {existing_subtitle.name}")
            except OSError as error:
                print(f"   ⚠️ 清理旧字幕文件失败: {existing_subtitle.name} - {error}")
        print(f"   📝 字幕已保存: {md_path.name}")
        return str(md_path)
    except Exception as e:
        print(f"   ❌ 保存字幕失败: {e}")
        return ""


# ===========================================================================
# Summary Building
# ===========================================================================

def build_summary_markdown(
    title: str,
    video_id: str,
    summary_text: str,
    provider_name: str,
    context: ChannelContext,
    publish_dates: Dict[str, str],
) -> str:
    """将摘要内容组装为 Obsidian Markdown"""
    date_str = publish_dates['display']
    return f"""---
title: {title}
source: https://www.youtube.com/watch?v={video_id}
channel: {context.name}
channel_url: {context.url}
author: {context.display_name}
published: {date_str}
created: {date_str}
tags:
  - youtube
  - {context.tag_name}
summary_provider: {provider_name}
---

# {title}

{summary_text}

---
*摘要由 {context.display_name} 视频摘要工具自动生成 | provider: {provider_name}*
"""


# ===========================================================================
# ASR Audio Capture & Transcription
# ===========================================================================

def capture_browser_audio(
    video_url: str,
    video_id: str,
    chunk_index: int = 0,
    start_seconds: float = 0.0,
    capture_seconds: Optional[int] = None,
) -> Optional[Tuple[Path, float, float]]:
    """使用浏览器播放页面中的 video 元素抓取一段音频。"""
    work_dir = get_asr_work_root()
    work_dir.mkdir(parents=True, exist_ok=True)
    script_path = work_dir / f'{video_id}-{chunk_index:03d}-capture-audio.js'
    output_path = work_dir / f'{video_id}-{chunk_index:03d}.webm'

    require_target = json.dumps(get_playwright_require_target())
    browser_executable = json.dumps(get_asr_browser_executable())
    effective_capture_seconds = capture_seconds or get_asr_capture_seconds()
    timeout_seconds = max(120, effective_capture_seconds + 90)
    navigation_timeout_ms = get_asr_navigation_timeout_seconds() * 1000
    script = f"""const fs = require('fs');
const {{ chromium }} = require({require_target});

(async () => {{
  const browser = await chromium.launch({{
    executablePath: {browser_executable},
    headless: true,
    args: ['--autoplay-policy=no-user-gesture-required'],
  }});
  const page = await browser.newPage({{ viewport: {{ width: 1440, height: 1200 }} }});
  page.setDefaultTimeout({navigation_timeout_ms});
  page.setDefaultNavigationTimeout({navigation_timeout_ms});
  try {{
    await page.goto({json.dumps(video_url)}, {{ waitUntil: 'commit', timeout: {navigation_timeout_ms} }});
    await page.waitForSelector('video', {{ timeout: {navigation_timeout_ms} }});
    await page.waitForTimeout(8000);
    const result = await page.evaluate(async (options) => {{
      const video = document.querySelector('video');
      if (!video) throw new Error('No video element');
      const waitForMetadata = () => new Promise(resolve => {{
        const finish = () => resolve();
        if (video.readyState >= 1 && Number.isFinite(video.duration) && video.duration > 0) {{
          finish();
          return;
        }}
        video.addEventListener('loadedmetadata', finish, {{ once: true }});
        setTimeout(finish, 5000);
      }});
      const waitForSeek = () => new Promise(resolve => {{
        let done = false;
        const finish = () => {{
          if (!done) {{
            done = true;
            resolve();
          }}
        }};
        video.addEventListener('seeked', finish, {{ once: true }});
        setTimeout(finish, 1500);
      }});
      await waitForMetadata();
      if (Number.isFinite(video.duration) && options.startSeconds > 0) {{
        video.currentTime = Math.min(options.startSeconds, Math.max(0, video.duration - 0.25));
        await waitForSeek();
      }} else if (options.startSeconds > 0) {{
        video.currentTime = options.startSeconds;
        await waitForSeek();
      }}
      video.muted = false;
      video.volume = 1.0;
      try {{ await video.play(); }} catch (_error) {{}}
      await new Promise(resolve => setTimeout(resolve, options.warmupMs));
      const duration = Number.isFinite(video.duration) ? video.duration : 0;
      const actualStartTime = Number.isFinite(video.currentTime) ? video.currentTime : options.startSeconds;
      const remainingMs = duration > 0 ? Math.max(0, (duration - video.currentTime) * 1000) : options.captureMs;
      const actualCaptureMs = Math.max(1000, Math.min(options.captureMs, remainingMs || options.captureMs));
      const getStreamWithAudio = async () => {{
        for (let attempt = 0; attempt < 5; attempt += 1) {{
          const candidate = video.captureStream();
          if (candidate.getAudioTracks().length) {{
            return candidate;
          }}
          try {{ await video.play(); }} catch (_error) {{}}
          await new Promise(resolve => setTimeout(resolve, 1000));
        }}
        throw new Error('No audio tracks in captureStream');
      }};
      const stream = await getStreamWithAudio();
      const audioTracks = stream.getAudioTracks();
      const audioOnly = new MediaStream(audioTracks);
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';
      const recorder = new MediaRecorder(audioOnly, {{ mimeType }});
      const chunks = [];
      recorder.ondataavailable = event => {{ if (event.data && event.data.size) chunks.push(event.data); }};
      recorder.start(1000);
      await new Promise(resolve => setTimeout(resolve, actualCaptureMs));
      recorder.stop();
      await new Promise(resolve => recorder.onstop = resolve);
      const blob = new Blob(chunks, {{ type: mimeType }});
      const buffer = await blob.arrayBuffer();
      const bytes = new Uint8Array(buffer);
      let binary = '';
      const chunkSize = 0x8000;
      for (let i = 0; i < bytes.length; i += chunkSize) {{
        binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
      }}
      return {{
        size: blob.size,
        mimeType,
        duration,
        startTime: actualStartTime,
        endTime: duration > 0 ? Math.min(duration, actualStartTime + actualCaptureMs / 1000) : actualStartTime + actualCaptureMs / 1000,
        base64: btoa(binary),
      }};
    }}, {{
      startSeconds: {start_seconds},
      captureMs: {effective_capture_seconds * 1000},
      warmupMs: {get_env_int('YTSUBMD_ASR_WARMUP_SECONDS', DEFAULT_ASR_WARMUP_SECONDS) * 1000},
    }});
    fs.writeFileSync({json.dumps(str(output_path))}, Buffer.from(result.base64, 'base64'));
    console.log(JSON.stringify({{
      outPath: {json.dumps(str(output_path))},
      size: result.size,
      mimeType: result.mimeType,
      duration: result.duration,
      startTime: result.startTime,
      endTime: result.endTime,
    }}));
  }} finally {{
    await browser.close();
  }}
}})().catch(error => {{
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
}});
"""
    try:
        script_path.write_text(script, encoding='utf-8')
        max_attempts = get_asr_capture_retries()
        for attempt in range(1, max_attempts + 1):
            try:
                result = subprocess.run(
                    ['node', str(script_path)],
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                )
            except FileNotFoundError:
                print("   ❌ 缺少 node，无法执行浏览器音频抓取")
                cleanup_temp_path(output_path)
                return None
            except subprocess.TimeoutExpired:
                if attempt >= max_attempts:
                    print("   ❌ 浏览器音频抓取超时")
                    cleanup_temp_path(output_path)
                    return None
                print(f"   ⚠️ 浏览器音频抓取超时，准备重试 ({attempt}/{max_attempts})")
                cleanup_temp_path(output_path)
                time.sleep(3)
                continue

            if result.returncode != 0:
                error_output = result.stderr.strip() or result.stdout.strip()
                if is_playwright_dependency_missing(error_output):
                    print("   ⚠️ 浏览器音频抓取依赖缺失，改用 yt-dlp 音频下载")
                    cleanup_temp_path(output_path)
                    return None
                if attempt >= max_attempts:
                    print(f"   ❌ 浏览器音频抓取失败: {error_output[:300]}")
                    cleanup_temp_path(output_path)
                    return None
                print(f"   ⚠️ 浏览器音频抓取失败，准备重试 ({attempt}/{max_attempts}): {error_output[:160]}")
                cleanup_temp_path(output_path)
                time.sleep(3)
                continue

            try:
                payload = json.loads(result.stdout.strip() or '{}')
            except json.JSONDecodeError:
                if attempt >= max_attempts:
                    print("   ❌ 浏览器音频抓取返回值无法解析")
                    cleanup_temp_path(output_path)
                    return None
                print(f"   ⚠️ 浏览器音频抓取返回值无法解析，准备重试 ({attempt}/{max_attempts})")
                cleanup_temp_path(output_path)
                time.sleep(3)
                continue

            audio_path = Path(str(payload.get('outPath', '')).strip() or output_path)
            if not audio_path.is_file():
                if attempt >= max_attempts:
                    print("   ❌ 浏览器音频抓取未生成音频文件")
                    return None
                print(f"   ⚠️ 浏览器音频文件缺失，准备重试 ({attempt}/{max_attempts})")
                time.sleep(3)
                continue

            duration = float(payload.get('duration', 0) or 0)
            start_time = float(payload.get('startTime', start_seconds) or start_seconds)
            end_time = float(payload.get('endTime', 0) or 0)
            print(f"   🎙️ 已抓取浏览器音频分段 {chunk_index + 1}: {audio_path.name} ({start_time:.1f}s → {end_time:.1f}s)")
            return audio_path, duration, end_time
    finally:
        cleanup_temp_path(script_path)

    return None


def download_audio_with_ytdlp(
    video_url: str,
    video_id: str,
    cookies_file: Optional[str] = None,
    cookies_from_browser: Optional[str] = None,
) -> Optional[Path]:
    """直接用 yt-dlp 下载整段音频，作为浏览器抓音失败时的备用路径。"""
    work_dir = get_asr_work_root()
    work_dir.mkdir(parents=True, exist_ok=True)
    output_base = work_dir / f'{video_id}-audio'

    cmd = [
        'yt-dlp',
        *build_cookie_args(cookies_file, cookies_from_browser),
        '--no-playlist',
        '-f', 'bestaudio/best',
        '--print', 'after_move:filepath',
        '-o', str(output_base),
        video_url,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except FileNotFoundError:
        print("   ❌ 缺少 yt-dlp，无法下载备用音频")
        return None
    except subprocess.TimeoutExpired:
        print("   ❌ yt-dlp 音频下载超时")
        return None

    if result.returncode != 0:
        error_output = result.stderr.strip() or result.stdout.strip()
        print(f"   ❌ yt-dlp 音频下载失败: {error_output[:300]}")
        return None

    candidates = sorted(
        [path for path in work_dir.glob(f'{video_id}-audio*') if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        print(f"   🎧 已下载备用音频: {candidates[0].name}")
        return candidates[0]

    for line in (result.stdout or '').splitlines()[::-1]:
        candidate = Path(line.strip())
        if candidate.is_file():
            print(f"   🎧 已下载备用音频: {candidate.name}")
            return candidate

    print("   ❌ yt-dlp 音频下载完成但未找到输出文件")
    return None


def transcribe_audio_with_asr(audio_path: Path, model: Optional[str] = None, language: str = 'zh') -> Optional[str]:
    """使用 faster-whisper 将音频转写为文本。"""
    python_executable = get_asr_python_executable()
    model_name = model or get_asr_model_name()
    code = r"""
import json
import sys
from faster_whisper import WhisperModel

audio_path = sys.argv[1]
model_name = sys.argv[2]
language = sys.argv[3]
model = WhisperModel(model_name, device='cpu', compute_type='int8')
segments, _info = model.transcribe(audio_path, language=language, vad_filter=True)
result = [segment.text.strip() for segment in segments if segment.text.strip()]
print(json.dumps(result, ensure_ascii=False))
"""
    try:
        result = subprocess.run(
            [python_executable, '-c', code, str(audio_path), model_name, language],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except FileNotFoundError:
        print(f"   ❌ 找不到 ASR Python 解释器: {python_executable}")
        return None
    except subprocess.TimeoutExpired:
        print("   ❌ ASR 转写超时")
        return None

    if result.returncode != 0:
        error_output = result.stderr.strip() or result.stdout.strip()
        print(f"   ❌ ASR 转写失败: {error_output[:300]}")
        return None

    try:
        parts = json.loads(result.stdout.strip() or '[]')
    except json.JSONDecodeError:
        print("   ❌ ASR 转写结果无法解析")
        return None

    text = ' '.join(str(item).strip() for item in parts if str(item).strip()).strip()
    if not text:
        print("   ❌ ASR 转写为空")
        return None
    print(f"   🧠 已完成 ASR 转写（{model_name}）")
    return text


def transcribe_video_with_asr(video_url: str, video_id: str) -> Optional[str]:
    """分段抓取整段视频音频并拼接 ASR 转写。"""
    if not can_reach_youtube():
        print("   ❌ 当前环境无法访问 YouTube，跳过 ASR 抓音")
        return None

    chunk_seconds = get_asr_capture_seconds()
    max_seconds = get_asr_max_seconds()
    current_start = 0.0
    known_duration = 0.0
    parts: List[str] = []
    chunk_index = 0

    while current_start < max_seconds:
        captured = capture_browser_audio(
            video_url,
            video_id,
            chunk_index=chunk_index,
            start_seconds=current_start,
            capture_seconds=chunk_seconds,
        )
        if not captured:
            if not parts and chunk_index == 0:
                fallback_audio = download_audio_with_ytdlp(video_url, video_id)
                if fallback_audio:
                    try:
                        fallback_text = transcribe_audio_with_asr(fallback_audio)
                    finally:
                        cleanup_temp_path(fallback_audio)
                    if fallback_text:
                        return fallback_text
            break

        audio_path, duration, end_time = captured
        if duration > 0:
            known_duration = duration

        try:
            text = transcribe_audio_with_asr(audio_path)
        finally:
            cleanup_temp_path(audio_path)

        if text:
            parts.append(text)

        if known_duration and end_time >= known_duration - 0.5:
            break

        next_start = end_time if end_time > current_start + 0.5 else current_start + chunk_seconds
        if next_start <= current_start + 0.5:
            break

        current_start = next_start
        chunk_index += 1

        if known_duration and current_start >= known_duration:
            break

    full_text = ' '.join(part.strip() for part in parts if part.strip()).strip()
    if not full_text:
        print("   ❌ 整段 ASR 转写为空")
        return None
    print(f"   🧾 已拼接 {len(parts)} 段 ASR 转写")
    return full_text


# ===========================================================================
# Subtitle Enhancement (MiniMax)
# ===========================================================================

def build_glossary_hint(glossary: Optional[Glossary]) -> str:
    """将 Glossary 渲染成稳定的 prompt 片段。"""
    if glossary:
        return glossary.to_prompt_hint()
    return "频道术语：\n- 无\n\n常见纠错：\n- 无\n\n保守规则：\n- 不确定时保留原词"


def correct_asr_text(
    title: str,
    asr_text: str,
    config: AppConfig,
    glossary: Optional[Glossary] = None,
) -> str:
    """对 ASR 文本做轻量纠错与规范化。"""
    prompt = f"""请将以下 ASR 自动转写文本整理成适合阅读的中文字幕正文。

要求：
1. 只做纠错与整理：修正明显的同音/近音识别错误、补全标点、修正断句、统一中英文大小写与空格。
2. 严格保留原意，不要总结、不要删减关键事实、不要新增信息。
3. 保持原有叙述顺序。
4. 输出纯正文段落，不要标题、不要列表、不要说明、不要 <think>。
5. 遇到明显的产品名、品牌名、术语、人名时，优先按"术语提示"纠正。
6. 如果某个词无法确定，保留原词或使用最保守写法，不要强行猜测。
7. 只处理当前文本本身，不要补写上下文。

视频标题：{title}

术语提示：
{build_glossary_hint(glossary)}

ASR 文本：
{asr_text}
"""
    corrected = call_minimax(
        prompt=prompt,
        config=config,
        system_prompt='你是一个专业的中文视频字幕校对编辑。',
        max_tokens=2200,
        temperature=0.1,
        timeout=120,
    )
    if corrected:
        print("   ✍️ 已完成 ASR 纠错")
        return corrected.strip()
    print("   ⚠️ ASR 纠错不可用，使用原始转写文本")
    return asr_text


def enhance_subtitle_chunk_with_minimax(
    title: str,
    chunk: str,
    config: AppConfig,
    chunk_label: str,
    max_chars: int,
) -> Optional[List[str]]:
    """优化单个字幕片段，必要时自动拆小后重试"""
    print(f"   ✨ 优化字幕片段 {chunk_label}")
    prompt = f"""请将以下 YouTube 自动字幕整理成适合阅读的中文正文。

要求：
1. 只做编辑整理：自动补全标点、修正断句、按语义智能分段。
2. 严格保留原意，不要总结、不要删减关键事实、不要新增信息。
3. 保持原有叙述顺序。
4. 输出纯正文段落，不要标题、不要列表、不要说明、不要 <think>。
5. 可适度去掉明显重复的口头禅，但不要明显压缩信息量。
6. 如果这是整段字幕中的一个片段，只整理这个片段本身，不要写过渡语。

视频标题：{title}
当前片段：{chunk_label}

字幕内容：
{chunk}
"""
    enhanced_chunk = call_minimax(
        prompt=prompt,
        config=config,
        system_prompt='你是一个专业的中文字幕编辑。',
        max_tokens=2200,
        temperature=0.1,
        timeout=120,
    )
    if enhanced_chunk:
        enhanced_chunk = enhanced_chunk.strip()
        if preserves_enough_content(chunk, enhanced_chunk):
            return [enhanced_chunk]
        print(f"   ⚠️ 片段 {chunk_label} 增强后信息量缩水明显，保留原始片段")
        return [chunk.strip()]

    if len(chunk) <= 800:
        return None

    smaller_max_chars = max(800, max_chars // 2)
    smaller_chunks = split_text_for_model(chunk, max_chars=smaller_max_chars)
    if len(smaller_chunks) <= 1:
        return None

    print(f"   ↪️ 片段 {chunk_label} 过长，拆成 {len(smaller_chunks)} 段后重试")
    results: List[str] = []
    for sub_index, smaller_chunk in enumerate(smaller_chunks, start=1):
        nested_label = f"{chunk_label}.{sub_index}/{len(smaller_chunks)}"
        enhanced_parts = enhance_subtitle_chunk_with_minimax(
            title=title,
            chunk=smaller_chunk,
            config=config,
            chunk_label=nested_label,
            max_chars=smaller_max_chars,
        )
        if not enhanced_parts:
            return None
        results.extend(enhanced_parts)
    return results


def enhance_subtitle_text_with_minimax(title: str, subtitle_text: str, config: AppConfig) -> Optional[str]:
    """使用 MiniMax 为字幕自动补标点并按语义分段"""
    chunks = split_text_for_model(subtitle_text)
    if not chunks:
        return ''

    enhanced_chunks: List[str] = []
    total_chunks = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        enhanced_parts = enhance_subtitle_chunk_with_minimax(
            title=title,
            chunk=chunk,
            config=config,
            chunk_label=f"{index}/{total_chunks}",
            max_chars=1800,
        )
        if not enhanced_parts:
            return None
        enhanced_chunks.extend(enhanced_parts)

    print(f"   ✅ 已使用 {config.minimax_model} 优化字幕标点和分段")
    return '\n\n'.join(enhanced_chunks)


def enhance_subtitle_text(title: str, subtitle_text: str, config: AppConfig) -> str:
    """优化字幕可读性，失败时回退到基础清洗文本"""
    enhanced_text = enhance_subtitle_text_with_minimax(title, subtitle_text, config)
    if enhanced_text:
        return enhanced_text

    print("   ⚠️ 智能标点/分段不可用，使用基础清洗字幕")
    return subtitle_text


# ===========================================================================
# Summary Generation
# ===========================================================================

def generate_summary(
    title: str,
    video_id: str,
    subtitle_text: str,
    context: ChannelContext,
    config: AppConfig,
    publish_dates: Dict[str, str],
) -> str:
    """生成视频摘要，优先使用 MiniMax，其次 DashScope"""
    summary_text = generate_summary_with_minimax(title, subtitle_text, config)
    if summary_text:
        return build_summary_markdown(title, video_id, summary_text, 'MiniMax', context, publish_dates)

    summary_text = generate_summary_with_dashscope(subtitle_text)
    if summary_text:
        return build_summary_markdown(title, video_id, summary_text, 'DashScope Qwen', context, publish_dates)

    print("   ⚠️ 未找到可用的 AI 摘要服务，使用基础摘要")
    return generate_basic_summary(title, video_id, subtitle_text, context, publish_dates)


def generate_basic_summary(
    title: str,
    video_id: str,
    subtitle_text: str,
    context: ChannelContext,
    publish_dates: Dict[str, str],
) -> str:
    """生成基础摘要（当 API 不可用时）"""
    date_str = publish_dates['display']
    preview = subtitle_text[:2000]

    summary = f"""---
title: {title}
source: https://www.youtube.com/watch?v={video_id}
channel: {context.name}
channel_url: {context.url}
author: {context.display_name}
published: {date_str}
created: {date_str}
tags:
  - youtube
  - {context.tag_name}
---

# {title}

## 视频信息

- **频道**：{context.display_name}
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

*此摘要由 {context.display_name} 视频摘要工具自动生成*
"""
    return summary


# ===========================================================================
# Save Summary
# ===========================================================================

def save_summary(
    title: str,
    video_id: str,
    content: str,
    context: ChannelContext,
    publish_dates: Dict[str, str],
    existing_summary: Optional[Path] = None,
) -> str:
    """保存摘要文件"""
    safe_title = sanitize_filename(title)
    filename = f"{safe_title}-{publish_dates['compact']}.md"

    filepath = context.summaries_dir / filename

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        if existing_summary and existing_summary != filepath:
            try:
                existing_summary.unlink()
                print(f"   🧹 已清理旧摘要文件: {existing_summary.name}")
            except OSError as error:
                print(f"   ⚠️ 清理旧摘要文件失败: {existing_summary.name} - {error}")
        print(f"   ✅ 摘要已保存: {filename}")
        return str(filepath)
    except Exception as e:
        print(f"   ❌ 保存失败: {e}")
        return ""


# ===========================================================================
# Video Processing
# ===========================================================================

def process_video_with_asr_fallback(
    video: Dict,
    context: ChannelContext,
    config: AppConfig,
    dry_run: bool = False,
    force: bool = False,
    glossary: Optional[Glossary] = None,
    cookies_file: Optional[str] = None,
    cookies_from_browser: Optional[str] = None,
) -> bool:
    """处理需要走浏览器音频 + ASR 兜底的视频。"""
    video_id = video['id']
    title = video['title']
    publish_dates = get_video_dates(video.get('upload_date', ''))
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    print(f"\n📹 处理（ASR 兜底）: {title}")

    chinese_title = translate_to_chinese(title)
    if chinese_title != title:
        print(f"   📝 翻译: {title} → {chinese_title}")
    else:
        print("   📝 使用原标题")

    existing_summary = find_existing_summary(video_id, context)
    existing_subtitle = find_existing_subtitle(video_id, context)
    if existing_summary and not force:
        print(f"   ⏭️ 已存在，跳过: {existing_summary.name}")
        return False
    if existing_summary and force:
        print(f"   ♻️ 已存在，按 --force 重新处理: {existing_summary.name}")

    if dry_run:
        print("   🔍 预览模式，跳过 ASR 音频抓取")
        return True

    asr_text = transcribe_video_with_asr(video_url, video_id)
    if not asr_text and (cookies_file or cookies_from_browser):
        print("   ⚠️ 浏览器抓音失败，尝试使用 cookies 下载备用音频")
        fallback_audio = download_audio_with_ytdlp(video_url, video_id, cookies_file, cookies_from_browser)
        if fallback_audio:
            try:
                asr_text = transcribe_audio_with_asr(fallback_audio)
            finally:
                cleanup_temp_path(fallback_audio)
    if not asr_text:
        return False

    corrected_text = correct_asr_text(chinese_title, asr_text, config, glossary)
    formatted_subtitle_text = enhance_subtitle_text(chinese_title, corrected_text, config)
    convert_subtitle_to_md(
        video_id,
        chinese_title,
        formatted_subtitle_text,
        'asr-zh',
        context,
        publish_dates,
        existing_subtitle=existing_subtitle,
    )

    summary = generate_summary(chinese_title, video_id, formatted_subtitle_text, context, config, publish_dates)
    save_summary(chinese_title, video_id, summary, context, publish_dates, existing_summary=existing_summary)
    return True


def process_video(
    video: Dict,
    context: ChannelContext,
    config: AppConfig,
    dry_run: bool = False,
    force: bool = False,
    cookies_file: Optional[str] = None,
    cookies_from_browser: Optional[str] = None,
) -> bool:
    """处理单个视频"""
    video_id = video['id']
    title = video['title']
    publish_dates = get_video_dates(video.get('upload_date', ''))

    print(f"\n📹 处理: {title}")

    chinese_title = translate_to_chinese(title)
    if chinese_title != title:
        print(f"   📝 翻译: {title} → {chinese_title}")
    else:
        print(f"   📝 使用原标题")

    existing_summary = find_existing_summary(video_id, context)
    existing_subtitle = find_existing_subtitle(video_id, context)
    if existing_summary and not force:
        print(f"   ⏭️ 已存在，跳过: {existing_summary.name}")
        return False
    if existing_summary and force:
        print(f"   ♻️ 已存在，按 --force 重新处理: {existing_summary.name}")

    subtitle_options = get_available_subtitles(video_id, cookies_file, cookies_from_browser)
    if not subtitle_options:
        print(f"   ⚠️ 无可用字幕")
        return False

    chosen_option = None
    for opt in sorted(
        subtitle_options,
        key=lambda o: (
            0 if o.code == "zh-Hans" else 1 if o.code == "zh-Hant" else 2 if o.code == "en" else 3,
            0 if not o.is_auto else 1,
        ),
    ):
        chosen_option = opt
        break

    if not chosen_option:
        print(f"   ⚠️ 无可用字幕")
        return False
    print(f"   使用字幕: {chosen_option.code}")

    if dry_run:
        print(f"   🔍 预览模式，跳过下载")
        return True

    subtitle_path = download_subtitle(
        video_id,
        context,
        chosen_option,
        cookies_file=cookies_file,
        cookies_from_browser=cookies_from_browser,
    )
    if not subtitle_path:
        print(f"   ❌ 字幕下载失败")
        return False

    try:
        subtitle_text = prepare_subtitle_text(subtitle_path)
    finally:
        cleanup_downloaded_subtitle(subtitle_path)

    if not subtitle_text:
        print(f"   ❌ 字幕清洗失败")
        return False

    formatted_subtitle_text = enhance_subtitle_text(chinese_title, subtitle_text, config)

    convert_subtitle_to_md(
        video_id,
        chinese_title,
        formatted_subtitle_text,
        chosen_option.code,
        context,
        publish_dates,
        existing_subtitle=existing_subtitle,
    )

    summary = generate_summary(chinese_title, video_id, formatted_subtitle_text, context, config, publish_dates)
    save_summary(chinese_title, video_id, summary, context, publish_dates, existing_summary=existing_summary)
    return True


# ===========================================================================
# Channel Configuration Loading
# ===========================================================================

def load_channels_config(config_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """从 channels.yaml 加载频道订阅列表，返回已启用的频道配置列表。"""
    candidates = []
    if config_path:
        candidates.append(config_path)
    candidates.append(Path(__file__).parent / 'channels.yaml')
    candidates.append(Path.cwd() / 'channels.yaml')

    for path in candidates:
        if path.is_file():
            try:
                return _parse_channels_yaml(path)
            except Exception as e:
                print(f"⚠️  解析 {path} 失败: {e}")
                return []
    return []


def _parse_channels_yaml(path: Path) -> List[Dict[str, Any]]:
    """简单 YAML 解析器，支持 channels.yaml 的固定格式。"""
    try:
        import yaml
        with path.open(encoding='utf-8') as f:
            data = yaml.safe_load(f)
        channels = data.get('channels', []) if data else []
    except ImportError:
        channels = _parse_channels_yaml_manual(path)

    result = []
    for ch in channels:
        if not ch or not isinstance(ch, dict):
            continue
        url = str(ch.get('url', '')).strip()
        if not url:
            continue
        result.append({
            'name': str(ch.get('name', '')).strip() or None,
            'url': url,
            'limit': int(ch.get('limit', 5)),
            'enabled': bool(ch.get('enabled', True)),
        })
    return [ch for ch in result if ch['enabled']]


def _parse_channels_yaml_manual(path: Path) -> List[Dict[str, Any]]:
    """不依赖 PyYAML 的手写解析，仅支持 channels.yaml 的固定格式。"""
    channels: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    with path.open(encoding='utf-8') as f:
        for raw_line in f:
            line = raw_line.rstrip()
            stripped = line.lstrip()

            if not stripped or stripped.startswith('#'):
                continue

            if re.match(r'^\s{2}-\s', line):
                if current is not None:
                    channels.append(current)
                current = {}
                inline = stripped[2:].strip()
                if ':' in inline:
                    k, _, v = inline.partition(':')
                    _set_channel_field(current, k.strip(), v.strip())
                continue

            if current is not None and re.match(r'^\s{4}', line) and ':' in stripped:
                k, _, v = stripped.partition(':')
                _set_channel_field(current, k.strip(), v.strip())

    if current is not None:
        channels.append(current)

    return channels


def _set_channel_field(ch: Dict[str, Any], key: str, raw_value: str) -> None:
    """解析单个 YAML 字段值并写入频道字典。"""
    v = raw_value.strip().strip('"').strip("'")
    if key == 'enabled':
        ch[key] = v.lower() not in ('false', '0', 'no')
    elif key == 'limit':
        try:
            ch[key] = int(v)
        except ValueError:
            ch[key] = 5
    else:
        ch[key] = v


def process_all_channels(
    config: AppConfig,
    dry_run: bool = False,
    force: bool = False,
    channels_file: Optional[Path] = None,
    cookies_file: Optional[str] = None,
    cookies_from_browser: Optional[str] = None,
) -> None:
    """读取 channels.yaml，依次处理所有已启用的频道。"""
    channels = load_channels_config(channels_file)

    if not channels:
        print("❌ channels.yaml 中没有已启用的频道，请检查配置文件。")
        return

    print(f"📋 共找到 {len(channels)} 个已启用频道")
    print()

    total_processed = 0
    for idx, ch in enumerate(channels, 1):
        ch_url = ch['url']
        ch_limit = ch['limit']

        context = build_channel_context(ch_url, config, override_name=ch.get('name'))
        context.subtitles_dir.mkdir(parents=True, exist_ok=True)
        context.summaries_dir.mkdir(parents=True, exist_ok=True)

        print("=" * 50)
        print(f"[{idx}/{len(channels)}] 📺 {context.name}")
        print(f"    URL: {ch_url}  |  limit: {ch_limit}")
        print("=" * 50)

        videos = get_channel_videos(ch_url, ch_limit, cookies_file, cookies_from_browser)
        if not videos:
            print(f"  ❌ 无法获取 {context.name} 的视频列表，跳过")
            continue

        processed = 0
        for video in videos:
            if process_video(
                video,
                context,
                config,
                dry_run,
                force,
                cookies_file=cookies_file,
                cookies_from_browser=cookies_from_browser,
            ):
                processed += 1
        total_processed += processed
        print(f"  ✅ {context.name}：本次处理 {processed} 个视频\n")

    print("=" * 50)
    print(f"✅ 所有频道完成！本次共处理 {total_processed} 个视频")
    print("=" * 50)


# ===========================================================================
# Main Entry Point
# ===========================================================================

def main() -> None:
    load_config()  # this actually just calls load_dotenv internally now
    from libs.config import load_dotenv
    load_dotenv()
    config = load_config()

    parser = argparse.ArgumentParser(description="YouTube 视频字幕摘要工具")
    parser.add_argument("--channel", "-c", default=config.default_channel_url, help="YouTube 频道 URL")
    parser.add_argument("--limit", "-l", type=int, default=config.default_limit, help="处理视频数量")
    parser.add_argument("--base-dir", help="覆盖输出根目录")
    parser.add_argument("--content-subdir", help="覆盖内容子目录")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不下载字幕")
    parser.add_argument("--force", "-f", action="store_true", help="强制重新处理已存在的视频")
    parser.add_argument("--all-channels", "-A", action="store_true", help="从 channels.yaml 读取所有已启用频道并依次处理")
    parser.add_argument("--channels-file", type=Path, default=None, help="指定 channels.yaml 路径")
    parser.add_argument("--cookies-file", help="YouTube cookies 文件路径")
    parser.add_argument("--cookies-from-browser", help="从浏览器读取 cookies")

    args = parser.parse_args()

    if args.base_dir:
        config = AppConfig(
            base_dir=Path(args.base_dir).expanduser(),
            content_subdir=args.content_subdir or config.content_subdir,
            default_channel_url=config.default_channel_url,
            default_channel_name=config.default_channel_name,
            default_limit=config.default_limit,
            minimax_base_url=config.minimax_base_url,
            minimax_model=config.minimax_model,
        )
    elif args.content_subdir:
        config = AppConfig(
            base_dir=config.base_dir,
            content_subdir=args.content_subdir,
            default_channel_url=config.default_channel_url,
            default_channel_name=config.default_channel_name,
            default_limit=config.default_limit,
            minimax_base_url=config.minimax_base_url,
            minimax_model=config.minimax_model,
        )

    cookies_file = args.cookies_file or os.environ.get("YTSUBMD_COOKIES_FILE", "").strip() or None
    cookies_from_browser = (
        args.cookies_from_browser or os.environ.get("YTSUBMD_COOKIES_FROM_BROWSER", "").strip() or None
    )

    context = build_channel_context(args.channel, config)

    if args.all_channels:
        process_all_channels(
            config,
            dry_run=args.dry_run,
            force=args.force,
            channels_file=args.channels_file,
            cookies_file=cookies_file,
            cookies_from_browser=cookies_from_browser,
        )
        return

    context.subtitles_dir.mkdir(parents=True, exist_ok=True)
    context.summaries_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 50)
    print(f"🎬 {context.name} 视频摘要工具")
    print("=" * 50)

    videos = get_channel_videos(args.channel, args.limit, cookies_file, cookies_from_browser)

    if not videos:
        print("❌ 无法获取视频列表")
        return

    processed = 0
    for video in videos:
        if process_video(
            video,
            context,
            config,
            args.dry_run,
            args.force,
            cookies_file=cookies_file,
            cookies_from_browser=cookies_from_browser,
        ):
            processed += 1

    print("\n" + "=" * 50)
    print(f"✅ 完成！处理了 {processed} 个视频")
    print(f"📂 字幕目录: {context.subtitles_dir}")
    print(f"📂 摘要目录: {context.summaries_dir}")
    print("=" * 50)


if __name__ == "__main__":
    main()
