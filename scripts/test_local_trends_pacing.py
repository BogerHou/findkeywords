from datetime import datetime, timedelta, timezone
import tempfile
import unittest

from local_trends_pacing import Pacer, availability, retry_deadline


class PacingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = datetime(2026, 9, 28, 15, 0, tzinfo=timezone.utc)
        self.pacer = Pacer(self.temp.name, clock=lambda: self.now)
        self.item = {'keyword': 'example checker', 'stage': 'chart30'}

    def resume(self, delay=0):
        return self.pacer.resume((self.now + timedelta(seconds=delay)).isoformat(), 'User authorized slower continuation')

    def test_cooldown_cannot_be_ignored_by_a_new_process(self):
        self.resume(3600)
        other = Pacer(self.temp.name, clock=lambda: self.now)
        self.assertFalse(other.claim(self.item)['allowed'])
        self.now += timedelta(seconds=3599)
        self.assertFalse(other.claim(self.item)['allowed'])
        self.now += timedelta(seconds=1)
        self.assertTrue(other.claim(self.item)['allowed'])

    def test_inflight_claim_prevents_overlapping_browser_queries(self):
        self.resume()
        self.assertTrue(self.pacer.claim(self.item)['allowed'])
        self.now += timedelta(seconds=1000)
        result = self.pacer.claim({'keyword': 'other', 'stage': 'chart30'})
        self.assertEqual(result['state'], 'awaiting_capture')
        self.assertEqual(result['inflight']['keyword'], self.item['keyword'])
        with self.assertRaises(ValueError):
            self.pacer.success('other', 'chart30')

    def test_saved_progress_keeps_a_full_interval_after_completion(self):
        self.resume()
        self.pacer.claim(self.item)
        self.now += timedelta(seconds=15)
        self.pacer.success(**self.item)
        self.now += timedelta(seconds=59)
        self.assertFalse(self.pacer.claim(self.item)['allowed'])
        self.now += timedelta(seconds=1)
        self.assertTrue(self.pacer.claim(self.item)['allowed'])

    def test_repeated_429_extends_cooldown_and_honors_retry_after(self):
        self.resume()
        self.pacer.claim(self.item)
        first = self.pacer.cooldown('HTTP429')
        self.assertEqual(first['seconds_remaining'], 7200)
        self.now += timedelta(seconds=7200)
        self.pacer.claim(self.item)
        second = self.pacer.cooldown('HTTP429', '20000')
        self.assertEqual(second['seconds_remaining'], 20000)
        self.assertIsNone(self.pacer.read()['inflight'])

    def test_six_successes_reset_backoff_but_never_raise_query_rate(self):
        self.resume()
        for _ in range(6):
            self.assertTrue(self.pacer.claim(self.item)['allowed'])
            self.pacer.success(**self.item)
            self.now += timedelta(seconds=60)
        self.assertEqual(self.pacer.read()['rate_limit_level'], 0)
        self.pacer.claim(self.item)
        self.assertEqual(self.pacer.cooldown('HTTP429')['seconds_remaining'], 3600)

    def test_captcha_needs_input_and_is_not_automatically_resumed(self):
        self.resume()
        self.pacer.claim(self.item)
        self.pacer.block('CAPTCHA requires user action')
        self.now += timedelta(days=10)
        self.assertEqual(self.pacer.claim(self.item)['state'], 'blocked')

    def test_retry_after_http_date_and_invalid_header(self):
        self.assertEqual(retry_deadline('Mon, 28 Sep 2026 19:00:00 GMT', self.now), self.now + timedelta(hours=4))
        self.assertEqual(retry_deadline('unrecognized', self.now), self.now)


if __name__ == '__main__':
    unittest.main()
