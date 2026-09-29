#!/usr/bin/env python3
"""Offline queue and evidence importer for user-authorized local browser queries.

This script does not make Google requests. Use the real browser UI to query and
download CSV, then import it here. Network failures never become zero values.
"""
from __future__ import annotations
import argparse
from collections import Counter
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from probe_full import atomic_json
from trends_full import RULE, evaluate_30, evaluate_background, windows
from local_trends_pacing import Pacer, POLICY, availability, utcnow

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'results/local-trends-20260928'


def read(path):
    return json.loads(path.read_text())


def canonical(term):
    return ' '.join(term.split()).casefold()


def validate_url(url, term, window, stage):
    parsed = urlsplit(url)
    q = parse_qs(parsed.query, keep_blank_values=True)
    start = window['background_start'] if stage == 'background' else window['start']
    if (parsed.scheme != 'https' or parsed.hostname != 'trends.google.com'
            or q.get('q') != [term] or q.get('geo') != ['US']
            or q.get('date') != [start + ' ' + window['end']]
            or q.get('gprop', ['']) != [''] or q.get('cat', ['0']) != ['0']):
        raise ValueError('Observed query URL does not match term/window/US/web/all categories')


def csv_points(raw, term, window, stage):
    rows = list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
    headers = [(i, r) for i, r in enumerate(rows) if len(r) == 2 and r[0] in ('Day', 'Week', '日', '周')]
    if len(headers) != 1:
        raise ValueError('Expected one time-series CSV header')
    index, header = headers[0]
    if header[1] not in (term + ': (United States)', term + ': (美国)'):
        raise ValueError('CSV term/geography mismatch; possible stale chart')
    points = []
    for row in rows[index + 1:]:
        if not row:
            continue
        if len(row) != 2 or not row[1].isdigit() or not 0 <= int(row[1]) <= 100:
            raise ValueError('Unexpected CSV value; do not coerce missing or <1 into zero')
        day = date.fromisoformat(row[0]).isoformat()
        points.append({'date': day, 'value': int(row[1]), 'partial': False})
    dates = [p['date'] for p in points]
    if dates != sorted(set(dates)):
        raise ValueError('Repeated/out-of-order CSV dates')
    if stage != 'background':
        start = date.fromisoformat(window['start'])
        if dates != [str(start + timedelta(days=i)) for i in range(30)]:
            raise ValueError('Expected exactly 30 complete daily dates')
    elif not dates or dates[-1] > window['end']:
        raise ValueError('Invalid background dates')
    return points


def next_stage(record, window):
    charts = record.get('charts', {})
    if 'chart30' not in charts:
        return 'chart30'
    first = charts['chart30']
    if first['status'] != 'chart' or not evaluate_30(first['points'], window)['eligible']:
        return None
    if 'background' not in charts:
        return 'background'
    bg = charts['background']
    if bg['status'] != 'chart' or not evaluate_background(bg['points'], window)['eligible']:
        return None
    return None if 'repeat30' in charts else 'repeat30'


def prepare():
    if (RUN / 'queue.json').exists():
        return read(RUN / 'queue.json')
    source = ROOT / 'site/full-keyword-reviewed.json'
    candidates = read(source)
    selected = [r for r in candidates if r['review_status'] != 'no_usable_source']
    def priority(r):
        if canonical(r['keyword']) == 'trading card scanner':
            return -1
        if r.get('semantic_review', {}).get('status') == 'meaning_checked' or r['review_status'] == 'supplement_needs_trends':
            return 0
        return 1 if r['review_status'] == 'ready_for_semantic_review' else 2
    selected.sort(key=priority)
    if len({canonical(r['keyword']) for r in selected}) != len(selected):
        raise ValueError('Duplicate query phrases')
    queue = {'created_at': datetime.now(timezone.utc).isoformat(), 'window': windows(),
             'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
             'scope': 'All retained literal candidates; semantic/quality flags remain in results.',
             'excluded': [r for r in candidates if r['review_status'] == 'no_usable_source'],
             'candidates': selected}
    atomic_json(RUN / 'queue.json', queue)
    return queue


def publish(queue):
    ledger_path = RUN / 'records.json'
    records = read(ledger_path) if ledger_path.exists() else {}
    public, pending = [], []
    for item in queue['candidates']:
        term = item['keyword']
        record = records.get(term, {})
        stage = next_stage(record, queue['window'])
        if stage:
            pending.append({'keyword': term, 'stage': stage})
        if not record:
            continue
        row = {**item, **record, 'window': queue['window'], 'next_stage': stage,
               'final_review': 'pending', 'matches_automatic_screen': False}
        for name, chart in record['charts'].items():
            fn = evaluate_background if name == 'background' else evaluate_30
            assessment = fn(chart['points'], queue['window']) if chart['status'] == 'chart' else {'eligible': False, 'status': chart['status']}
            row[name + '_assessment'] = assessment
        row['assessment'] = row['chart30_assessment']
        row['matches_automatic_screen'] = all(row.get(k, {}).get('eligible') for k in ('chart30_assessment', 'background_assessment', 'repeat30_assessment'))
        public.append(row)
    executions = Counter(c.get('execution', 'local_browser') for r in public for c in r['charts'].values())
    execution = 'mixed_browser' if len(executions) > 1 else next(iter(executions), 'local_browser')
    summary = {'status': 'awaiting_local_browser_batch' if pending else 'needs_final_review',
               'execution': execution, 'evidence_executions': dict(executions),
               'updated_at': datetime.now(timezone.utc).isoformat(),
               'candidates': len(queue['candidates']), 'excluded': len(queue['excluded']),
               'queried': len(public), 'completed': len(queue['candidates']) - len(pending),
               'pending': len(pending), 'window': queue['window'],
               'rule': {**{k: v for k, v in RULE.items() if k not in ('automatic_retries', 'request_interval_seconds')},
                        'browser_query_interval_seconds': POLICY['query_interval_seconds'],
                        'immediate_retries': 0, 'scheduled_cooldown_recovery': True,
                        'local_pacing_policy': POLICY},
               'chart_series': sum(c['status'] == 'chart' for r in public for c in r['charts'].values()),
               'automatic_matches': sum(r['matches_automatic_screen'] for r in public),
               'assessments': dict(Counter(r['assessment']['status'] for r in public)),
               'timezone_note': 'UTC selects the fixed calendar dates; CSV exports contain daily labels without timezone metadata. The failed browser request exposed tz=-480. Do not describe these exports as verified UTC buckets.',
               'note': 'Browser CSV/DOM evidence; each capture retains its execution source. Meaning/quality flags retained. Not final opportunities or search volumes.'}
    control = read(RUN / 'control.json') if (RUN / 'control.json').exists() else {}
    if control.get('status') == 'blocked':
        summary.update(status='blocked', error=control['reason'], blocked_at=control['at'])
    elif control.get('pacing_enabled') and pending:
        pacing = availability(control, utcnow())
        summary.update(status=pacing['state'], pacing=pacing,
                       next_allowed_at=control['next_allowed_at'],
                       last_rate_limit_reason=control.get('last_rate_limit_reason', control.get('reason')))
    atomic_json(RUN / 'summary.json', summary)
    atomic_json(RUN / 'pending.json', pending)
    atomic_json(ROOT / 'site/local-trends-status.json', summary)
    atomic_json(ROOT / 'site/local-trends-results.json', public)
    return summary, pending


def ingest(args, queue):
    if args.keyword not in {r['keyword'] for r in queue['candidates']}:
        raise ValueError('Unknown exact keyword')
    validate_url(args.url, args.keyword, queue['window'], args.stage)
    path = RUN / 'records.json'
    records = read(path) if path.exists() else {}
    record = records.setdefault(args.keyword, {'keyword': args.keyword, 'charts': {}})
    if next_stage(record, queue['window']) != args.stage:
        raise ValueError('Wrong/duplicate stage; preserve existing evidence')
    pacer = Pacer(RUN)
    pacer.require_claim(args.keyword, args.stage)
    if args.csv:
        raw = args.csv.read_bytes()
        points = csv_points(raw, args.keyword, queue['window'], args.stage)
        extension, status = '.csv', 'chart'
    else:
        raw = args.dom.read_bytes()
        capture = json.loads(raw)
        if capture['url'] != args.url or capture['keyword'] != args.keyword:
            raise ValueError('DOM capture query mismatch')
        text = capture.get('text', '')
        if any(x in text.lower() for x in ('too many requests', 'unusual traffic', 'something went wrong', 'try again later', 'captcha')):
            raise ValueError('Browser error is not no-data')
        if capture['status'] == 'no_data':
            if not any(x in text.lower() for x in ("not enough data", "doesn't have enough data", '没有足够的数据', '数据不足')):
                raise ValueError('No explicit insufficient-data message')
            points, status = [], 'below_reporting_threshold_no_chart'
        else:
            points, status = capture['points'], 'chart'
            if args.stage != 'background' and evaluate_30(points, queue['window'])['status'] == 'incomplete_or_non_daily':
                raise ValueError('Incomplete DOM daily chart')
        extension = '.json'
    digest = hashlib.sha256(raw).hexdigest()
    evidence = ROOT / 'site/local-trends-evidence' / (digest + extension)
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_bytes(raw)
    execution = getattr(args, 'execution', 'local_browser')
    browser_source = 'Browserless cloud browser' if execution == 'browserless_cloud' else 'local browser'
    record['charts'][args.stage] = {'status': status, 'points': points, 'url': args.url,
        'captured_at': args.captured_at,
        'imported_at': datetime.now(timezone.utc).isoformat(),
        'execution': execution,
        'source': 'Google Trends ' + browser_source + (' CSV download' if args.csv else ' observed DOM'),
        'evidence': evidence.relative_to(ROOT / 'site').as_posix(), 'evidence_sha256': digest}
    atomic_json(path, records)
    pacer.success(args.keyword, args.stage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'next', 'ingest', 'status', 'block', 'resume', 'claim', 'cooldown'])
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--keyword')
    parser.add_argument('--stage', choices=['chart30', 'background', 'repeat30'], default='chart30')
    parser.add_argument('--url')
    parser.add_argument('--csv', type=Path)
    parser.add_argument('--dom', type=Path)
    parser.add_argument('--captured-at')
    parser.add_argument('--execution', choices=['local_browser', 'browserless_cloud'], default='local_browser')
    parser.add_argument('--reason')
    parser.add_argument('--not-before')
    parser.add_argument('--retry-after')
    args = parser.parse_args()
    queue = prepare()
    action_result = None
    if args.command == 'block':
        if not args.reason:
            parser.error('block needs the observed failure reason')
        Pacer(RUN).block(args.reason)
    if args.command == 'resume':
        if not args.reason or not args.not_before:
            parser.error('resume needs explicit user authorization reason and a not-before timestamp')
        action_result = Pacer(RUN).resume(args.not_before, args.reason)
    if args.command == 'cooldown':
        if not args.reason:
            parser.error('cooldown needs the actual observed failure reason')
        action_result = Pacer(RUN).cooldown(args.reason, args.retry_after)
    if args.command == 'claim':
        _, pending = publish(queue)
        action_result = Pacer(RUN).claim(pending[0] if pending else None)
    if args.command == 'ingest':
        if not args.keyword or not args.url or bool(args.csv) == bool(args.dom):
            parser.error('ingest needs keyword, observed URL and exactly one CSV/DOM evidence file')
        ingest(args, queue)
    summary, pending = publish(queue)
    print(json.dumps(action_result if action_result is not None else pending[:args.limit] if args.command == 'next' else summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
