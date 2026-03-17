from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Protocol

import bestpartners_tool as youtube_tool
import bilibili_tool
from subscriptions import Subscription


class PlatformAdapter(Protocol):
    platform_name: str

    def build_context(self, subscription: Subscription, config: youtube_tool.AppConfig) -> youtube_tool.ChannelContext: ...
    def list_videos(self, subscription: Subscription, config: youtube_tool.AppConfig) -> List[Dict[str, str]]: ...
    def process_video(
        self,
        video: Dict[str, str],
        subscription: Subscription,
        context: youtube_tool.ChannelContext,
        config: youtube_tool.AppConfig,
        dry_run: bool,
        force: bool,
    ) -> bool: ...
    def find_existing_summary(
        self,
        video: Dict[str, str],
        subscription: Subscription,
        context: youtube_tool.ChannelContext,
    ) -> Optional[Path]: ...


@dataclass(frozen=True)
class YoutubeAdapter:
    platform_name: str = 'youtube'

    def build_context(self, subscription: Subscription, config: youtube_tool.AppConfig) -> youtube_tool.ChannelContext:
        return youtube_tool.build_channel_context(subscription.url, config, override_name=subscription.name)

    def list_videos(self, subscription: Subscription, config: youtube_tool.AppConfig) -> List[Dict[str, str]]:
        return youtube_tool.get_channel_videos(subscription.url, subscription.limit)

    def process_video(
        self,
        video: Dict[str, str],
        subscription: Subscription,
        context: youtube_tool.ChannelContext,
        config: youtube_tool.AppConfig,
        dry_run: bool,
        force: bool,
    ) -> bool:
        return youtube_tool.process_video(video, context, config, dry_run=dry_run, force=force)

    def find_existing_summary(
        self,
        video: Dict[str, str],
        subscription: Subscription,
        context: youtube_tool.ChannelContext,
    ) -> Optional[Path]:
        return youtube_tool.find_existing_summary(video['id'], context)


@dataclass(frozen=True)
class BilibiliAdapter:
    platform_name: str = 'bilibili'

    def build_context(self, subscription: Subscription, config: youtube_tool.AppConfig) -> youtube_tool.ChannelContext:
        return bilibili_tool.build_space_context(subscription.url, config, override_name=subscription.name)

    def list_videos(self, subscription: Subscription, config: youtube_tool.AppConfig) -> List[Dict[str, str]]:
        cookies_file, cookies_from_browser, temp_cookie = bilibili_tool.prepare_cookie_inputs(
            subscription.cookies_file,
            subscription.cookies_from_browser,
        )
        try:
            return bilibili_tool.get_space_videos(subscription.url, subscription.limit, cookies_file, cookies_from_browser)
        finally:
            bilibili_tool.cleanup_temp_cookie_file(temp_cookie)

    def process_video(
        self,
        video: Dict[str, str],
        subscription: Subscription,
        context: youtube_tool.ChannelContext,
        config: youtube_tool.AppConfig,
        dry_run: bool,
        force: bool,
    ) -> bool:
        cookies_file, cookies_from_browser, temp_cookie = bilibili_tool.prepare_cookie_inputs(
            subscription.cookies_file,
            subscription.cookies_from_browser,
        )
        try:
            return bilibili_tool.process_video(
                video,
                context,
                config,
                cookies_file,
                cookies_from_browser,
                dry_run=dry_run,
                force=force,
            )
        finally:
            bilibili_tool.cleanup_temp_cookie_file(temp_cookie)

    def find_existing_summary(
        self,
        video: Dict[str, str],
        subscription: Subscription,
        context: youtube_tool.ChannelContext,
    ) -> Optional[Path]:
        return bilibili_tool.find_existing_summary(bilibili_tool.get_video_url(video['id']), context)


@dataclass(frozen=True)
class DouyinAdapter:
    platform_name: str = 'douyin'

    def build_context(self, subscription: Subscription, config: youtube_tool.AppConfig) -> youtube_tool.ChannelContext:
        return youtube_tool.ChannelContext(url=subscription.url, name=subscription.name, content_root=config.content_root)

    def list_videos(self, subscription: Subscription, config: youtube_tool.AppConfig) -> List[Dict[str, str]]:
        print('⚠️ 抖音适配器目前仅为预留骨架，尚未实现抓取。')
        return []

    def process_video(
        self,
        video: Dict[str, str],
        subscription: Subscription,
        context: youtube_tool.ChannelContext,
        config: youtube_tool.AppConfig,
        dry_run: bool,
        force: bool,
    ) -> bool:
        print('⚠️ 抖音适配器目前仅为预留骨架，尚未实现处理。')
        return False

    def find_existing_summary(
        self,
        video: Dict[str, str],
        subscription: Subscription,
        context: youtube_tool.ChannelContext,
    ) -> Optional[Path]:
        return None


ADAPTERS: Dict[str, PlatformAdapter] = {
    'youtube': YoutubeAdapter(),
    'bilibili': BilibiliAdapter(),
    'douyin': DouyinAdapter(),
}


def get_adapter(platform: str) -> PlatformAdapter:
    normalized = platform.strip().lower()
    adapter = ADAPTERS.get(normalized)
    if adapter is None:
        raise ValueError(f'不支持的平台: {platform}')
    return adapter
