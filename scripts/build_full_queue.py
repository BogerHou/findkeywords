#!/usr/bin/env python3
"""Prepare every root-matched domain, reusing auditable prior records. Offline only."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import probe_prescreen as pre

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(output):
    source = ROOT / 'site/roots-data.json'
    data = json.loads(source.read_text())
    domains = {r['domain']: r for r in data['domains']}
    if len(domains) != len(data['domains']):
        raise ValueError('Duplicate source domains')
    index = json.loads((ROOT / 'site/probe-cache-index.json').read_text())
    old, origins = {}, []
    for s in index['sources']:
        p = ROOT / s['path']
        if sha(p) != s['sha256']:
            raise ValueError('Historical source checksum changed: ' + str(p))
        rows = json.loads(p.read_text()) if p.suffix == '.json' else [json.loads(x) for x in p.read_text().splitlines()]
        origins.append(s)
        for r in rows:
            if r['domain'] not in domains:
                continue
            if r.get('fetched_at', '') >= old.get(r['domain'], {}).get('fetched_at', ''):
                old[r['domain']] = {**r, '_origin': s}
    reused, retry = {}, {}
    for domain, r in old.items():
        # Retry old transport/5xx failures once on AWS. Retain actual block,
        # missing-page and non-HTML evidence; a different host is not a bypass.
        status = r.get('http_status')
        if r.get('fetch_status') != 'ok' and status not in (401, 403, 404, 410, 429) and r.get('fetch_status') != 'unsupported_content_type':
            retry[domain] = {'checked_at': r.get('fetched_at'), 'reason': r.get('fetch_error') or r.get('fetch_status'), 'origin': r['_origin']}
            continue
        fields = {k: r.get(k) or ([] if k == 'h1' else '') for k in ('title', 'description', 'og_description', 'h1', 'visible_text')}
        if r.get('fetch_status') == 'ok':
            decision, reason = pre.classify_page('', fields)
        elif status in (404, 410):
            decision, reason = 'skip', 'homepage_missing'
        elif status in (401, 403, 429):
            decision, reason = 'recheck', 'historical_http_blocked'
        else:
            decision, reason = 'skip', 'non_html'
        reused[domain] = {'domain': domain, 'source': domains[domain], 'checked_at': r.get('fetched_at'),
                          'policy_version': 'historical-fields-reclassified-v1', 'decision': decision, 'reason': reason,
                          'page': fields, 'final_url': r.get('final_url'), 'requests': [], 'stop_batch': False,
                          'reused': True, 'provenance': r['_origin'], 'historical_fetch_status': r.get('fetch_status')}
    pilot = ROOT / 'results/aws-pilot-01/results.jsonl'
    pilot_sha = sha(pilot)
    review = json.loads((ROOT / 'site/prescreen-review.json').read_text())
    if review['resultsSha256'] != pilot_sha:
        raise ValueError('Pilot review checksum mismatch')
    reviewed = {r['domain']: r for r in review['items']}
    pilot_rows = [json.loads(x) for x in pilot.read_text().splitlines()]
    for r in pilot_rows:
        domain = r['domain']
        if domain not in domains:
            raise ValueError('Pilot domain outside source')
        row = {**r, 'reused': True, 'provenance': {'path': 'results/aws-pilot-01/results.jsonl', 'sha256': pilot_sha}}
        if domain in reviewed:
            row.update(original_decision=r['decision'], original_reason=r['reason'], decision='skip',
                       reason='reviewed_placeholder_or_parking', review=reviewed[domain])
        reused[domain] = row
        retry.pop(domain, None)
    pending = []
    for domain, r in domains.items():
        if domain not in reused:
            pending.append({**r, 'queue_reason': 'retry_old_failure_on_aws' if domain in retry else 'never_probed',
                            **({'previous_attempt': retry[domain]} if domain in retry else {})})
    pending.sort(key=lambda r: hashlib.sha256(('full-2026-09-28\0' + r['domain']).encode()).hexdigest())
    output.mkdir(parents=True, exist_ok=False)
    reuse_path = output / 'reused.jsonl'
    reuse_path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in reused.values()))
    summary = {'universe': len(domains), 'reused': len(reused), 'queued': len(pending),
               **dict(Counter(r['queue_reason'] for r in pending)), 'historically_seen': len(set(old) | {r['domain'] for r in pilot_rows})}
    pre.dump(output / 'queue.json', {'version': 'all-root-domains-v1', 'summary': summary,
             'source': {'path': 'site/roots-data.json', 'sha256': sha(source), 'window': data['meta']['sourceWindow']},
             'reuse_sha256': sha(reuse_path), 'selection': 'Every one of 16090 source domains; no priority or TLD exclusion; includes formerly deferred same-name TLDs.',
             'domains': pending})
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    build(p.parse_args().output)
