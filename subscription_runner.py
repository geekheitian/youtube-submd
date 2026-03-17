#!/usr/bin/env python3

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import bestpartners_tool as shared
from platform_adapters import get_adapter
from subscription_status import STATUS_HTML_PATH, STATUS_JSON_PATH, load_status, write_status, write_status_html
from subscriptions import Subscription, load_subscriptions


def parse_args() -> argparse.Namespace:
    config = shared.load_config()
    parser = argparse.ArgumentParser(description='统一订阅入口（YouTube / Bilibili / Douyin scaffold）')
    parser.add_argument('--all-subscriptions', action='store_true', help='处理 subscriptions.yaml 中所有启用订阅')
    parser.add_argument('--subscriptions-file', type=Path, default=None, help='指定 subscriptions.yaml 路径')
    parser.add_argument('--name', help='只处理指定订阅名称')
    parser.add_argument('--platform', help='只处理指定平台')
    parser.add_argument('--dry-run', action='store_true', help='预览模式，不下载字幕')
    parser.add_argument('--force', action='store_true', help='强制重处理')
    parser.add_argument('--base-dir', help='覆盖输出根目录')
    parser.add_argument('--content-subdir', help='覆盖内容子目录')
    parser.add_argument('--status-json', type=Path, default=STATUS_JSON_PATH, help='状态 JSON 输出路径')
    parser.add_argument('--status-html', type=Path, default=STATUS_HTML_PATH, help='状态 HTML 输出路径')
    parser.add_argument('--write-status-only', action='store_true', help='仅重建状态 HTML，不执行订阅')
    parser.add_argument('--default-limit', type=int, default=config.default_limit, help='覆盖默认 limit（仅对未配置订阅生效）')
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> shared.AppConfig:
    config = shared.load_config()
    if args.base_dir:
        return shared.AppConfig(
            base_dir=Path(args.base_dir).expanduser(),
            content_subdir=args.content_subdir or config.content_subdir,
            default_channel_url=config.default_channel_url,
            default_channel_name=config.default_channel_name,
            default_limit=args.default_limit,
            minimax_base_url=config.minimax_base_url,
            minimax_model=config.minimax_model,
        )
    if args.content_subdir or args.default_limit != config.default_limit:
        return shared.AppConfig(
            base_dir=config.base_dir,
            content_subdir=args.content_subdir or config.content_subdir,
            default_channel_url=config.default_channel_url,
            default_channel_name=config.default_channel_name,
            default_limit=args.default_limit,
            minimax_base_url=config.minimax_base_url,
            minimax_model=config.minimax_model,
        )
    return config


def select_subscriptions(items: List[Subscription], name: Optional[str], platform: Optional[str]) -> List[Subscription]:
    result = items
    if name:
        result = [item for item in result if item.name == name]
    if platform:
        result = [item for item in result if item.platform == platform.lower()]
    return result


def recent_files(directory: Path, limit: int = 3) -> List[str]:
    if not directory.is_dir():
        return []
    files = sorted(
        [path for path in directory.glob('*.md') if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return [str(path) for path in files[:limit]]


def run_subscription(subscription: Subscription, config: shared.AppConfig, dry_run: bool, force: bool) -> Dict:
    adapter = get_adapter(subscription.platform)
    context = adapter.build_context(subscription, config)
    context.subtitles_dir.mkdir(parents=True, exist_ok=True)
    context.summaries_dir.mkdir(parents=True, exist_ok=True)

    print('=' * 50)
    print(f'📺 [{subscription.platform}] {subscription.name}')
    print(f'URL: {subscription.url} | limit: {subscription.limit}')
    print('=' * 50)

    started_at = datetime.now()
    videos = adapter.list_videos(subscription, config)
    if not videos:
        return {
            'name': subscription.name,
            'platform': subscription.platform,
            'url': subscription.url,
            'last_run_at': started_at.isoformat(timespec='seconds'),
            'result': 'no_videos',
            'processed': 0,
            'skipped': 0,
            'failed': 0,
            'last_error': '无法获取视频列表',
            'recent_files': recent_files(context.summaries_dir),
        }

    processed = 0
    skipped = 0
    failed = 0
    last_error = ''
    for video in videos:
        existing = adapter.find_existing_summary(video, subscription, context)
        if existing and not force:
            skipped += 1
            continue
        success = adapter.process_video(video, subscription, context, config, dry_run, force)
        if success:
            processed += 1
        else:
            failed += 1
            last_error = f"处理失败: {video.get('title', video.get('id', 'unknown'))}"

    result = 'ok'
    if failed and not processed:
        result = 'failed'
    elif failed:
        result = 'partial'
    elif skipped and not processed:
        result = 'skipped'

    return {
        'name': subscription.name,
        'platform': subscription.platform,
        'url': subscription.url,
        'last_run_at': datetime.now().isoformat(timespec='seconds'),
        'result': result,
        'processed': processed,
        'skipped': skipped,
        'failed': failed,
        'last_error': last_error,
        'recent_files': recent_files(context.summaries_dir),
    }


def rebuild_status_html(status_json_path: Path, status_html_path: Path) -> None:
    status = load_status(status_json_path)
    write_status_html(status, status_html_path)
    print(f'✅ 已生成状态面板: {status_html_path}')


def main() -> None:
    shared.load_dotenv()
    args = parse_args()
    if args.write_status_only:
        rebuild_status_html(args.status_json, args.status_html)
        return

    config = build_config(args)
    subscriptions = load_subscriptions(args.subscriptions_file)
    subscriptions = select_subscriptions(subscriptions, args.name, args.platform)

    if not subscriptions:
        print('❌ 没有可执行的订阅，请检查 subscriptions.yaml 或筛选条件。')
        return

    if not args.all_subscriptions and len(subscriptions) > 1 and not args.name and not args.platform:
        print('⚠️ 未指定 --all-subscriptions，默认仍执行全部已启用订阅。')

    results = [run_subscription(subscription, config, args.dry_run, args.force) for subscription in subscriptions]
    status = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'subscriptions': results,
    }
    write_status(status, args.status_json)
    write_status_html(status, args.status_html)

    total_processed = sum(item['processed'] for item in results)
    total_skipped = sum(item['skipped'] for item in results)
    total_failed = sum(item['failed'] for item in results)

    print('\n' + '=' * 50)
    print(f'✅ 全部完成：处理 {total_processed}，跳过 {total_skipped}，失败 {total_failed}')
    print(f'📄 状态文件: {args.status_json}')
    print(f'🖥️ 状态面板: {args.status_html}')
    print('=' * 50)


if __name__ == '__main__':
    main()
