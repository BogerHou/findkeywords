from datetime import date, timedelta
import unittest
from urllib.parse import parse_qs, urlsplit

from research_pipeline import extract, terms_in_field
from trends_full import evaluate_30, evaluate_background, explore_url, windows


class TrendTests(unittest.TestCase):
    def setUp(self):
        self.window = windows(date(2026, 9, 28))

    def points(self, values, start=None):
        start = date.fromisoformat(start or self.window['start'])
        return [{'date': str(start + timedelta(days=i)), 'value': v, 'partial': False} for i, v in enumerate(values)]

    def test_exact_threshold_and_sustained_signal(self):
        r = evaluate_30(self.points([0] * 16 + [10] * 7 + [20] * 7), self.window)
        self.assertTrue(r['eligible'])
        self.assertEqual(r['ratio'], 2)
        r = evaluate_30(self.points([0] * 16 + [10] * 7 + [19] * 7), self.window)
        self.assertFalse(r['eligible'])

    def test_zero_baseline_not_infinite_and_spikes_rejected(self):
        r = evaluate_30(self.points([0] * 23 + [20] * 7), self.window)
        self.assertTrue(r['eligible'])
        self.assertIsNone(r['ratio'])
        r = evaluate_30(self.points([0] * 23 + [1] * 6 + [100]), self.window)
        self.assertFalse(r['eligible'])

    def test_missing_partial_and_zero_not_fabricated(self):
        self.assertEqual(evaluate_30(self.points([0] * 30), self.window)['status'], 'below_reporting_threshold')
        self.assertEqual(evaluate_30(self.points([0] * 29), self.window)['status'], 'incomplete_or_non_daily')
        p = self.points([1] * 30); p[-1]['partial'] = True
        self.assertFalse(evaluate_30(p, self.window)['eligible'])

    def test_background_excludes_old_signal_and_missing_dates(self):
        start, end = date.fromisoformat(self.window['background_start']), date.fromisoformat(self.window['end'])
        values = [0] * ((end - start).days + 1)
        values[-10:] = [50] * 10
        points = self.points(values, str(start))
        self.assertTrue(evaluate_background(points, self.window)['eligible'])
        points[10]['value'] = 5
        self.assertFalse(evaluate_background(points, self.window)['eligible'])
        points[10]['value'] = 0
        self.assertFalse(evaluate_background(points[:20] + points[50:], self.window)['eligible'])

    def test_query_is_encoded_once(self):
        q = parse_qs(urlsplit(explore_url('agent permission matrix', '2026-08-29', '2026-09-27')).query)
        self.assertEqual(q['q'], ['agent permission matrix'])

    def test_literal_extraction_and_domain_not_used_as_keyword(self):
        self.assertIn('ai voice generator', terms_in_field('Free AI Voice Generator | Example', {'generator', 'example'}))
        self.assertIn('logo maker svg', terms_in_field('Logo Maker SVG – Free SVG Logo Maker Online', {'maker', 'online'}))
        self.assertIn('font detector from image', terms_in_field('Font Detector From Image – Identify Fonts Online', {'detector', 'online'}))
        self.assertEqual(terms_in_field('Welcome to our official website', {'generator'}), [])
        records = [{'domain': 'newvoicegenerator.com', 'decision': 'pass', 'reason': 'html_with_content',
                    'page': {'title': 'Welcome to our official website'}}]
        candidates, audit = extract(records, {'generator'})
        self.assertEqual(candidates, [])
        self.assertEqual(audit[0]['keyword_status'], 'needs_keyword_review')


if __name__ == '__main__':
    unittest.main()
