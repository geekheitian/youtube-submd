import unittest
from unittest import mock
from pathlib import Path
import sys
import os


class TranscriptServiceTests(unittest.TestCase):
    def _svc_import(self, name):
        project_root = str(Path(__file__).resolve().parent.parent.parent)
        for _k in list(sys.modules.keys()):
            if _k == "services" or _k.startswith("services."):
                sys.modules.pop(_k, None)
        sys.path.insert(0, project_root)
        if name == "transcript":
            from services.transcript import (
                YouTubeTranscriptService,
                TranscriptResult,
                SubtitleOption,
            )

            return YouTubeTranscriptService, TranscriptResult, SubtitleOption
        raise ValueError(f"Unknown service: {name}")

    def test_get_transcript_returns_result_on_success(self):
        YouTubeTranscriptService, TranscriptResult, _ = self._svc_import("transcript")
        svc = YouTubeTranscriptService()

        video_info_output = "Test Video Title|20260327"
        subtitle_output = "[info] Available subtitles for test123:\nLanguage      Formats...\nzh-Hans       vtt, ttml, srv2"

        def mock_subprocess_run(cmd, *args, **kwargs):
            if "--print" in cmd and "%(title)s" in " ".join(cmd):
                mocked = mock.MagicMock()
                mocked.returncode = 0
                mocked.stdout = video_info_output
                mocked.stderr = ""
                return mocked
            if "--list-subs" in cmd:
                mocked = mock.MagicMock()
                mocked.returncode = 0
                mocked.stdout = subtitle_output
                mocked.stderr = ""
                return mocked
            if "--write-subs" in cmd or "--write-auto-subs" in cmd:
                mocked = mock.MagicMock()
                mocked.returncode = 0
                mocked.stdout = "Writing video subtitles"
                mocked.stderr = "Writing video subtitles"
                return mocked
            mocked = mock.MagicMock()
            mocked.returncode = 0
            mocked.stdout = ""
            mocked.stderr = ""
            return mocked

        with mock.patch("subprocess.run", side_effect=mock_subprocess_run):
            with mock.patch(
                "services.transcript.prepare_subtitle_text",
                return_value="这是第一行字幕 这是第二行字幕",
            ):
                with mock.patch("services.transcript.cleanup_downloaded_subtitle"):
                    with mock.patch(
                        "services.transcript.Path.glob",
                        return_value=[Path("/tmp/test.vtt")],
                    ):
                        with mock.patch("builtins.open", mock.MagicMock()):
                            result = svc.get_transcript("test123")

        self.assertIsInstance(result, TranscriptResult)
        self.assertEqual(result.video_id, "test123")
        self.assertEqual(result.title, "Test Video Title")
        self.assertEqual(result.language, "zh-Hans")
        self.assertEqual(result.source_url, "https://www.youtube.com/watch?v=test123")

    def test_get_transcript_returns_none_when_no_subtitles(self):
        YouTubeTranscriptService, _, _ = self._svc_import("transcript")
        svc = YouTubeTranscriptService()

        def mock_subprocess_run(cmd, *args, **kwargs):
            mocked = mock.MagicMock()
            if "--print" in cmd:
                mocked.returncode = 0
                mocked.stdout = "Some Title|20260327"
                mocked.stderr = ""
            else:
                mocked.returncode = 0
                mocked.stdout = ""
                mocked.stderr = ""
            return mocked

        with mock.patch("subprocess.run", side_effect=mock_subprocess_run):
            result = svc.get_transcript("test_no_subs")

        self.assertIsNone(result)

    def test_choose_subtitle_option_prefers_zh_hans(self):
        _, _, SubtitleOption = self._svc_import("transcript")
        from services.transcript import YouTubeTranscriptService

        svc = YouTubeTranscriptService()
        options = [
            SubtitleOption(code="en", is_auto=False),
            SubtitleOption(code="zh-Hans", is_auto=False),
            SubtitleOption(code="zh-Hant", is_auto=True),
        ]
        chosen = svc.choose_subtitle_option(options)
        self.assertEqual(chosen.code, "zh-Hans")
        self.assertFalse(chosen.is_auto)

    def test_choose_subtitle_option_falls_back_to_zh_hant(self):
        _, _, SubtitleOption = self._svc_import("transcript")
        from services.transcript import YouTubeTranscriptService

        svc = YouTubeTranscriptService()
        options = [
            SubtitleOption(code="en", is_auto=False),
            SubtitleOption(code="zh-Hant", is_auto=True),
        ]
        chosen = svc.choose_subtitle_option(options)
        self.assertEqual(chosen.code, "zh-Hant")
        self.assertTrue(chosen.is_auto)


class SummaryServiceTests(unittest.TestCase):
    def _summary_import(self):
        project_root = str(Path(__file__).resolve().parent.parent.parent)
        for _k in list(sys.modules.keys()):
            if _k == "services" or _k.startswith("services."):
                sys.modules.pop(_k, None)
        sys.path.insert(0, project_root)
        from services.summary import YouTubeSummaryService, SummaryResult
        from youtumd import AppConfig

        return YouTubeSummaryService, SummaryResult, AppConfig

    def test_generate_summary_returns_result_on_minimax_success(self):
        YouTubeSummaryService, SummaryResult, AppConfig = self._summary_import()
        config = AppConfig(
            base_dir=Path("/tmp/test"),
            content_subdir="content",
            default_channel_url="https://www.youtube.com/@test",
            default_channel_name="test",
            default_limit=10,
            minimax_base_url="https://api.minimax.chat/v1",
            minimax_model="MiniMax-M2.7",
        )
        svc = YouTubeSummaryService(config)

        import json

        mock_response_data = {
            "base_resp": {"status_code": 0},
            "choices": [{"message": {"content": "### 核心主题\n测试摘要内容"}}],
        }
        mock_response_bytes = json.dumps(mock_response_data).encode("utf-8")

        mock_response = mock.MagicMock()
        mock_response.read.return_value = mock_response_bytes
        mock_response.__enter__ = mock.MagicMock(return_value=mock_response)
        mock_response.__exit__ = mock.MagicMock(return_value=False)

        with mock.patch.dict(os.environ, {"MINIMAX_API_KEY": "test-key"}):
            with mock.patch("urllib.request.urlopen", return_value=mock_response):
                result = svc.generate_summary("Test Title", "test123", "这是字幕内容")

        self.assertIsInstance(result, SummaryResult)
        self.assertEqual(result.video_id, "test123")
        self.assertEqual(result.title, "Test Title")
        self.assertEqual(result.provider, "MiniMax")
        self.assertIn("核心主题", result.summary)
        self.assertEqual(result.source_url, "https://www.youtube.com/watch?v=test123")

    def test_generate_summary_raises_when_no_provider_available(self):
        YouTubeSummaryService, _, AppConfig = self._summary_import()
        config = AppConfig(
            base_dir=Path("/tmp/test"),
            content_subdir="content",
            default_channel_url="https://www.youtube.com/@test",
            default_channel_name="test",
            default_limit=10,
            minimax_base_url="https://api.minimax.chat/v1",
            minimax_model="MiniMax-M2.7",
        )
        svc = YouTubeSummaryService(config)

        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch(
                "urllib.request.urlopen", side_effect=Exception("no network")
            ):
                with self.assertRaises(ValueError) as ctx:
                    svc.generate_summary("Test Title", "test123", "字幕内容")
        self.assertIn("test123", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
