#!/usr/bin/env python3
"""Verify downloaded AWS expansion evidence offline, without making requests."""
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

from curate_full import canonical
from probe_full import atomic_json, load_records
from probe_domains import PageParser, decode_html

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit(root=ROOT):
    run = root / 'results/aws-expansion-20260928'
    inputs = root / 'results/aws-expansion-20260928-input'
    outputs = root / 'results/aws-expansion-20260928-keywords'
    read = lambda p: json.loads(p.read_text())
    queue = read(inputs / 'queue.json')
    summary = read(run / 'summary.json')
    terms_summary = read(outputs / 'summary.json')
    manifest = read(run / 'run.json')
    rows = load_records(run / 'results.jsonl')
    by_domain = {r['domain']: r for r in rows}
    queued = {r['domain']: r for r in queue['domains']}
    require(set(queued) == set(by_domain), 'Domain coverage mismatch')
    require(summary['pending'] == 0 and summary['status'] == 'domains_complete', 'Crawl not complete')
    require(len(rows) == summary['covered'] == summary['universe'], 'Summary count mismatch')
    require(dict(Counter(r['decision'] for r in rows)) == summary['decisions'], 'Decision count mismatch')
    require(sha(inputs / 'queue.json') == manifest['queue_sha256'], 'Queue hash mismatch')
    require(sha(run / 'results.jsonl') == terms_summary['source_results_sha256'], 'Result hash mismatch')
    require(sha(root / 'site/full-keyword-reviewed.json') == terms_summary['prior_keywords_sha256'], 'Prior keyword hash mismatch')
    source_manifest = read(root / queue['source']['path'])
    require(sha(root / queue['source']['path']) == queue['source']['sha256'], 'Source manifest mismatch')
    source_lines = {}
    for batch in source_manifest['batches']:
        require(sha(root / batch['archive']) == batch['sha256'], 'Source archive mismatch')
        require(sha(root / batch['text']) == batch['text_sha256'], 'Source text mismatch')
        source_lines[Path(batch['text']).name] = (root / batch['text']).read_text().splitlines()

    body_files, parsed_pages, empty_pages = set(), 0, 0
    visible_text_variances = []
    for domain, row in by_domain.items():
        require(row['source'] == queued[domain], 'Source row changed: ' + domain)
        source = queued[domain]
        require(source_lines[source['sourceFile']][source['sourceLine'] - 1].strip().lower() == domain,
                'Source line mismatch: ' + domain)
        for request in row.get('requests', []):
            if not request.get('body_file'):
                continue
            path = run / request['body_file']
            require(path.resolve().is_relative_to(run.resolve()), 'Invalid body path')
            body = gzip.decompress(path.read_bytes())
            require(hashlib.sha256(body).hexdigest() == request['body_sha256'], 'Body hash mismatch')
            require(len(body) == request['saved_decoded_bytes'], 'Body length mismatch')
            body_files.add(request['body_file'])
        fields = row.get('page') or row.get('page_prefix')
        if fields is not None:
            homepage = next(q for q in reversed(row['requests']) if q['stage'] == 'homepage')
            if not homepage.get('body_file'):
                require(homepage.get('saved_decoded_bytes') == 0 and not any(fields.values()),
                        'Nonempty page is missing saved body: ' + domain)
                empty_pages += 1
                continue
            body = gzip.decompress((run / homepage['body_file']).read_bytes())
            parser = PageParser()
            parser.feed(decode_html(body, homepage.get('content_type')))
            if 'page' in row:
                parser.close()
            reparsed = parser.extracted()
            require(all(reparsed[k] == fields[k] for k in ('title', 'description', 'og_description', 'h1')),
                    'Saved keyword field parse mismatch: ' + domain)
            if reparsed['visible_text'] != fields['visible_text']:
                visible_text_variances.append({'domain': domain,
                    'saved_visible_characters': len(fields['visible_text']),
                    'local_reparsed_visible_characters': len(reparsed['visible_text']),
                    'keyword_fields_match': True,
                    'note': 'Body hash verified. Full visible text differs on local reparse; cause not established. Original decision preserved.'})
            parsed_pages += 1

    keywords = read(outputs / 'keywords.json')
    require(len(keywords) == len({canonical(k['keyword']) for k in keywords}) == terms_summary['keywords'], 'Keyword count mismatch')
    prior = {canonical(k['keyword']) for k in read(root / 'site/full-keyword-reviewed.json')}
    local_queue = read(root / 'results/local-trends-20260928/queue.json')
    frozen = {canonical(k['keyword']) for k in local_queue['candidates']}
    evidence_count = 0
    for term in keywords:
        require(term['is_new_to_prior_keywords'] == (canonical(term['keyword']) not in prior), 'New keyword flag mismatch')
        for evidence in term['evidence']:
            row = by_domain[evidence['domain']]
            fields = row.get('page') or row.get('page_prefix') or {}
            values = fields.get('h1', []) if evidence['field'] == 'h1' else [fields.get(evidence['field'], '')]
            require(evidence['quote'] in values, 'Quote does not match saved field')
            require(canonical(term['keyword']) in canonical(evidence['quote']), 'Nonliteral keyword')
            require(evidence['checked_at'] == row['checked_at'], 'Evidence time mismatch')
            evidence_count += 1
    pages = read(outputs / 'domains.json')
    require({p['domain'] for p in pages} == set(by_domain), 'Derived page coverage mismatch')
    require(dict(Counter(p['decision'] for p in pages)) == terms_summary['decisions'], 'Corrected decision count mismatch')
    reviews = read(root / 'scripts/data/expansion-semantic-reviews.json')
    term_lookup = {canonical(t['keyword']): t for t in keywords}
    reviewed = set()
    for review in reviews['reviews']:
        key = canonical(review['keyword'])
        require(key in term_lookup and key not in reviewed, 'Missing or duplicate reviewed term')
        reviewed.add(key)
        require(any(all(e[k] == review[k] for k in ('domain', 'field', 'quote')) for e in term_lookup[key]['evidence']),
                'Stale semantic review source: ' + key)
    atomic_json(root / 'site/expansion-semantic-reviews.json', reviews)
    return {'status': 'evidence_integrity_verified', 'verified_at': datetime.now(timezone.utc).isoformat(),
        'domains': len(rows), 'source_lists': len(source_lines), 'saved_body_files_verified': len(body_files),
        'pages_reparsed': parsed_pages, 'empty_page_records_without_body_file': empty_pages,
        'visible_text_reparse_variances': visible_text_variances,
        'keywords': len(keywords), 'literal_evidence_records_verified': evidence_count,
        'keyword_source_domains': len({e['domain'] for k in keywords for e in k['evidence']}),
        'semantic_terms_reviewed': len(reviewed), 'semantic_terms_pending': len(keywords) - len(reviewed),
        'semantic_statuses': dict(Counter(r['status'] for r in reviews['reviews'])),
        'new_to_frozen_local_queue': sum(canonical(k['keyword']) not in frozen for k in keywords),
        'already_in_frozen_local_queue': sum(canonical(k['keyword']) in frozen for k in keywords),
        'source_results_sha256': sha(run / 'results.jsonl'), 'keywords_sha256': sha(outputs / 'keywords.json'),
        'local_trends_queue_sha256': sha(root / 'results/local-trends-20260928/queue.json'),
        'semantic_review_complete': False, 'trends_queries': 0,
        'scope': 'Offline coverage, source archive/text/line hashes, saved response hashes, field reparsing and literal phrase verification. Does not establish site quality, query meaning, launch dates or search demand.'}


if __name__ == '__main__':
    result = audit()
    atomic_json(ROOT / 'results/aws-expansion-20260928-keywords/evidence-audit.json', result)
    atomic_json(ROOT / 'site/expansion-evidence-audit.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
