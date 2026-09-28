import unittest

from audit_access import confirmed_robots, summarize


class AccessAuditTests(unittest.TestCase):
    def row(self, domain='one.test', reason='http_blocked', code=403, title=''):
        return {'domain': domain, 'decision': 'recheck', 'reason': reason,
                'page': {'title': title, 'h1': []},
                'requests': [{'stage': 'robots', 'http_status': code, 'body_sha256': domain}]}

    def test_blocked_domain_is_counted_once_despite_multiple_requests(self):
        row = self.row()
        row['requests'].append(dict(row['requests'][0]))
        result = summarize([row, self.row('two.test', 'dns_error', None)], set())
        self.assertEqual(result['access_restriction_domains'], 1)
        self.assertEqual(result['http_status_domain_counts']['403'], 1)
        self.assertEqual(sum(x['count'] for x in result['groups']), 2)

    def test_embedded_challenge_code_alone_is_not_a_block(self):
        rows = [self.row('a.test', 'robots_returned_html', 200), self.row('b.test', 'robots_returned_html', 200)]
        review = {'items': [
            {'domain': 'a.test', 'body_sha256': 'a.test', 'title': 'Login', 'verification_markers': ['cloudflare_challenge_markup']},
            {'domain': 'b.test', 'body_sha256': 'b.test', 'title': 'Just a moment...', 'verification_markers': ['explicit_challenge_title']},
        ]}
        confirmed = confirmed_robots(review, rows)
        self.assertEqual(confirmed, {'b.test'})
        self.assertEqual(summarize(rows, confirmed)['access_restriction_domains'], 1)

    def test_a_new_unaccounted_reason_fails_instead_of_disappearing(self):
        with self.assertRaisesRegex(ValueError, 'Unmapped'):
            summarize([self.row(reason='not_mapped_yet')], set())


if __name__ == '__main__':
    unittest.main()
