import tempfile
import unittest
from pathlib import Path
from unittest import mock

import youtumd as tool
import platform_adapters
from subscriptions import Glossary, Subscription


class PlatformAdaptersTests(unittest.TestCase):
    def make_config(self, base_dir: Path) -> tool.AppConfig:
        return tool.AppConfig(
            base_dir=base_dir,
            content_subdir="01-内容",
            default_channel_url=tool.DEFAULT_CHANNEL,
            default_channel_name=tool.DEFAULT_CHANNEL_NAME,
            default_limit=1,
            minimax_base_url=tool.DEFAULT_MINIMAX_BASE_URL,
            minimax_model=tool.DEFAULT_MINIMAX_MODEL,
        )

    @mock.patch('platform_adapters.youtube_tool.process_video', return_value=True)
    @mock.patch('platform_adapters.youtube_tool.process_video_with_asr_fallback', return_value=True)
    def test_youtube_adapter_routes_by_subtitle_strategy(self, mock_asr, mock_native):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self.make_config(Path(tmpdir))
            adapter = platform_adapters.YoutubeAdapter()
            native_subscription = Subscription(
                platform='youtube',
                name='BestPartners',
                url='https://www.youtube.com/@BestPartners/videos',
                subtitle_strategy='native',
            )
            asr_subscription = Subscription(
                platform='youtube',
                name='技术爬爬虾',
                url='https://www.youtube.com/@tech-shrimp/videos',
                subtitle_strategy='asr_fallback',
                glossary=Glossary(preferred_terms=['API'], alias_map={}, keep_original=[]),
            )
            context = adapter.build_context(native_subscription, config)
            video = {'id': 'abc123', 'title': 'Test'}

            adapter.process_video(video, native_subscription, context, config, dry_run=False, force=False)
            adapter.process_video(video, asr_subscription, context, config, dry_run=False, force=False)

            mock_native.assert_called_once()
            mock_asr.assert_called_once()
            self.assertEqual(mock_asr.call_args.kwargs['glossary'], asr_subscription.glossary)


if __name__ == '__main__':
    unittest.main()
