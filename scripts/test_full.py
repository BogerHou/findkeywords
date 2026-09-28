"""Offline regression tests for the full sweep's audit and resume boundaries."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import probe_full as full


class FullTests(unittest.TestCase):
    def fields(self, title, description='', text='content ' * 40):
        return dict(title=title, description=description, h1=[], visible_text=text)

    def test_clear_placeholders(self):
        self.assertEqual(full.classify_page('', self.fields('aimicroprocessor.com for sale | Spaceship.com'))[0], 'skip')
        self.assertEqual(full.classify_page('', self.fields('Launching Soon')), ('skip', 'placeholder_page'))
        self.assertEqual(full.classify_page('', self.fields('h1 Lorem Ipsum', 'Lorem ipsum dolor sit amet')), ('skip', 'template_placeholder'))

    def test_article_and_javascript_are_not_garbage(self):
        self.assertEqual(full.classify_page('', self.fields('How to list a domain for sale', text='Long article. ' * 150))[0], 'pass')
        self.assertEqual(full.classify_page('<script></script>', self.fields('New calculator', text='')),
                         ('recheck', 'javascript_or_thin'))

    def test_resume_rejects_partial_duplicates_and_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'results.jsonl'
            p.write_text('{"domain":"example.com"}')
            with self.assertRaisesRegex(ValueError, 'Partial'):
                full.load_records(p)
            p.write_text('{"domain":"example.com"}\n' * 2)
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                full.load_records(p)
            p.write_text('{"domain":"unknown.com"}\n')
            with self.assertRaises(ValueError):
                full.load_records(p, {'example.com'})

    def test_rate_limit_stops_origin_not_unrelated_sites(self):
        with patch.object(full.FullCheck, 'run', return_value={'reason': 'rate_limited', 'stop_batch': True}):
            result = full.check({'domain': 'example.com'}, '/tmp/unused')
        self.assertFalse(result['stop_batch'])
        self.assertTrue(result['stopped_origin'])

    def test_global_and_host_request_spacing(self):
        class Lock:
            def __enter__(self): return self
            def __exit__(self, *args): pass
        class Last: value = 0
        clock = [100.0]
        def sleep(seconds): clock[0] += seconds
        moments = []
        def fetch(*args, **kwargs):
            moments.append(clock[0]); return {'status': 'ok'}
        with patch.object(full, '_lock', Lock()), patch.object(full, '_last', Last()), \
             patch.object(full.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(full.time, 'sleep', side_effect=sleep), \
             patch.object(full.pre.probe, 'fetch_public', side_effect=fetch):
            a, b = full.SharedTransport(), full.SharedTransport()
            a.get('https://example.com/robots.txt')
            b.get('https://example.net/robots.txt')
            a.get('https://example.com/')
        self.assertEqual(moments, [100, 100.5, 105])


if __name__ == '__main__':
    unittest.main()
