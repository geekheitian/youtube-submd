"""DashScope AI provider integration (Alibaba Qwen)."""

import os
from typing import Optional

from libs.ai.minimax import sanitize_summary_text


def generate_summary_with_dashscope(subtitle_text: str) -> Optional[str]:
    """Generate structured summary using DashScope (Qwen)."""
    api_key = os.environ.get('DASHSCOPE_API_KEY', '')
    if not api_key:
        return None

    try:
        import dashscope
        from dashscope import Generation
    except ImportError:
        print("   ⚠️ 未安装 dashscope，跳过 DashScope 摘要")
        return None

    dashscope.api_key = api_key
    prompt = """你是一个专业的视频内容分析师。请根据以下字幕内容生成适合 Obsidian 保存的结构化中文笔记。

要求：
1. 总长度控制在 500-900 字
2. 使用 Markdown，严格包含以下四个三级标题：
   - ### 核心主题
   - ### 关键观点
   - ### 重要结论
   - ### 可行动点
3. "关键观点"使用 3-5 条 bullet points
4. "可行动点"使用 2-4 条 bullet points
5. 去除口语重复与冗余表达，保留真正有信息量的观点
6. 不要输出 YAML、不要重复视频标题、不要写额外前言或结尾说明
7. 不要输出 <think>、推理过程、草稿或中间分析

字幕内容：
""" + subtitle_text + """

请生成结构化摘要："""

    try:
        response = Generation.call(
            model='qwen-turbo',
            prompt=prompt,
            max_tokens=2000,
            temperature=0.7,
        )
    except Exception as error:
        print(f"   ⚠️ DashScope 生成摘要出错: {error}")
        return None

    if response.status_code != 200:
        print(f"   ⚠️ DashScope 调用失败: {response.message}")
        return None

    if hasattr(response.output, 'text'):
        summary_text = response.output.text
    elif response.output and response.output.choices:
        summary_text = response.output.choices[0].message.content
    else:
        summary_text = str(response.output)

    summary_text = summary_text.strip()
    if not summary_text:
        print("   ⚠️ DashScope 返回的摘要为空")
        return None

    summary_text = sanitize_summary_text(summary_text)
    if not summary_text:
        print("   ⚠️ DashScope 返回的摘要清洗后为空")
        return None

    print("   🤖 已使用 DashScope 生成摘要")
    return summary_text
