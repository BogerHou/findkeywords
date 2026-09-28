import tempfile
from pathlib import Path
import unittest

from build_expansion_queue import select
from build_roots_site import RootMatcher
from extract_expansion import extract, literal_phrases


class ExpansionTests(unittest.TestCase):
    def test_new_lists_deduplicate_and_never_retry_old_domains(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / '2026-09-27.txt'
            p.write_text('oldgenerator.com\nnewgenerator.net\nnewgenerator.net\nhello.com\nhttps://badgenerator.com\n')
            matcher = RootMatcher({'roots': [{'term': 'Generator'}]})
            rows, counts, excluded, invalid = select([(p, '2026-09-27')], {'oldgenerator.com'}, matcher)
            self.assertEqual([x['domain'] for x in rows], ['newgenerator.net'])
            self.assertEqual(rows[0]['sourceLine'], 2)
            self.assertEqual(excluded, ['oldgenerator.com'])
            self.assertEqual(counts['duplicate_rows'], 1)
            self.assertEqual(len(invalid), 1)

    def test_actual_page_uses_do_not_need_domain_roots(self):
        self.assertIn('Virtual mix CD', literal_phrases('Virtual mix CD | Brand', {'maker'}))
        self.assertNotIn('Home', literal_phrases('Home', {'maker'}))
        self.assertIn('school ERP', literal_phrases('school ERP', {'online'}))

    def test_metadata_and_prior_keywords_stay_distinct(self):
        rows = [{'domain': 'somemaker.test', 'decision': 'recheck', 'reason': 'javascript_or_thin',
                 'page': {'title': 'Virtual mix CD', 'h1': [], 'description': 'school ERP'}}]
        terms, pages, _ = extract(rows, {'maker'}, {'virtual mix cd'})
        by_term = {x['keyword']: x for x in terms}
        self.assertFalse(by_term['Virtual mix CD']['is_new_to_prior_keywords'])
        self.assertTrue(by_term['school ERP']['is_new_to_prior_keywords'])
        self.assertTrue(all(x['review_status'] == 'metadata_only' for x in terms))
        self.assertEqual(pages[0]['decision'], 'recheck')

    def test_placeholder_correction_prevents_keyword_promotion(self):
        rows = [{'domain': 'somemaker.test', 'decision': 'pass', 'reason': 'html_with_content',
                 'page': {'title': 'Namecheap Parking Page', 'h1': [], 'description': 'Great virtual maker'}}]
        terms, pages, corrections = extract(rows, {'maker'}, set())
        self.assertEqual(terms, [])
        self.assertEqual(pages[0]['decision'], 'skip')
        self.assertEqual(len(corrections), 1)


if __name__ == '__main__':
    unittest.main()
