import tempfile
import unittest
from pathlib import Path

import subscription_status
import subscriptions


class SubscriptionsTests(unittest.TestCase):
    def test_manual_loader_reads_platform_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'subscriptions.yaml'
            config_path.write_text(
                """subscriptions:
  - platform: youtube
    name: Foo
    url: https://www.youtube.com/@foo/videos
    limit: 3
    enabled: true
  - platform: bilibili
    name: Bar
    url: https://space.bilibili.com/123/video
    limit: 2
    enabled: false
""",
                encoding='utf-8',
            )
            items = subscriptions.load_subscriptions(config_path)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].platform, 'youtube')
            self.assertEqual(items[0].name, 'Foo')

    def test_status_html_contains_subscription_name(self):
        html = subscription_status.render_status_html(
            {
                'generated_at': '2026-03-17T00:00:00',
                'subscriptions': [
                    {
                        'name': 'BestPartners',
                        'platform': 'youtube',
                        'last_run_at': '2026-03-17T00:00:00',
                        'result': 'ok',
                        'processed': 1,
                        'skipped': 0,
                        'failed': 0,
                        'last_error': '',
                        'recent_files': ['/tmp/a.md'],
                    }
                ],
            }
        )
        self.assertIn('BestPartners', html)
        self.assertIn('youtube', html)


if __name__ == '__main__':
    unittest.main()
