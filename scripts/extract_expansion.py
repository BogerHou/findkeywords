#!/usr/bin/env python3
"""Extract saved literal page phrases after the AWS expansion. Never query Trends."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from curate_full import page_correction, MARKETING, GENERIC, canonical
from probe_full import atomic_json, load_records
from research_pipeline import terms_in_field

ROOT = Path(__file__).resolve().parents[1]
SHELL = {'home', 'homepage', 'welcome', 'about us', 'contact us', 'sign in', 'log in', 'login', 'privacy policy', 'terms of service'}


def literal_phrases(text, roots):
    """Short headings/sentences need no root. Longer fields also retain root spans."""
    found = {term: 'literal_root_span' for term in terms_in_field(text, roots)}
    for segment in re.split(r'[|:;!?\n\r•。！？]|\s[-–—]\s|\.(?=\s|$)', text):
        segment = segment.strip()
        words = re.findall(r'\w+', segment, re.UNICODE)
        non_latin = bool(re.search(r'[^\x00-\x7f]', segment))
        eligible_length = 2 <= len(words) <= 10 or (non_latin and 4 <= len(segment) <= 60)
        if 4 <= len(segment) <= 120 and eligible_length and canonical(segment) not in SHELL:
            if re.search(r'https?://|www\.|\.(?:com|net|org)\b', segment, re.I):
                continue
            found[segment] = 'short_literal_field_segment_needs_semantic_review'
    return found


def extract(rows, roots, prior):
    terms, pages, corrections = {}, [], []
    for row in rows:
        correction = page_correction(row)
        effective = correction or row
        if correction:
            corrections.append(correction)
        fields = row.get('page') or row.get('page_prefix') or {}
        usable = effective['decision'] == 'pass' or effective['reason'] in {'javascript_or_thin', 'thin_or_empty', 'homepage_too_large'}
        incomplete = bool(row.get('incomplete_html') or row.get('page_prefix'))
        page_terms = set()
        if usable:
            sources = [('title', fields.get('title', ''))] + [('h1', s) for s in fields.get('h1', [])] + [('description', fields.get('description', ''))]
            for field, quote in sources:
                for term, method in literal_phrases(quote, roots).items():
                    key = canonical(term)
                    if key not in canonical(quote):
                        raise ValueError('Nonliteral extraction')
                    ev = {'domain': row['domain'], 'field': field, 'quote': quote,
                          'page_decision': effective['decision'], 'page_reason': effective['reason'],
                          'incomplete_html': incomplete, 'checked_at': row.get('checked_at'), 'method': method}
                    entry = terms.setdefault(key, {'keyword': term, 'evidence': [], 'is_new_to_prior_keywords': key not in prior})
                    if not any(all(e[k] == ev[k] for k in ('domain', 'field', 'quote')) for e in entry['evidence']):
                        entry['evidence'].append(ev)
                    page_terms.add(key)
        pages.append({'domain': row['domain'], 'decision': effective['decision'], 'reason': effective['reason'],
                      'original_decision': row['decision'], 'original_reason': row['reason'], 'page': fields,
                      'keywords': sorted(page_terms), 'meaning_review': 'pending',
                      'keyword_status': 'literal_candidates' if page_terms else 'needs_semantic_review' if usable and any(fields.values()) else 'no_usable_page_fields'})
    for entry in terms.values():
        complete = any(e['page_decision'] == 'pass' and not e['incomplete_html'] for e in entry['evidence'])
        entry['review_status'] = 'phrase_review' if MARKETING.search(entry['keyword']) or canonical(entry['keyword']) in GENERIC else 'ready_for_semantic_review' if complete else 'metadata_only'
        entry.update(meaning_review='pending', trends_status='not_queried', language_scope='Source language retained; US demand not inferred')
    return sorted(terms.values(), key=lambda x: canonical(x['keyword'])), pages, corrections


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--prior-keywords', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    domain_summary = json.loads((a.input / 'summary.json').read_text())
    if domain_summary['status'] != 'domains_complete' or domain_summary['pending'] != 0:
        raise ValueError('Require completed domain coverage before final extraction')
    rows = load_records(a.input / 'results.jsonl')
    if len(rows) != domain_summary['queued']:
        raise ValueError('Expansion coverage mismatch')
    roots = {x['term'].casefold() for x in json.loads((ROOT / 'scripts/data/keyword-roots.json').read_text())['roots']}
    prior = {canonical(x['keyword']) for x in json.loads(a.prior_keywords.read_text())}
    keywords, pages, corrections = extract(rows, roots, prior)
    summary = {'status': 'extracted_pending_semantic_and_trends_review', 'updated_at': datetime.now(timezone.utc).isoformat(),
        'domains': len(rows), 'decisions': dict(Counter(x['decision'] for x in pages)),
        'keywords': len(keywords), 'new_to_prior_keywords': sum(x['is_new_to_prior_keywords'] for x in keywords),
        'already_in_prior_keywords': sum(not x['is_new_to_prior_keywords'] for x in keywords),
        'review_statuses': dict(Counter(x['review_status'] for x in keywords)),
        'page_annotations': len(corrections), 'pages_needing_semantics': sum(x['keyword_status'] == 'needs_semantic_review' for x in pages),
        'trends_queries': 0, 'source_results_sha256': hashlib.sha256((a.input / 'results.jsonl').read_bytes()).hexdigest(),
        'prior_keywords_sha256': hashlib.sha256(a.prior_keywords.read_bytes()).hexdigest(),
        'note': '51 roots select domain names only. Saved Title/H1/Description short spans do not require roots. Literal phrases need semantic review; list dates are not verified registration/launch dates. Existing local Trends queue unchanged.'}
    for name, value in [('summary', summary), ('keywords', keywords), ('domains', pages), ('corrections', corrections)]:
        atomic_json(a.output / (name + '.json'), value)
        atomic_json(ROOT / 'site' / ('expansion-' + ('keyword-status' if name == 'summary' else name) + '.json'), value)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
