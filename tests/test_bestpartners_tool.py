import json
import subprocess
import tempfile
import urllib.error
import unittest
from unittest import mock
from pathlib import Path

import youtumd as tool
from subscriptions import Glossary


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

    def test_parse_available_subtitles_distinguishes_manual_and_auto(self):
        output = """[info] Available subtitles for test:
Language Name Formats
zh-Hans Chinese (Simplified) vtt

[info] Available automatic captions for test:
Language Name Formats
zh-Hans-zh Chinese (Simplified) from Chinese vtt
en English vtt
"""
        options = tool.parse_available_subtitles(output)
        self.assertEqual(
            options,
            [
                tool.SubtitleOption(code='zh-Hans', is_auto=False),
                tool.SubtitleOption(code='zh-Hans-zh', is_auto=True),
                tool.SubtitleOption(code='en', is_auto=True),
            ],
        )

    def test_choose_subtitle_option_prefers_exact_manual_then_exact_auto_code(self):
        manual = tool.choose_subtitle_option([
            tool.SubtitleOption(code='zh-Hans-zh', is_auto=True),
            tool.SubtitleOption(code='zh-Hans', is_auto=False),
        ])
        auto = tool.choose_subtitle_option([
            tool.SubtitleOption(code='zh-Hans-zh', is_auto=True),
            tool.SubtitleOption(code='en', is_auto=True),
        ])
        self.assertEqual(manual, tool.SubtitleOption(code='zh-Hans', is_auto=False))
        self.assertEqual(auto, tool.SubtitleOption(code='zh-Hans-zh', is_auto=True))

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

    def test_find_existing_subtitle_matches_source_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self.make_config(Path(tmpdir))
            context = tool.build_channel_context('https://www.youtube.com/@BestPartners/videos', config)
            context.subtitles_dir.mkdir(parents=True, exist_ok=True)
            subtitle_path = context.subtitles_dir / 'existing.md'
            subtitle_path.write_text(
                '---\nsource: https://www.youtube.com/watch?v=video123\n---\n',
                encoding='utf-8',
            )

            match = tool.find_existing_subtitle('video123', context)
            missing = tool.find_existing_subtitle('video999', context)

            self.assertEqual(match, subtitle_path)
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
            self.assertIn('### 核心主题', markdown)
            self.assertIn('MiniMax-M2.5', markdown)
            self.assertIn('published: 2026-03-01', markdown)

    def test_get_video_dates_uses_upload_date_when_available(self):
        dates = tool.get_video_dates('20260315')
        self.assertEqual(dates['compact'], '20260315')
        self.assertEqual(dates['display'], '2026-03-15')

    def test_cleanup_downloaded_subtitle_removes_temp_vtt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            subtitle_path = Path(tmpdir) / 'sample.vtt'
            subtitle_path.write_text('WEBVTT', encoding='utf-8')
            tool.cleanup_downloaded_subtitle(str(subtitle_path))
            self.assertFalse(subtitle_path.exists())

    def test_convert_subtitle_to_md_removes_old_noncanonical_file_on_force_retry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self.make_config(Path(tmpdir))
            context = tool.build_channel_context('https://www.youtube.com/@BestPartners/videos', config)
            context.subtitles_dir.mkdir(parents=True, exist_ok=True)
            old_path = context.subtitles_dir / '旧字幕.md'
            old_path.write_text('old', encoding='utf-8')

            publish_dates = tool.get_video_dates('20260318')
            saved_path = tool.convert_subtitle_to_md(
                video_id='abc123',
                title='测试标题',
                subtitle_text='字幕内容',
                lang='asr-zh',
                context=context,
                publish_dates=publish_dates,
                existing_subtitle=old_path,
            )

            self.assertFalse(old_path.exists())
            self.assertTrue(Path(saved_path).exists())
            self.assertTrue(saved_path.endswith('测试标题-20260318-字幕.md'))

    def test_save_summary_removes_old_noncanonical_file_on_force_retry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self.make_config(Path(tmpdir))
            context = tool.build_channel_context('https://www.youtube.com/@BestPartners/videos', config)
            context.summaries_dir.mkdir(parents=True, exist_ok=True)
            old_path = context.summaries_dir / '旧摘要.md'
            old_path.write_text('old', encoding='utf-8')

            publish_dates = tool.get_video_dates('20260318')
            saved_path = tool.save_summary(
                title='测试标题',
                video_id='abc123',
                content='摘要内容',
                context=context,
                publish_dates=publish_dates,
                existing_summary=old_path,
            )

            self.assertFalse(old_path.exists())
            self.assertTrue(Path(saved_path).exists())
            self.assertTrue(saved_path.endswith('测试标题-20260318.md'))

    def test_sanitize_summary_text_removes_prompt_leakage(self):
        raw = """、推理过程、草稿或中间分析

视频内容是关于 AI 概念的科普。

让我整理笔记内容：

### 核心主题
主题内容

### 关键观点
- 观点一

### 重要结论
结论内容

### 可行动点
- 行动一
"""
        cleaned = tool.sanitize_summary_text(raw)
        self.assertTrue(cleaned.startswith('### 核心主题'))
        self.assertNotIn('推理过程、草稿或中间分析', cleaned)
        self.assertNotIn('让我整理笔记内容', cleaned)
        self.assertIn('### 可行动点', cleaned)

    @mock.patch('youtumd.time.sleep', return_value=None)
    @mock.patch('youtumd.subprocess.run')
    def test_download_subtitle_retries_on_429_for_auto_subs(self, mock_run, _mock_sleep):
        first = mock.Mock(returncode=1, stdout='', stderr='ERROR: Unable to download video subtitles: HTTP Error 429: Too Many Requests')
        second = mock.Mock(returncode=0, stdout='Writing video subtitles', stderr='')

        with tempfile.TemporaryDirectory() as tmpdir:
            config = self.make_config(Path(tmpdir))
            context = tool.build_channel_context('https://www.youtube.com/@BestPartners/videos', config)
            context.subtitles_dir.mkdir(parents=True, exist_ok=True)

            call_count = {'count': 0}

            def run_side_effect(*args, **kwargs):
                result = first if call_count['count'] == 0 else second
                call_count['count'] += 1
                if call_count['count'] == 2:
                    (context.subtitles_dir / 'abc.zh-Hans-zh.vtt').write_text('WEBVTT', encoding='utf-8')
                return result

            mock_run.side_effect = run_side_effect

            option = tool.SubtitleOption(code='zh-Hans-zh', is_auto=True)
            subtitle_path = tool.download_subtitle('abc', context, option, retries=1)

            self.assertTrue(subtitle_path.endswith('abc.zh-Hans-zh.vtt'))
            self.assertEqual(mock_run.call_args_list[0].args[0][1], '--write-auto-subs')
            self.assertEqual(mock_run.call_count, 2)

    @mock.patch('youtumd.call_minimax')
    def test_correct_asr_text_includes_glossary_hint(self, mock_call_minimax):
        mock_call_minimax.return_value = '纠错后的文本'
        glossary = Glossary(
            preferred_terms=['OpenAI'],
            alias_map={'Open AI': 'OpenAI'},
            keep_original=['OpenAI'],
        )
        corrected = tool.correct_asr_text('测试标题', 'Open AI 发布了新模型', self.make_config(Path('/tmp')), glossary)
        self.assertEqual(corrected, '纠错后的文本')
        prompt = mock_call_minimax.call_args.kwargs['prompt']
        self.assertIn('术语提示：', prompt)
        self.assertIn('Open AI -> OpenAI', prompt)

    def test_preserves_enough_content_rejects_overcompressed_enhancement(self):
        original = '这是一个很长的原始字幕片段' * 20
        shortened = '这是一个很短的结果'
        self.assertFalse(tool.preserves_enough_content(original, shortened))
        self.assertTrue(tool.preserves_enough_content(original, original))

    @mock.patch('youtumd.urllib.request.urlopen')
    def test_can_reach_youtube_returns_true_on_success(self, mock_urlopen):
        mock_response = mock.MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_response
        self.assertTrue(tool.can_reach_youtube(timeout_seconds=1))

    @mock.patch('youtumd.urllib.request.urlopen', side_effect=urllib.error.URLError('timed out'))
    def test_can_reach_youtube_returns_false_on_failure(self, _mock_urlopen):
        self.assertFalse(tool.can_reach_youtube(timeout_seconds=1))

    @mock.patch('youtumd.call_minimax', return_value='明显缩短后的结果')
    def test_enhance_subtitle_chunk_with_minimax_falls_back_to_original_when_overcompressed(self, _mock_call):
        chunk = '原始字幕内容非常长，需要保留足够信息量。' * 20
        result = tool.enhance_subtitle_chunk_with_minimax(
            title='测试标题',
            chunk=chunk,
            config=self.make_config(Path('/tmp')),
            chunk_label='1/1',
            max_chars=1800,
        )
        self.assertEqual(result, [chunk.strip()])

    @mock.patch('youtumd.cleanup_temp_path')
    @mock.patch('youtumd.transcribe_audio_with_asr')
    @mock.patch('youtumd.capture_browser_audio')
    def test_transcribe_video_with_asr_merges_multiple_chunks(self, mock_capture, mock_transcribe, _mock_cleanup):
        audio1 = Path('/tmp/chunk1.webm')
        audio2 = Path('/tmp/chunk2.webm')
        mock_capture.side_effect = [
            (audio1, 70.0, 45.0),
            (audio2, 70.0, 70.0),
        ]
        mock_transcribe.side_effect = ['第一段', '第二段']

        with mock.patch('youtumd.get_asr_capture_seconds', return_value=45), \
             mock.patch('youtumd.get_asr_max_seconds', return_value=180), \
             mock.patch('youtumd.can_reach_youtube', return_value=True):
            merged = tool.transcribe_video_with_asr('https://www.youtube.com/watch?v=abc', 'abc')

        self.assertEqual(merged, '第一段 第二段')
        self.assertEqual(mock_capture.call_count, 2)
        self.assertEqual(mock_capture.call_args_list[0].kwargs['start_seconds'], 0.0)
        self.assertEqual(mock_capture.call_args_list[1].kwargs['start_seconds'], 45.0)

    @mock.patch('youtumd.capture_browser_audio')
    def test_transcribe_video_with_asr_stops_when_youtube_unreachable(self, mock_capture):
        with mock.patch('youtumd.can_reach_youtube', return_value=False):
            merged = tool.transcribe_video_with_asr('https://www.youtube.com/watch?v=abc', 'abc')

        self.assertIsNone(merged)
        mock_capture.assert_not_called()

    @mock.patch('youtumd.subprocess.run')
    def test_download_audio_with_ytdlp_returns_downloaded_file(self, mock_run):
        with tempfile.TemporaryDirectory() as tmpdir:
            work_root = Path(tmpdir)
            audio_path = work_root / 'abc-audio.webm'
            audio_path.write_text('audio', encoding='utf-8')

            mock_run.return_value = mock.Mock(returncode=0, stdout='', stderr='')
            with mock.patch('youtumd.get_asr_work_root', return_value=work_root):
                result = tool.download_audio_with_ytdlp(
                    'https://www.youtube.com/watch?v=abc',
                    'abc',
                )

        self.assertEqual(result, audio_path)
        self.assertEqual(mock_run.call_args.args[0][0], 'yt-dlp')
        self.assertIn('--no-playlist', mock_run.call_args.args[0])
        self.assertIn('-f', mock_run.call_args.args[0])

    @mock.patch('youtumd.cleanup_temp_path')
    @mock.patch('youtumd.transcribe_audio_with_asr', return_value='全文')
    @mock.patch('youtumd.download_audio_with_ytdlp')
    @mock.patch('youtumd.capture_browser_audio', return_value=None)
    def test_transcribe_video_with_asr_falls_back_to_ytdlp_audio(
        self,
        mock_capture,
        mock_download,
        mock_transcribe,
        _mock_cleanup,
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = Path(tmpdir) / 'abc-audio.webm'
            audio_path.write_text('audio', encoding='utf-8')
            mock_download.return_value = audio_path

            with mock.patch('youtumd.can_reach_youtube', return_value=True), \
                 mock.patch('youtumd.get_asr_capture_seconds', return_value=45), \
                 mock.patch('youtumd.get_asr_max_seconds', return_value=180):
                merged = tool.transcribe_video_with_asr('https://www.youtube.com/watch?v=abc', 'abc')

        self.assertEqual(merged, '全文')
        mock_capture.assert_called_once()
        mock_download.assert_called_once_with('https://www.youtube.com/watch?v=abc', 'abc')
        mock_transcribe.assert_called_once_with(audio_path)

    @mock.patch('youtumd.time.sleep', return_value=None)
    @mock.patch('youtumd.subprocess.run')
    def test_capture_browser_audio_retries_after_timeout(self, mock_run, _mock_sleep):
        timeout = subprocess.TimeoutExpired(cmd=['node'], timeout=120)
        output_path_holder = {}

        def run_side_effect(*args, **kwargs):
            if not output_path_holder:
                command = args[0]
                script_path = Path(command[1])
                output_path_holder['path'] = script_path.with_name('abc-001.webm')
                raise timeout
            output_path_holder['path'].write_text('audio', encoding='utf-8')
            return mock.Mock(returncode=0, stdout=json.dumps({
                'outPath': str(output_path_holder['path']),
                'duration': 90.0,
                'startTime': 45.0,
                'endTime': 90.0,
            }), stderr='')

        mock_run.side_effect = run_side_effect

        with tempfile.TemporaryDirectory() as tmpdir, \
             mock.patch('youtumd.get_asr_work_root', return_value=Path(tmpdir)), \
             mock.patch('youtumd.get_asr_capture_retries', return_value=2):
            result = tool.capture_browser_audio(
                video_url='https://www.youtube.com/watch?v=abc',
                video_id='abc',
                chunk_index=1,
                start_seconds=45.0,
                capture_seconds=45,
            )

        self.assertIsNotNone(result)
        self.assertEqual(mock_run.call_count, 2)
        self.assertEqual(result[1], 90.0)
        self.assertEqual(result[2], 90.0)

    @mock.patch('youtumd.save_summary')
    @mock.patch('youtumd.generate_summary', return_value='summary')
    @mock.patch('youtumd.convert_subtitle_to_md', return_value='/tmp/subtitle.md')
    @mock.patch('youtumd.enhance_subtitle_text', return_value='增强文本')
    @mock.patch('youtumd.correct_asr_text', return_value='纠错文本')
    @mock.patch('youtumd.transcribe_video_with_asr', return_value='原始转写')
    @mock.patch('youtumd.translate_to_chinese', return_value='中文标题')
    def test_process_video_with_asr_fallback_reuses_existing_post_pipeline(
        self,
        mock_translate,
        _mock_transcribe_video,
        mock_correct,
        mock_enhance,
        mock_convert,
        mock_generate,
        mock_save,
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self.make_config(Path(tmpdir))
            context = tool.build_channel_context('https://www.youtube.com/@tech-shrimp/videos', config, override_name='技术爬爬虾')
            context.subtitles_dir.mkdir(parents=True, exist_ok=True)
            context.summaries_dir.mkdir(parents=True, exist_ok=True)

            success = tool.process_video_with_asr_fallback(
                {'id': 'abc123', 'title': 'Original Title', 'upload_date': '20260318'},
                context,
                config,
                glossary=Glossary(preferred_terms=['API'], alias_map={}, keep_original=[]),
            )

            self.assertTrue(success)
            mock_translate.assert_called_once()
            mock_correct.assert_called_once()
            mock_enhance.assert_called_once_with('中文标题', '纠错文本', config)
            mock_convert.assert_called_once()
            self.assertEqual(mock_convert.call_args.args[3], 'asr-zh')
            mock_generate.assert_called_once()
            mock_save.assert_called_once()


if __name__ == '__main__':
    unittest.main()
