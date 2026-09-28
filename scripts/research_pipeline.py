#!/usr/bin/env python3
"""Wait for full domain coverage, then extract evidence-backed terms and query Trends."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import time

from probe_full import atomic_json, load_records
import probe_prescreen as pre
from trends_full import Client, RULE, evaluate_30, evaluate_background, windows

ROOT = Path(__file__).resolve().parents[1]
STOP = set('a an the and or for with from by of your our their my to is are be get use create build best free top easy simple powerful ultimate instant professional welcome official home website site tool tools'.split())


def terms_in_field(text, roots):
    """Conservative literal phrases; no words inferred from the domain name."""
    found = set()
    for segment in re.split(r'[|:;!?\n\r•]|\s[-–—]\s|\.(?=\s|$)', text):
        words = list(re.finditer(r'[A-Za-z0-9]+(?:[+\x27-][A-Za-z0-9]+)*', segment))
        # Preserve short complete headings (including modifiers AFTER the root),
        # e.g. "Logo Maker SVG" and "Font Detector From Image". Otherwise an
        # end-at-root extractor would erase the more specific query itself.
        whole_start, whole_end = 0, len(words)
        while whole_start < whole_end and words[whole_start].group().casefold() in STOP:
            whole_start += 1
        while whole_end > whole_start and words[whole_end-1].group().casefold() in STOP:
            whole_end -= 1
        whole_tokens = [w.group().casefold() for w in words[whole_start:whole_end]]
        if 2 <= len(whole_tokens) <= 7 and any(t in roots for t in whole_tokens) and any(t not in STOP and t not in roots for t in whole_tokens):
            phrase = re.sub(r'\s+', ' ', segment[words[whole_start].start():words[whole_end-1].end()]).strip().casefold()
            if 4 <= len(phrase) <= 80 and re.fullmatch(r"[a-z0-9+\x27 &/().-]+", phrase) and not re.search(r'https?://|www\.|\.(com|net|org)\b', phrase):
                found.add(phrase)
        for i, word in enumerate(words):
            if word.group().casefold() not in roots:
                continue
            start, end = max(0, i - 5), i + 1
            if i == 0 or word.group().casefold() in {'online', 'convert', 'example', 'sample'}:
                end = min(len(words), i + 4)
            # Boundary words before the root delimit marketing boilerplate.
            for j in range(start, i):
                if words[j].group().casefold() in {'with', 'your', 'our', 'the', 'best', 'free', 'use', 'using', 'get', 'is', 'are'}:
                    start = j + 1
            while start < end and words[start].group().casefold() in STOP:
                start += 1
            while end > start and words[end - 1].group().casefold() in STOP:
                end -= 1
            tokens = [w.group().casefold() for w in words[start:end]]
            if not 2 <= len(tokens) <= 7 or not any(t not in STOP and t not in roots and t != 'online' for t in tokens):
                continue
            # Preserve interior punctuation/hyphens; term is a literal field span.
            phrase = re.sub(r'\s+', ' ', segment[words[start].start():words[end - 1].end()]).strip().casefold()
            if 4 <= len(phrase) <= 80 and re.fullmatch(r"[a-z0-9+\x27 &/().-]+", phrase) and not re.search(r'https?://|www\.|\.(com|net|org)\b', phrase):
                found.add(phrase)
    return sorted(found)


def extract(records, root_ids):
    by_term, audit = {}, []
    for row in records:
        eligible = row['decision'] == 'pass' or row['reason'] in {'javascript_or_thin', 'thin_or_empty', 'homepage_too_large'}
        fields = row.get('page') or row.get('page_prefix') or {}
        extracted = set()
        if eligible:
            sources = [('title', fields.get('title', ''))] + [('h1', s) for s in fields.get('h1', [])]
            # Description is a fallback, kept visible as a weaker phrase source.
            if not any(terms_in_field(text, root_ids) for _, text in sources):
                sources.append(('description', fields.get('description', '')))
            for field, text in sources:
                for term in terms_in_field(text, root_ids):
                    evidence = {'domain': row['domain'], 'field': field, 'quote': text,
                                'page_decision': row['decision'], 'page_reason': row['reason'],
                                'checked_at': row.get('checked_at'), 'incomplete_html': row.get('incomplete_html', False)}
                    by_term.setdefault(term, []).append(evidence)
                    extracted.add(term)
        audit.append({'domain': row['domain'], 'decision': row['decision'], 'reason': row['reason'],
                      'terms': sorted(extracted), 'keyword_status': 'literal_candidates' if extracted else 'needs_keyword_review' if eligible and any(fields.values()) else 'no_usable_page_evidence',
                      'checked_at': row.get('checked_at'), 'reused': row.get('reused', False),
                      'page': {k: fields.get(k) for k in ('title', 'description', 'h1')},
                      'request_evidence': [{k: q.get(k) for k in ('url', 'stage', 'http_status', 'error_kind', 'body_sha256')} for q in row.get('requests', [])]})
    candidates = [{'keyword': word, 'evidence': refs, 'extraction': 'literal_page_phrase_v1', 'meaning_review': 'pending'} for word, refs in by_term.items()]
    # Broad generic phrases are not excluded. This ordering spends requests on
    # stronger page support first without an arbitrary term-count cutoff.
    candidates.sort(key=lambda r: (-sum(e['field'] in {'title', 'h1'} for e in r['evidence']), hashlib.sha256(r['keyword'].encode()).hexdigest()))
    return candidates, audit


def run(args):
    if not args.execute:
        print(json.dumps({'mode': 'offline_preview', 'network_requests': 0, 'rule': RULE}))
        return
    pre.validate_network(args.network_config)
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / '.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        summary_path = args.output / 'summary.json'
        previous = json.loads(summary_path.read_text()) if summary_path.exists() else {}
        if previous.get('status') in {'paused', 'needs_final_review'}:
            raise SystemExit('Prior workflow requires review, not automatic replay')
        state = {'status': 'waiting_for_domain_screening', 'rule': RULE, 'queried': 0, 'confirmed': None}
        def publish():
            state['updated_at'] = datetime.now(timezone.utc).isoformat()
            atomic_json(summary_path, state)
            atomic_json(ROOT / 'site/full-trends-status.json', state)
        publish()
        while True:
            p = args.domains / 'summary.json'
            domain_summary = json.loads(p.read_text()) if p.exists() else {}
            if domain_summary.get('status') == 'domains_complete' and domain_summary.get('pending') == 0:
                break
            if domain_summary.get('status') in {'paused', 'interrupted'}:
                state.update(status='paused', error='Domain screening stopped: ' + str(domain_summary.get('stop_reason')))
                publish()
                return
            stamp = domain_summary.get('updated_at')
            if stamp and (datetime.now(timezone.utc) - datetime.fromisoformat(stamp.replace('Z', '+00:00'))).total_seconds() > 300:
                state.update(status='paused', error='Domain progress has not updated for five minutes; inspect the service before continuing.')
                publish()
                return
            time.sleep(30)
        input_dir = args.queue.parent
        queue = json.loads(args.queue.read_text())
        if hashlib.sha256((input_dir / 'reused.jsonl').read_bytes()).hexdigest() != queue['reuse_sha256']:
            raise ValueError('Reused evidence changed')
        records = load_records(input_dir / 'reused.jsonl') + load_records(args.domains / 'results.jsonl', {r['domain'] for r in queue['domains']})
        if len(records) != queue['summary']['universe'] or len({r['domain'] for r in records}) != len(records):
            raise ValueError('Domain coverage not complete')
        roots = {r['id'] for r in json.loads((ROOT / 'site/roots-data.json').read_text())['roots']}
        candidates, audit = extract(records, roots)
        candidate_path = args.output / 'candidates.json'
        candidate_doc = {'candidates': candidates, 'domain_statuses': dict(Counter(r['keyword_status'] for r in audit)),
                         'source_results_sha256': hashlib.sha256((args.domains / 'results.jsonl').read_bytes()).hexdigest()}
        atomic_json(candidate_path, candidate_doc)
        atomic_json(ROOT / 'site/full-domain-results.json', audit)
        atomic_json(ROOT / 'site/full-keyword-candidates.json', candidate_doc)
        window_file = args.output / 'window.json'
        window = json.loads(window_file.read_text()) if window_file.exists() else windows()
        atomic_json(window_file, window)
        result_path = args.output / 'results.jsonl'
        raw = result_path.read_bytes() if result_path.exists() else b''
        if raw and not raw.endswith(b'\n'):
            raise ValueError('Partial Trends result needs review')
        results = [json.loads(x) for x in raw.splitlines()]
        done = {r['keyword'] for r in results}
        if len(done) != len(results) or not done <= {r['keyword'] for r in candidates}:
            raise ValueError('Trends result coverage mismatch')
        state.update(status='querying_trends', candidates=len(candidates), pending=len(candidates) - len(done), queried=len(done),
                     window=window, domain_statuses=candidate_doc['domain_statuses'], extraction_method='Literal Title/H1 phrases; Description fallback. Unextractable pages remain pending semantic review.')
        publish()
        client = Client(args.output / 'evidence')
        try:
            if len(done) < len(candidates):
                client.initialize()
            with result_path.open('a') as out:
                for item in candidates:
                    term = item['keyword']
                    if term in done:
                        continue
                    state['current_keyword'] = term
                    publish()
                    chart = client.chart(term, window['start'], window['end'])
                    row = {**item, 'window': window, 'chart30': chart,
                           'assessment': evaluate_30(chart['points'], window) if chart['status'] == 'chart' else {'status': chart['status'], 'eligible': False},
                           'matches_automatic_screen': False, 'final_review': 'pending'}
                    if row['assessment']['eligible']:
                        background = client.chart(term, window['background_start'], window['end'])
                        row['background'] = background
                        row['background_assessment'] = evaluate_background(background['points'], window)
                        if row['background_assessment']['eligible']:
                            repeat = client.chart(term, window['start'], window['end'])
                            row['repeat30'] = repeat
                            row['repeat_assessment'] = evaluate_30(repeat['points'], window) if repeat['status'] == 'chart' else {'eligible': False, 'status': repeat['status']}
                            row['matches_automatic_screen'] = row['repeat_assessment']['eligible']
                    out.write(json.dumps(row, ensure_ascii=False) + '\n')
                    out.flush()
                    os.fsync(out.fileno())
                    results.append(row)
                    done.add(term)
                    state.update(queried=len(done), pending=len(candidates) - len(done), automatic_matches=sum(r['matches_automatic_screen'] for r in results),
                                 assessments=dict(Counter(r['assessment']['status'] for r in results)))
                    atomic_json(ROOT / 'site/full-trends-results.json', results)
                    publish()
        except Exception as exc:
            state.update(status='paused', error=type(exc).__name__ + ': ' + str(exc)[:500],
                         note='Failed/blocked requests are not no-data results. No automatic retries or IP rotation.')
            publish()
            print(json.dumps(state, ensure_ascii=False), flush=True)
            return
        state.update(status='needs_final_review', current_keyword=None,
                     note='Automatic screening complete; keyword meaning, page quality and candidate evidence still require review. Not verified search volume.')
        publish()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--queue', type=Path, required=True)
    p.add_argument('--domains', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--network-config', type=Path, default=pre.NETWORK_CONFIG)
    p.add_argument('--execute', action='store_true')
    run(p.parse_args())
