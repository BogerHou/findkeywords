#!/usr/bin/env python3
"""Auditable Trends website JSON reader and the user-approved 30-day growth rule.

This is NOT the restricted-access official Trends API. Website endpoints can
change or block automation. No proxy rotation, CAPTCHA handling or auto-retry.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
import gzip
import hashlib
from http.cookiejar import CookieJar
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import build_opener, HTTPCookieProcessor, ProxyHandler, Request, HTTPRedirectHandler


RULE = {'geo': 'US', 'property': '', 'category': 0, 'query_type': 'search_term',
        'last7_to_previous7_minimum': 2, 'last7_nonzero_days_minimum': 5,
        'last7_largest_day_share_maximum': 0.40,
        'background_months': 6,
        'background_policy': 'Any detected signal in a complete interval before the 30-day window requires review; never automatically call it a new term.',
        'zero_baseline_policy': 'Keep as emerging signal if sustained and no spike; ratio stays null, never infinite.',
        'request_interval_seconds': 20, 'automatic_retries': 0,
        'note': '0–100 relative search interest, not searches or website visits. Zero is below the display threshold, not proof of zero searches.'}


def windows(today=None):
    end = (today or datetime.now(timezone.utc).date()) - timedelta(days=1)
    start = end - timedelta(days=29)
    month = end.month - 6
    year = end.year
    if month <= 0:
        year, month = year - 1, month + 12
    import calendar
    background = date(year, month, min(end.day, calendar.monthrange(year, month)[1]))
    return {'start': str(start), 'end': str(end), 'background_start': str(background), 'timezone': 'UTC', 'days': 30}


def explore_url(term, start, end):
    # urlencode once. A literal "%20" in q would be a different query.
    return 'https://trends.google.com/trends/explore?' + urlencode({'date': start + ' ' + end, 'geo': 'US', 'q': term, 'hl': 'en-US'})


def evaluate_30(points, window):
    dates = [(date.fromisoformat(window['start']) + timedelta(days=i)).isoformat() for i in range(30)]
    if [p['date'] for p in points] != dates or any(p.get('partial') for p in points):
        return {'status': 'incomplete_or_non_daily', 'eligible': False}
    values = [p['value'] for p in points]
    if not all(type(v) is int and 0 <= v <= 100 for v in values):
        raise ValueError('Invalid Trends values')
    if not any(values):
        return {'status': 'below_reporting_threshold', 'eligible': False}
    previous, current = sum(values[-14:-7]) / 7, sum(values[-7:]) / 7
    days = sum(v > 0 for v in values[-7:])
    spike = max(values[-7:]) / sum(values[-7:]) if sum(values[-7:]) else None
    ratio = current / previous if previous else None
    eligible = days >= 5 and spike is not None and spike <= RULE['last7_largest_day_share_maximum'] and (previous == 0 or ratio >= 2)
    return {'status': ('zero_baseline_emerging' if previous == 0 else 'rapid_growth') if eligible else 'growth_rule_not_met',
            'eligible': eligible, 'previous7_mean': previous, 'last7_mean': current, 'ratio': ratio,
            'last7_nonzero_days': days, 'last7_largest_day_share': spike,
            'first_nonzero_date_in_window': next(p['date'] for p in points if p['value'] > 0)}


def evaluate_background(points, window):
    if not points:
        return {'status': 'background_insufficient', 'eligible': False}
    # Never treat a weekly bin overlapping the 30-day boundary as earlier proof.
    intervals = []
    for i, p in enumerate(points[:-1]):
        if points[i + 1]['date'] <= window['start'] and not p.get('partial'):
            intervals.append(p)
    first = date.fromisoformat(points[0]['date'])
    last = date.fromisoformat(points[-1]['date'])
    gaps = [(date.fromisoformat(b['date']) - date.fromisoformat(a['date'])).days for a, b in zip(points, points[1:])]
    if first > date.fromisoformat(window['background_start']) + timedelta(days=7) or last < date.fromisoformat(window['end']) - timedelta(days=7) or last > date.fromisoformat(window['end']) or any(g < 1 or g > 7 for g in gaps) or not intervals:
        return {'status': 'background_incomplete', 'eligible': False}
    signals = [p for p in intervals if p['value'] > 0]
    if signals:
        return {'status': 'earlier_signal_requires_review', 'eligible': False, 'earlier_nonzero_intervals': len(signals),
                'first_earlier_signal': signals[0]['date']}
    if not any(p['value'] > 0 for p in points):
        return {'status': 'background_below_threshold', 'eligible': False}
    return {'status': 'no_earlier_reported_signal', 'eligible': True,
            'note': 'Earlier zero indices do not prove the word or demand did not exist.'}


class TrendsUnavailable(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise TrendsUnavailable('Unexpected redirect to ' + urlsplit(newurl).netloc)


class Client:
    def __init__(self, output):
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()), NoRedirect())
        self.last_request = float('-inf')

    def get(self, url, kind, *, want_json=True):
        if urlsplit(url).hostname != 'trends.google.com':
            raise ValueError('Only the Trends website may be queried')
        pause = self.last_request + RULE['request_interval_seconds'] - time.monotonic()
        if pause > 0:
            time.sleep(pause)
        self.last_request = time.monotonic()
        request = Request(url, headers={'User-Agent': 'FindKeywordsResearch/1.0', 'Accept-Language': 'en-US,en;q=0.8', 'Accept': 'application/json,text/html;q=0.8'})
        meta = {'url': url, 'kind': kind, 'captured_at': datetime.now(timezone.utc).isoformat()}
        body = b''
        try:
            try:
                response = self.opener.open(request, timeout=30)
            except HTTPError as exc:
                response = exc
            with response:
                meta.update(http_status=response.status, content_type=response.headers.get('Content-Type'),
                            retry_after=response.headers.get('Retry-After'))
                body = response.read(2 * 1024 * 1024 + 1)
            digest = hashlib.sha256(body).hexdigest()
            (self.output / (digest + '.gz')).write_bytes(gzip.compress(body, mtime=0))
            meta.update(body_sha256=digest, body_bytes=len(body))
            if meta['http_status'] != 200:
                raise TrendsUnavailable('Google Trends HTTP ' + str(meta['http_status']))
            if len(body) > 2 * 1024 * 1024:
                raise TrendsUnavailable('Trends response exceeds cap')
            text = body.decode('utf-8')
            if not want_json:
                if 'unusual traffic' in text.lower() or 'recaptcha' in text.lower():
                    raise TrendsUnavailable('Google verification page')
                return None
            text = text.lstrip()
            if text.startswith(")]}'"):
                text = text[4:].lstrip(',\r\n ')
            try:
                return json.loads(text)
            except (ValueError, TypeError) as exc:
                raise TrendsUnavailable('Non-JSON response; no chart data inferred') from exc
        except Exception as exc:
            meta['error'] = type(exc).__name__ + ': ' + str(exc)[:300]
            raise
        finally:
            with (self.output / 'requests.jsonl').open('a') as log:
                log.write(json.dumps(meta, ensure_ascii=False) + '\n')

    def initialize(self):
        self.get('https://trends.google.com/trends/explore?geo=US', 'session', want_json=False)

    def chart(self, term, start, end):
        req = {'comparisonItem': [{'keyword': term, 'time': start + ' ' + end, 'geo': 'US'}], 'category': 0, 'property': ''}
        url = 'https://trends.google.com/trends/api/explore?' + urlencode({'hl': 'en-US', 'tz': 0, 'req': json.dumps(req, separators=(',', ':'))})
        doc = self.get(url, 'explore')
        widgets = doc.get('widgets')
        if not isinstance(widgets, list):
            raise TrendsUnavailable('Missing widgets; no-data cannot be inferred')
        widget = next((w for w in widgets if w.get('id') == 'TIMESERIES'), None)
        if not widget:
            return {'status': 'no_timeseries_widget', 'points': [], 'url': explore_url(term, start, end)}
        payload = widget.get('request')
        if not isinstance(payload, dict) or not widget.get('token'):
            raise TrendsUnavailable('Invalid time-series widget')
        # Demand a single exact search term and requested geography, rather than
        # accidentally recording a topic or an unrelated comparison chart.
        items = payload.get('comparisonItem', [])
        keywords = [k for item in items for k in item.get('complexKeywordsRestriction', {}).get('keyword', [])]
        if len(keywords) != 1 or keywords[0].get('value', '').casefold() != term.casefold() or keywords[0].get('type') != 'BROAD':
            raise TrendsUnavailable('Returned widget keyword/type does not match requested search term')
        if len(items) != 1 or items[0].get('geo', {}).get('country') != 'US':
            raise TrendsUnavailable('Returned widget geography mismatch')
        url = 'https://trends.google.com/trends/api/widgetdata/multiline?' + urlencode({'hl': 'en-US', 'tz': 0, 'req': json.dumps(payload, separators=(',', ':')), 'token': widget['token']})
        result = self.get(url, 'timeline')
        series = result.get('default', {}).get('timelineData')
        if not isinstance(series, list):
            raise TrendsUnavailable('Missing timelineData')
        points = []
        for p in series:
            values = p.get('value')
            if not isinstance(values, list) or len(values) != 1 or type(values[0]) is not int or not 0 <= values[0] <= 100:
                raise TrendsUnavailable('Unexpected value schema')
            partial = p.get('isPartial', False)
            partial = any(partial) if isinstance(partial, list) else bool(partial)
            points.append({'date': datetime.fromtimestamp(int(p['time']), timezone.utc).date().isoformat(), 'value': values[0], 'partial': partial})
        if len({p['date'] for p in points}) != len(points) or points != sorted(points, key=lambda p: p['date']):
            raise TrendsUnavailable('Repeated or out-of-order dates')
        return {'status': 'chart' if points else 'empty_timeline', 'points': points, 'url': explore_url(term, start, end),
                'captured_at': datetime.now(timezone.utc).isoformat(), 'widget_request': payload}
