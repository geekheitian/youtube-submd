from __future__ import annotations

import json
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Dict, List

STATUS_JSON_PATH = Path(__file__).parent / 'status.json'
STATUS_HTML_PATH = Path(__file__).parent / 'status.html'


def write_status(status: Dict, status_path: Path = STATUS_JSON_PATH) -> None:
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')


def load_status(status_path: Path = STATUS_JSON_PATH) -> Dict:
    if not status_path.is_file():
        return {}
    return json.loads(status_path.read_text(encoding='utf-8'))


def render_status_html(status: Dict) -> str:
    generated_at = escape(str(status.get('generated_at', '')))
    rows: List[str] = []
    for item in status.get('subscriptions', []):
        error = escape(str(item.get('last_error') or ''))
        recent_files = '<br>'.join(escape(str(path)) for path in item.get('recent_files', []))
        rows.append(
            '<tr>'
            f"<td>{escape(str(item.get('name', '')))}</td>"
            f"<td>{escape(str(item.get('platform', '')))}</td>"
            f"<td>{escape(str(item.get('last_run_at', '')))}</td>"
            f"<td>{escape(str(item.get('result', '')))}</td>"
            f"<td>{escape(str(item.get('processed', 0)))}</td>"
            f"<td>{escape(str(item.get('skipped', 0)))}</td>"
            f"<td>{escape(str(item.get('failed', 0)))}</td>"
            f"<td>{error}</td>"
            f"<td>{recent_files}</td>"
            '</tr>'
        )

    table_rows = '\n'.join(rows) or '<tr><td colspan="9">暂无运行记录</td></tr>'
    return f"""<!DOCTYPE html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"UTF-8\">
  <title>youtube-submd 状态面板</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif; margin: 24px; color: #222; }}
    h1 {{ margin-bottom: 8px; }}
    .meta {{ color: #666; margin-bottom: 16px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; vertical-align: top; text-align: left; }}
    th {{ background: #f6f6f6; }}
    code {{ background: #f2f2f2; padding: 1px 4px; border-radius: 4px; }}
  </style>
</head>
<body>
  <h1>youtube-submd 状态面板</h1>
  <div class=\"meta\">最近更新时间：<code>{generated_at or datetime.now().isoformat()}</code></div>
  <table>
    <thead>
      <tr>
        <th>订阅</th>
        <th>平台</th>
        <th>最近运行</th>
        <th>结果</th>
        <th>处理</th>
        <th>跳过</th>
        <th>失败</th>
        <th>最近错误</th>
        <th>最近文件</th>
      </tr>
    </thead>
    <tbody>
      {table_rows}
    </tbody>
  </table>
</body>
</html>
"""


def write_status_html(status: Dict, html_path: Path = STATUS_HTML_PATH) -> None:
    html_path.write_text(render_status_html(status), encoding='utf-8')
