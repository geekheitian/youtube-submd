import tempfile
import unittest
from pathlib import Path

import bilibili_tool as tool


class BilibiliToolTests(unittest.TestCase):
    def test_normalize_space_url_adds_video_suffix(self):
        self.assertEqual(
            tool.normalize_space_url("https://space.bilibili.com/513194466"),
            "https://space.bilibili.com/513194466/video",
        )
        self.assertEqual(
            tool.normalize_space_url("https://space.bilibili.com/513194466/video"),
            "https://space.bilibili.com/513194466/video",
        )

    def test_parse_playlist_line_keeps_title_and_id(self):
        video = tool.parse_playlist_line("测试标题|BV1UKZtBNE42|20260317")
        self.assertEqual(video["title"], "测试标题")
        self.assertEqual(video["id"], "BV1UKZtBNE42")
        self.assertEqual(video["upload_date"], "20260317")

    def test_parse_playlist_line_keeps_title_with_pipes(self):
        video = tool.parse_playlist_line("A | B | C|BV1UKZtBNE42|20260317")
        self.assertEqual(video["title"], "A | B | C")
        self.assertEqual(video["id"], "BV1UKZtBNE42")

    def test_extract_subtitle_lines_from_json_reads_body_content(self):
        content = '{"body":[{"content":"第一句"},{"content":"第二句"}]}'
        self.assertEqual(tool.extract_subtitle_lines_from_json(content), ["第一句", "第二句"])

    def test_extract_subtitle_lines_from_text_strips_timestamps(self):
        content = """WEBVTT

1
00:00:00.000 --> 00:00:02.000
第一句

2
00:00:02.000 --> 00:00:04.000
第二句
"""
        self.assertEqual(tool.extract_subtitle_lines_from_text(content), ["第一句", "第二句"])

    def test_find_existing_summary_matches_bilibili_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = tool.load_config()
            config = config.__class__(
                base_dir=Path(tmpdir),
                content_subdir=config.content_subdir,
                default_channel_url=config.default_channel_url,
                default_channel_name=config.default_channel_name,
                default_limit=config.default_limit,
                minimax_base_url=config.minimax_base_url,
                minimax_model=config.minimax_model,
            )
            context = tool.build_space_context("https://space.bilibili.com/513194466/video", config)
            context.summaries_dir.mkdir(parents=True, exist_ok=True)
            summary_path = context.summaries_dir / "existing.md"
            summary_path.write_text(
                "---\nsource: https://www.bilibili.com/video/BV1UKZtBNE42\n---\n",
                encoding="utf-8",
            )

            match = tool.find_existing_summary("https://www.bilibili.com/video/BV1UKZtBNE42", context)
            self.assertEqual(match, summary_path)

    def test_convert_raw_cookie_header_to_netscape(self):
        converted = tool.convert_raw_cookie_header_to_netscape("SESSDATA=abc; bili_jct=def")
        self.assertIn("# Netscape HTTP Cookie File", converted)
        self.assertIn("\tSESSDATA\tabc", converted)
        self.assertIn("\tbili_jct\tdef", converted)

    def test_is_raw_cookie_header_detects_single_line_cookie(self):
        self.assertTrue(tool.is_raw_cookie_header("SESSDATA=abc; bili_jct=def"))
        self.assertFalse(tool.is_raw_cookie_header("# Netscape HTTP Cookie File\n.example.com\tTRUE"))


if __name__ == "__main__":
    unittest.main()
