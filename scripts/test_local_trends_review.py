from datetime import date, timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import local_trends_review as review
from local_trends_review import csv_points, next_stage, validate_url
from trends_full import windows


class LocalBrowserEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.window = windows(date(2026, 9, 28))
        self.url = 'https://trends.google.com/trends/explore?date=2026-08-29%202026-09-27&geo=US&q=da%20checker'

    def csv(self, values, heading='da checker: (美国)'):
        start = date.fromisoformat(self.window['start'])
        rows = ['类别：所有类别', '', '日,' + heading]
        rows += [str(start + timedelta(days=i)) + ',' + str(v) for i, v in enumerate(values)]
        return '\n'.join(rows).encode()

    def test_stale_chart_and_truncated_dates_rejected(self):
        self.assertEqual(len(csv_points(self.csv([0] * 30), 'da checker', self.window, 'chart30')), 30)
        with self.assertRaisesRegex(ValueError, 'stale chart'):
            csv_points(self.csv([0] * 30, 'other: (美国)'), 'da checker', self.window, 'chart30')
        with self.assertRaisesRegex(ValueError, '30 complete'):
            csv_points(self.csv([0] * 29), 'da checker', self.window, 'chart30')

    def test_missing_or_small_values_are_not_fabricated_zeroes(self):
        for value in ('', '<1', '429', 'Error'):
            with self.assertRaises(ValueError):
                csv_points(self.csv([0] * 29 + [value]), 'da checker', self.window, 'chart30')

    def test_query_scope_and_double_encoding_checked(self):
        validate_url(self.url, 'da checker', self.window, 'chart30')
        for url in (self.url.replace('geo=US', 'geo=GB'), self.url.replace('%20checker', '%2520checker'), self.url + '&gprop=youtube'):
            with self.assertRaises(ValueError):
                validate_url(url, 'da checker', self.window, 'chart30')

    def test_growth_needs_background_and_repeat(self):
        p = csv_points(self.csv([0] * 16 + [10] * 7 + [20] * 7), 'da checker', self.window, 'chart30')
        record = {'charts': {'chart30': {'status': 'chart', 'points': p}}}
        self.assertEqual(next_stage(record, self.window), 'background')
        record['charts']['background'] = {'status': 'below_reporting_threshold_no_chart', 'points': []}
        self.assertIsNone(next_stage(record, self.window))
        p = csv_points(self.csv([0] * 30), 'da checker', self.window, 'chart30')
        self.assertIsNone(next_stage({'charts': {'chart30': {'status': 'chart', 'points': p}}}, self.window))

    def test_cloud_capture_keeps_source_and_legacy_captures_stay_local(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / 'results'
            run.mkdir()
            (root / 'site').mkdir()
            queue = {'window': self.window, 'excluded': [],
                     'candidates': [{'keyword': 'da checker'}, {'keyword': 'second term'}]}
            csv = root / 'chart.csv'
            args = SimpleNamespace(keyword='da checker', stage='chart30', url=self.url,
                                   csv=csv, dom=None, captured_at='2026-09-29T02:00:00Z')
            with patch.object(review, 'ROOT', root), patch.object(review, 'RUN', run):
                csv.write_bytes(self.csv([0] * 30))
                review.ingest(args, queue)
                records = json.loads((run / 'records.json').read_text())
                # Older captures predate the execution field.
                del records['da checker']['charts']['chart30']['execution']
                (run / 'records.json').write_text(json.dumps(records))
                args.keyword = 'second term'
                args.url = self.url.replace('da%20checker', 'second%20term')
                args.execution = 'browserless_cloud'
                csv.write_bytes(self.csv([0] * 30, 'second term: (美国)'))
                review.ingest(args, queue)
                summary, pending = review.publish(queue)
                self.assertEqual(summary['execution'], 'mixed_browser')
                self.assertEqual(summary['evidence_executions'],
                                 {'local_browser': 1, 'browserless_cloud': 1})
                self.assertEqual(pending, [])
                records = json.loads((run / 'records.json').read_text())
                cloud = records['second term']['charts']['chart30']
                self.assertIn('Browserless cloud browser', cloud['source'])
                self.assertIn('local browser', records['da checker']['charts']['chart30']['source'])
                self.assertEqual((root / 'site' / cloud['evidence']).read_bytes(), csv.read_bytes())


if __name__ == '__main__':
    unittest.main()
