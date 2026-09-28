#!/usr/bin/env python3
"""Offline access-outcome accounting. Never attributes a failure to IP reputation."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re

from curate_full import page_correction
from probe_domains import PageParser, decode_html
from probe_full import atomic_json, load_records

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/aws-full-20260928-access-audit'
EXPLICIT_TITLE = re.compile(r'\s*(?:just a moment[.!…]*|security check|client challenge|access denied[.!]*|verify you are human|confirm you are human|403 forbidden)\s*', re.I)
GROUPS = {
    'access_restriction': ('拒绝、认证、验证或限流迹象', {'http_blocked', 'historical_http_blocked', 'rate_limited', 'challenge', 'review_challenge', 'audit_robots_verification'}),
    'dns': ('DNS 解析失败', {'dns_error'}),
    'tls': ('TLS 握手或证书验证失败', {'tls_handshake_error', 'tls_certificate_error'}),
    'network': ('超时、连接或其他传输失败', {'timeout', 'connect_error', 'transport_error'}),
    'robots_rules': ('robots 规则或采集器解析/大小/间隔限制', {'robots_disallowed', 'robots_complex_rules', 'robots_too_large', 'robots_slower_schedule_required'}),
    'robots_html': ('robots 返回 HTML，未明确识别为验证页', {'robots_returned_html'}),
    'redirects': ('跳转触发采集边界', {'external_or_unsupported_redirect', 'https_downgrade', 'redirect_limit_or_missing_location', 'redirect_loop'}),
    'target_validation': ('解析目标不符合公网地址限制', {'target_error'}),
    'other_http': ('其他 HTTP 错误', {'robots_http_error', 'homepage_http_error'}),
    'limited_content': ('薄页、依赖脚本、截断或缺少标签', {'javascript_or_thin', 'thin_or_empty', 'homepage_too_large', 'missing_keyword_evidence'}),
    'unusable_page': ('不存在、停放、占位或格式不适合提词', {'homepage_missing', 'soft_404', 'parking_page', 'placeholder_page', 'template_placeholder', 'reviewed_placeholder_or_parking', 'review_parking', 'review_placeholder', 'non_html', 'missing_content_type'}),
    'page_candidate': ('取得页面内容，仍待语义与趋势验证', {'html_with_content'}),
}


def scan_robots_bodies(rows, source_hash):
    items = []
    for row in rows:
        if row['reason'] != 'robots_returned_html':
            continue
        req = row['requests'][-1]
        raw = gzip.decompress((ROOT / 'results/aws-full-20260928' / req['body_file']).read_bytes())
        if hashlib.sha256(raw).hexdigest() != req['body_sha256']:
            raise ValueError('Saved body hash mismatch: ' + row['domain'])
        html = decode_html(raw, req.get('content_type'))
        parser = PageParser()
        parser.feed(html)
        fields = parser.extracted()
        title = fields.get('title', '')
        markers = []
        if EXPLICIT_TITLE.fullmatch(title):
            markers.append('explicit_challenge_title')
        if 'cf-chl-' in html or '/cdn-cgi/challenge-platform/' in html:
            markers.append('cloudflare_challenge_markup')
        if re.search(r'please (?:enable javascript and cookies|verify (?:that )?you are (?:a )?human)|checking (?:your )?browser|verifying you are human', fields.get('visible_text', ''), re.I):
            markers.append('verification_text')
        items.append({'domain': row['domain'], 'http_status': req.get('http_status'), 'title': title,
                      'h1': fields.get('h1', []), 'verification_markers': markers, 'body_sha256': req['body_sha256']})
    return {'source_results_sha256': source_hash, 'total': len(items), 'items': items,
            'note': 'Saved robots HTML only. Embedded challenge code alone is not proof that access was blocked.'}


def confirmed_robots(review, rows):
    expected = {r['domain']: r for r in rows if r['reason'] == 'robots_returned_html'}
    items = review['items']
    if len(items) != len(expected) or {r['domain'] for r in items} != set(expected):
        raise ValueError('Robots review coverage mismatch')
    confirmed = set()
    for item in items:
        source = expected[item['domain']]['requests'][-1]
        if item['body_sha256'] != source['body_sha256']:
            raise ValueError('Robots review source mismatch')
        # Turnstile/challenge-platform scripts can be embedded in a normal page.
        if EXPLICIT_TITLE.fullmatch(item['title']):
            confirmed.add(item['domain'])
    return confirmed


def summarize(rows, confirmed):
    groups, reasons, status_domains = Counter(), Counter(), {}
    cases = []
    for row in rows:
        effective = page_correction(row) or row
        reason = 'audit_robots_verification' if row['domain'] in confirmed else effective['reason']
        matching = [key for key, (_, values) in GROUPS.items() if reason in values]
        if len(matching) != 1:
            raise ValueError('Unmapped/overlapping reason: ' + reason)
        key = matching[0]
        groups[key] += 1
        reasons[reason] += 1
        for req in row.get('requests', []):
            if req.get('http_status') is not None:
                status_domains.setdefault(str(req['http_status']), set()).add(row['domain'])
        if key == 'access_restriction':
            cases.append({'domain': row['domain'], 'original_reason': row['reason'], 'audit_reason': reason,
                          'evidence': [{'stage': q.get('stage'), 'url': q.get('url'), 'http_status': q.get('http_status'),
                                        'body_sha256': q.get('body_sha256')} for q in row.get('requests', [])],
                          'heading_correction': effective if effective is not row else None})
    n = len(rows)
    return {'domains': n, 'groups': [{'id': key, 'label': label, 'count': groups[key], 'percent': round(100 * groups[key] / n, 2)} for key, (label, _) in GROUPS.items()],
            'effective_reasons': dict(reasons), 'http_status_domain_counts': {key: len(value) for key, value in status_domains.items()},
            'access_restriction_domains': len(cases), 'access_restriction_percent': round(100 * len(cases) / n, 2),
            'homepage_request_recorded': sum(any(q.get('stage') == 'homepage' for q in r.get('requests', [])) for r in rows),
            'no_homepage_request_recorded': sum(not any(q.get('stage') == 'homepage' for q in r.get('requests', [])) for r in rows),
            'access_cases': cases}


def run(scan=False):
    new_path = ROOT / 'results/aws-full-20260928/results.jsonl'
    reused_path = ROOT / 'results/aws-full-20260928-input/reused.jsonl'
    rows, reused = load_records(new_path), load_records(reused_path)
    digest = hashlib.sha256(new_path.read_bytes()).hexdigest()
    review_path = OUT / 'robots-html-review.json'
    if scan:
        atomic_json(review_path, scan_robots_bodies(rows, digest))
    review = json.loads(review_path.read_text())
    if review.get('source_results_sha256') != digest:
        raise ValueError('Robots body review is missing source fingerprint; run saved-body scan on AWS')
    confirmed = confirmed_robots(review, rows)
    doc = {'updated_at': datetime.now(timezone.utc).isoformat(), 'source_results_sha256': digest,
           'source_reused_sha256': hashlib.sha256(reused_path.read_bytes()).hexdigest(),
           'network_requests': 0, 'aws_new': summarize(rows, confirmed), 'historical_reused': summarize(reused, set()),
           'all_records': summarize(reused + rows, confirmed), 'robots_html_additional_verification': len(confirmed),
           'robots_html_embedded_code_only': sum(bool(i['verification_markers']) and i['domain'] not in confirmed for i in review['items']),
           'method': 'Unique domain counts. Page-heading corrections applied; three saved robots HTML verification titles classified separately. HTTP status and visible challenge do not identify the reason for refusal.',
           'limitations': ['Historical reused rows were not all probed from this AWS IP; homepage request counts for them are not complete.',
                           'HTTP error bodies and full response headers were not retained by the original domain fetcher; 403 cannot be assigned to a particular WAF or IP policy.',
                           'DNS/TLS/timeout failures may have several causes; no controlled network/browser comparison was performed.',
                           'TLS-only, short timeouts, no JS rendering, limited robots parser, size caps and apex/www redirect scope reduce coverage.']}
    atomic_json(OUT / 'summary.json', doc)
    public = {key: value for key, value in doc.items() if key not in {'aws_new', 'historical_reused', 'all_records'}}
    for scope in ('aws_new', 'historical_reused', 'all_records'):
        public[scope] = {key: value for key, value in doc[scope].items() if key != 'access_cases'}
    atomic_json(ROOT / 'site/full-access-audit.json', public)
    atomic_json(ROOT / 'site/full-access-cases.json', [
        {**case, 'scope': scope} for scope in ('aws_new', 'historical_reused') for case in doc[scope]['access_cases']])
    print(json.dumps({k: v for k, v in doc['aws_new'].items() if k not in {'access_cases', 'http_status_domain_counts'}}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scan-robots-bodies', action='store_true', help='Read saved AWS gzip files only; no HTTP requests')
    run(p.parse_args().scan_robots_bodies)
