import unittest
from curate_full import page_correction, MARKETING, canonical


class CurationTests(unittest.TestCase):
    def row(self, title, h1=None):
        return {'domain':'example.com','decision':'pass','reason':'html_with_content',
                'page':{'title':title,'h1':h1 or []}}

    def test_exact_placeholder_and_challenge_corrections(self):
        self.assertEqual(page_correction(self.row('Security check'))['decision'], 'recheck')
        self.assertEqual(page_correction(self.row('Client Challenge'))['reason'], 'review_challenge')
        self.assertEqual(page_correction(self.row('Namecheap Parking Page'))['decision'], 'skip')
        self.assertEqual(page_correction(self.row('Example.com for sale | Spaceship.com'))['reason'], 'review_parking')
        self.assertEqual(page_correction(self.row('example.com — Coming Soon'))['reason'], 'review_placeholder')

    def test_generic_titles_and_articles_not_rejected(self):
        for title in ['Home', 'WordPress', 'Example.com', 'How to list a domain for sale', 'Security check tools compared']:
            self.assertIsNone(page_correction(self.row(title)))

    def test_marketing_phrase_is_distinct_from_use_case(self):
        self.assertTrue(MARKETING.search('seo checker grow organic traffic'))
        self.assertFalse(MARKETING.search('trading card scanner'))
        self.assertEqual(canonical(' AI  Prompt\nEnhancer '), 'ai prompt enhancer')


if __name__ == '__main__':
    unittest.main()
