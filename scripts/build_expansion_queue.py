#!/usr/bin/env python3
"""Offline root screening of newly acquired lists; exclude all prior attempts."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from build_roots_site import RootMatcher, CONFIG
from probe_full import atomic_json
from screen_month import normalize_domain

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select(batches, prior, matcher):
    seen, selected, excluded, invalid = set(), {}, [], []
    counts = Counter()
    for source_path, source_date in batches:
        for line, raw in enumerate(source_path.read_text().splitlines(), 1):
            counts['raw_rows'] += 1
            domain, error = normalize_domain(raw)
            if error:
                counts['invalid_rows'] += 1
                invalid.append({'source_file': source_path.name, 'source_line': line, 'reason': error})
                continue
            if domain in seen:
                counts['duplicate_rows'] += 1
                continue
            seen.add(domain)
            hits = matcher.matches(domain, domain=True)
            if not hits:
                counts['not_matched'] += 1
                continue
            counts['root_matched'] += 1
            if domain in prior:
                counts['previously_attempted'] += 1
                excluded.append(domain)
                continue
            selected[domain] = {'domain': domain, 'roots': matcher.roots_for(hits), 'matches': hits,
                'sourceDate': source_date, 'sourceFile': source_path.name, 'sourceLine': line,
                'queue_reason': 'new_source_root_match_never_previously_attempted'}
    counts.update(unique_valid=len(seen), queued=len(selected))
    ordered = sorted(selected.values(), key=lambda x: hashlib.sha256(('expansion-20260928\0' + x['domain']).encode()).hexdigest())
    return ordered, dict(counts), excluded, invalid


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--history', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise ValueError('Use a new output directory; never silently replace a running queue')
    manifest, history = json.loads(a.manifest.read_text()), json.loads(a.history.read_text())
    batches = []
    for b in manifest['batches']:
        if b['status'] != 'ok':
            continue
        source = ROOT / b['text']
        if sha(source) != b['text_sha256']:
            raise ValueError('Source hash mismatch: ' + b['date'])
        batches.append((source, b['date']))
    if not batches:
        raise ValueError('No verified new source lists')
    matcher = RootMatcher(json.loads(CONFIG.read_text()))
    rows, counts, excluded, invalid = select(batches, set(history['domains']), matcher)
    if len(rows) > 20000:
        raise ValueError('Explicitly split a larger queue before crawling')
    a.output.mkdir(parents=True)
    reuse = a.output / 'reused.jsonl'
    reuse.write_text('')
    queue = {'version': 'new-source-expansion-v1',
        'summary': {'universe': len(rows), 'queued': len(rows), 'reused': 0},
        'source': {'path': str(a.manifest), 'sha256': sha(a.manifest),
            'window': {'start': manifest['window_start'], 'end': manifest['window_end']}},
        'reuse_sha256': sha(reuse), 'history_sha256': sha(a.history), 'root_config_sha256': sha(CONFIG),
        'selection': 'All new valid domains matching the same 51 roots; exclude every prior attempted domain, including prior failures. No TLD quota.',
        'source_note': manifest['coverage_note'], 'counts': counts, 'domains': rows}
    atomic_json(a.output / 'queue.json', queue)
    atomic_json(a.output / 'audit.json', {'counts': counts, 'excluded_previously_attempted': excluded,
        'invalid_rows': invalid, 'historical_domains': len(history['domains']), 'historical_sources': history['sources'],
        'acquisition': manifest, 'rules': queue['selection'], 'root_config_sha256': queue['root_config_sha256']})
    print(json.dumps({'counts': counts, 'historical_domains': len(history['domains']), 'queue': str(a.output / 'queue.json')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
