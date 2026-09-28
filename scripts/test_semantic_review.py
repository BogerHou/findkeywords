import copy
import unittest

from semantic_review import fields, fields_hash, validate_ledger


class SemanticReviewTests(unittest.TestCase):
    def setUp(self):
        self.row = {'domain': 'example.net', 'page': {'title': 'Trading Card Scanner', 'description': 'Scan card photos.', 'h1': []}}
        self.evidence = {'domain': 'example.net', 'field': 'title', 'quote': 'Trading Card Scanner'}
        self.candidates = [{'keyword': 'trading card scanner', 'evidence': [self.evidence]}]
        self.term = {'keyword': 'trading card scanner', 'status': 'meaning_checked',
                     'meaning': 'Scan trading cards', 'reason': 'Literal title only',
                     'evidence': self.evidence, 'source_fields_sha256': fields_hash(self.row),
                     'reviewed_at': '2026-09-28T13:00:00+00:00', 'batch_id': 'test'}
        self.ledger = {'version': 1, 'domains': [], 'terms': [self.term]}

    def validate(self, ledger=None, row=None):
        return validate_ledger(ledger or self.ledger, {'example.net': row or self.row}, self.candidates, [])

    def test_saved_review_cannot_survive_changed_source(self):
        self.assertEqual(len(self.validate()[1]), 1)
        changed = copy.deepcopy(self.row)
        changed['page']['description'] = 'This domain is for sale'
        with self.assertRaisesRegex(ValueError, 'source changed'):
            self.validate(row=changed)

    def test_invented_or_unrelated_field_is_not_accepted(self):
        forged = copy.deepcopy(self.ledger)
        forged['terms'][0]['evidence']['quote'] = 'AI Trading Card Scanner'
        with self.assertRaisesRegex(ValueError, 'quoted field'):
            self.validate(forged)
        duplicate = copy.deepcopy(self.ledger)
        duplicate['terms'].append({**self.term, 'keyword': 'Trading  Card Scanner'})
        with self.assertRaisesRegex(ValueError, 'duplicate term'):
            self.validate(duplicate)

    def test_resolved_domain_requires_actual_supplement(self):
        domain = {'domain': 'example.net', 'status': 'supplemented', 'reason': 'Literal title',
                  'selected_keywords': ['Trading Card Scanner'], 'source_fields': fields(self.row),
                  'source_fields_sha256': fields_hash(self.row), 'reviewed_at': 'now', 'batch_id': 'test'}
        ledger = {'version': 1, 'domains': [domain], 'terms': []}
        with self.assertRaisesRegex(ValueError, 'missing supplement'):
            self.validate(ledger)
        result = validate_ledger(ledger, {'example.net': self.row}, self.candidates,
                                 [{'domain': 'example.net', 'keyword': 'Trading Card Scanner'}])
        self.assertEqual(len(result[0]), 1)


if __name__ == '__main__':
    unittest.main()
