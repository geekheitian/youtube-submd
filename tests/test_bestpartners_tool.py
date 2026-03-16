import tempfile
import unittest
from pathlib import Path

import bestpartners_tool as tool


class BestPartnersToolTests(unittest.TestCase):
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

    def test_sanitize_filename_replaces_illegal_chars_and_truncates(self):
        raw = 'A<B>:"C"/D\\E|F?G*' + 'x' * 100
        sanitized = tool.sanitize_filename(raw, max_length=20)
        self.assertEqual(sanitized, 'A_B___C__D_E_F_G_xxx')
        self.assertEqual(len(sanitized), 20)

    def test_get_channel_name_extracts_handle_and_fallback(self):
        self.assertEqual(
            tool.get_channel_name('https://www.youtube.com/@BestPartners/videos'),
            'BestPartners',
        )
        self.assertEqual(
            tool.get_channel_name('https://www.youtube.com/channel/UC123abc'),
            'UC123abc',
        )
        self.assertEqual(
            tool.get_channel_name('https://www.youtube.com/videos', default_channel_name='FallbackChannel'),
            'FallbackChannel',
        )

    def test_build_channel_context_uses_configured_content_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self.make_config(Path(tmpdir))
            context = tool.build_channel_context('https://www.youtube.com/@BestPartners/videos', config)
            self.assertEqual(context.name, 'BestPartners')
            self.assertEqual(context.display_name, '@BestPartners')
            self.assertEqual(context.channel_dir, Path(tmpdir) / '01-内容' / 'BestPartners')
            self.assertEqual(context.subtitles_dir, Path(tmpdir) / '01-内容' / 'BestPartners' / '字幕')
            self.assertEqual(context.summaries_dir, Path(tmpdir) / '01-内容' / 'BestPartners' / '摘要')

    def test_prepare_subtitle_text_cleans_vtt_content(self):
        vtt = """WEBVTT

1
00:00:00.000 --> 00:00:01.000
Hello world
Kind: captions
Language: zh-Hans

2
00:00:01.000 --> 00:00:02.000
Second line
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            subtitle_path = Path(tmpdir) / 'sample.vtt'
            subtitle_path.write_text(vtt, encoding='utf-8')
            subtitle_text = tool.prepare_subtitle_text(str(subtitle_path))
            self.assertEqual(subtitle_text, 'Hello world Second line')

    def test_find_existing_summary_matches_source_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self.make_config(Path(tmpdir))
            context = tool.build_channel_context('https://www.youtube.com/@BestPartners/videos', config)
            context.summaries_dir.mkdir(parents=True, exist_ok=True)
            summary_path = context.summaries_dir / 'existing.md'
            summary_path.write_text(
                '---\nsource: https://www.youtube.com/watch?v=video123\n---\n',
                encoding='utf-8',
            )

            match = tool.find_existing_summary('video123', context)
            missing = tool.find_existing_summary('video999', context)

            self.assertEqual(match, summary_path)
            self.assertIsNone(missing)

    def test_build_summary_markdown_includes_channel_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self.make_config(Path(tmpdir))
            context = tool.build_channel_context('https://www.youtube.com/@BestPartners/videos', config)
            publish_dates = tool.get_video_dates('20260301')
            markdown = tool.build_summary_markdown(
                title='测试标题',
                video_id='abc123',
                summary_text='### 核心主题\n测试摘要',
                provider_name='MiniMax-M2.5',
                context=context,
                publish_dates=publish_dates,
            )
            self.assertIn('channel: BestPartners', markdown)
            self.assertIn('channel_url: https://www.youtube.com/@BestPartners/videos', markdown)
            self.assertIn('author: @BestPartners', markdown)
            self.assertIn('## 结构化摘要', markdown)
            self.assertIn('MiniMax-M2.5', markdown)
            self.assertIn('published: 2026-03-01', markdown)

    def test_get_video_dates_uses_upload_date_when_available(self):
        dates = tool.get_video_dates('20260315')
        self.assertEqual(dates['compact'], '20260315')
        self.assertEqual(dates['display'], '2026-03-15')


if __name__ == '__main__':
    unittest.main()
