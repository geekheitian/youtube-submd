#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from subscription_status import STATUS_HTML_PATH, STATUS_JSON_PATH, load_status, write_status_html


def main() -> None:
    parser = argparse.ArgumentParser(description='查看 youtube-submd 运行状态')
    parser.add_argument('--json', default=str(STATUS_JSON_PATH), help='状态 JSON 路径')
    parser.add_argument('--html', default=str(STATUS_HTML_PATH), help='状态 HTML 路径')
    parser.add_argument('--write-html', action='store_true', help='根据 JSON 重新生成 HTML')
    args = parser.parse_args()

    json_path = Path(args.json)
    html_path = Path(args.html)
    status = load_status(json_path)
    subscriptions = status.get('subscriptions', [])
    if not subscriptions:
        print('暂无状态记录。')
        return

    print(f"最近更新时间: {status.get('generated_at', '')}")
    for item in subscriptions:
        print(
            f"- {item.get('name')} [{item.get('platform')}] "
            f"结果={item.get('result')} 处理={item.get('processed')} "
            f"跳过={item.get('skipped')} 失败={item.get('failed')}"
        )
        if item.get('last_error'):
            print(f"  最近错误: {item.get('last_error')}")
        for file_path in item.get('recent_files', []):
            print(f"  文件: {file_path}")

    if args.write_html:
        write_status_html(status, html_path)
        print(f'✅ 已生成 HTML: {html_path}')


if __name__ == '__main__':
    main()
