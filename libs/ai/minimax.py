"""MiniMax AI provider integration."""

import json
import os
import re
import urllib.error
import urllib.request
from typing import Optional

from libs.ai._utils import (
    preserves_enough_content,
    split_text_for_model,
    strip_reasoning_markup,
)
from libs.config import AppConfig


def sanitize_summary_text(summary_text: str) -> str:
    """Clean model summary output: remove prompt leakage, preambles, extra blank lines."""
    cleaned = strip_reasoning_markup(summary_text).replace('\r\n', '\n').strip()

    first_heading = cleaned.find("### 核心主题")
    if first_heading > 0:
        cleaned = cleaned[first_heading:]

    leaked_line_patterns = (
        r'^(?:、)?推理过程、草稿或中间分析\s*$',
        r'^让我整理笔记内容[:：]?\s*$',
        r'^请生成结构化摘要[:：]?\s*$',
        r'^输出要求[:：]?\s*$',
    )

    kept_lines: list[str] = []
    for line in cleaned.split('\n'):
        stripped = line.strip()
        if stripped == "## 结构化摘要":
            continue
        if any(re.fullmatch(pattern, stripped) for pattern in leaked_line_patterns):
            continue
        kept_lines.append(line.rstrip())

    cleaned = '\n'.join(kept_lines).strip()
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned


def call_minimax(
    prompt: str,
    config: AppConfig,
    system_prompt: str,
    max_tokens: int,
    temperature: float,
    timeout: int = 120,
) -> Optional[str]:
    """Call MiniMax chat API and return cleaned text result."""
    api_key = os.environ.get('MINIMAX_API_KEY', '')
    if not api_key:
        return None

    payload = {
        'model': config.minimax_model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': prompt},
        ],
        'max_tokens': max_tokens,
        'temperature': temperature,
    }

    request = urllib.request.Request(
        f"{config.minimax_base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode('utf-8'),
        method='POST',
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as error:
        body = error.read().decode('utf-8', errors='replace')
        print(f"   ⚠️ MiniMax 请求失败: HTTP {error.code} - {body[:200]}")
        return None
    except urllib.error.URLError as error:
        print(f"   ⚠️ MiniMax 连接失败: {error.reason}")
        return None
    except TimeoutError:
        print("   ⚠️ MiniMax 请求超时")
        return None
    except json.JSONDecodeError as error:
        print(f"   ⚠️ MiniMax 响应解析失败: {error}")
        return None

    base_resp = data.get('base_resp') or {}
    status_code = base_resp.get('status_code', 0)
    if status_code not in (0, None):
        print(f"   ⚠️ MiniMax 调用失败: {base_resp.get('status_msg', 'unknown error')}")
        return None

    choices = data.get('choices') or []
    if not choices:
        print("   ⚠️ MiniMax 未返回内容")
        return None

    message = choices[0].get('message') or {}
    result_text = strip_reasoning_markup(message.get('content') or '')
    if not result_text:
        print("   ⚠️ MiniMax 返回内容为空")
        return None

    return result_text


def generate_summary_with_minimax(
    title: str,
    subtitle_text: str,
    config: AppConfig,
) -> Optional[str]:
    """Generate structured summary using MiniMax."""
    prompt = f"""请根据以下 YouTube 视频字幕生成一份适合保存到 Obsidian 的结构化中文笔记。

输出要求：
1. 总长度控制在 500-900 字
2. 使用 Markdown，严格包含以下四个三级标题：
   - ### 核心主题
   - ### 关键观点
   - ### 重要结论
   - ### 可行动点
3. "关键观点"使用 3-5 条 bullet points
4. "可行动点"使用 2-4 条 bullet points
5. 内容要去除口语重复和冗余表达，保留真正有信息量的观点
6. 不要输出 YAML、不要重复视频标题、不要写额外前言或结尾说明
7. 不要输出 <think>、推理过程、草稿或中间分析

视频标题：{title}

字幕内容：
{subtitle_text[:120000]}
"""

    summary_text = call_minimax(
        prompt=prompt,
        config=config,
        system_prompt='你是一个专业的视频内容分析师。',
        max_tokens=1200,
        temperature=0.4,
    )
    if not summary_text:
        return None

    summary_text = sanitize_summary_text(summary_text)
    if not summary_text:
        print("   ⚠️ MiniMax 返回的摘要清洗后为空")
        return None

    print(f"   🤖 已使用 {config.minimax_model} 生成摘要")
    return summary_text
