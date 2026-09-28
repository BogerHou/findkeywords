#!/usr/bin/env python3
"""Offline corrections and query-phrase triage; never substitutes for Trends data."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from probe_full import atomic_json, load_records

ROOT = Path(__file__).resolve().parents[1]
PARKING = re.compile(r'^(?:namecheap parking page|parked domain name on hostinger dns system|domain registered at whc\.ca|domain parking|(?:[a-z0-9.-]+\.[a-z]{2,}) (?:is )?for sale(?:\s*[|–—].*)?)$', re.I)
PLACEHOLDER = re.compile(r'^(?:coming soon[.!…]*|launching soon[.!…]*|site en construction|domain default page|site is created successfully!|новый сайт успешно создан и готов к работе|エックスサーバー サーバー初期ページ|webcake\s*[|]\s*chưa xuất bản|sorry, the website has been stopped|website is online|.*\s[–—-]\scoming soon|website [a-z0-9.-]+ is ready\. the content is to be added)$', re.I)
CHALLENGE = re.compile(r'^(?:security check|client challenge|confirm you are human|verify you are human|robot or human\??)$', re.I)
MARKETING = re.compile(r'\b(?:complete guide|ultimate guide|essential guide|your guide|grow organic traffic|boosting online visibility|maximizing online visibility|unlocking|grow your|boost your|our online|your online|toggle menu|sign up|sign in|log in|contact us|cookie policy|privacy policy|terms of service)\b', re.I)
GENERIC = {'online presence', 'online visibility', 'authority online', 'online success', 'online experience', 'online business', 'online journey', 'online world'}


def page_correction(row):
    fields = row.get('page') or row.get('page_prefix') or {}
    for field, values in [('title', [fields.get('title', '')]), ('h1', fields.get('h1', []))]:
        for text in values:
            for pattern, decision, reason in [(CHALLENGE, 'recheck', 'review_challenge'), (PARKING, 'skip', 'review_parking'), (PLACEHOLDER, 'skip', 'review_placeholder')]:
                if pattern.fullmatch(text.strip()):
                    return {'domain': row['domain'], 'original_decision': row['decision'], 'original_reason': row['reason'],
                            'decision': decision, 'reason': reason, 'field': field, 'quote': text,
                            'method': 'Exact saved heading pattern; no new network access.'}
    return None


def canonical(text):
    return re.sub(r'\s+', ' ', text).strip().casefold()


def run():
    result_path = ROOT / 'results/aws-full-20260928/results.jsonl'
    reuse_path = ROOT / 'results/aws-full-20260928-input/reused.jsonl'
    candidate_path = ROOT / 'results/aws-full-20260928-trends/candidates.json'
    raw_candidates = json.loads(candidate_path.read_text())
    result_hash = hashlib.sha256(result_path.read_bytes()).hexdigest()
    if raw_candidates['source_results_sha256'] != result_hash:
        raise ValueError('Candidate source mismatch')
    rows = load_records(reuse_path) + load_records(result_path)
    by_domain = {r['domain']: r for r in rows}
    if len(rows) != 16090 or len(by_domain) != len(rows):
        raise ValueError('Full coverage required')
    corrections = {r['domain']: c for r in rows if (c := page_correction(r)) is not None}
    candidates = []
    for item in raw_candidates['candidates']:
        usable = [e for e in item['evidence'] if e['domain'] not in corrections and by_domain[e['domain']]['decision'] != 'skip']
        if not usable:
            status, reason = 'no_usable_source', '来源证据全部为已纠正的停放、占位、验证页或已跳过页面。'
        elif MARKETING.search(item['keyword']) or item['keyword'] in GENERIC:
            status, reason = 'phrase_review', '包含明确营销/导航用语，或过于泛化的营销短语；暂不直接作为用途关键词查询。'
        elif all(e['page_decision'] != 'pass' or e.get('incomplete_html') for e in usable):
            status, reason = 'metadata_only', '仅有薄页面或截断内容的标签证据；保留线索，页面用途还需复核。'
        else:
            status, reason = 'ready_for_semantic_review', '有完整页面字段支持，未命中本轮明确噪声规则；仍需语义与趋势验证。'
        candidates.append({**item, 'review_status': status, 'review_reason': reason,
                           'usable_evidence_count': len(usable), 'source_kind': 'original_literal_extraction'})
    supplement_path = ROOT / 'scripts/data/full-keyword-supplements.json'
    supplements = json.loads(supplement_path.read_text())
    existing = {canonical(r['keyword']): r for r in candidates}
    supplemented_domains = set()
    for addition in supplements:
        domain, term, field = addition['domain'], addition['keyword'], addition['field']
        source = by_domain[domain]
        if domain in corrections or source['decision'] == 'skip':
            raise ValueError('Supplement source rejected: ' + domain)
        page = source.get('page') or source.get('page_prefix') or {}
        values = page.get(field, []) if field == 'h1' else [page.get(field, '')]
        quote = next((s for s in values if canonical(term) in canonical(s)), None)
        if quote is None:
            raise ValueError('Supplement is not a literal source phrase: ' + term)
        if canonical(term) in existing:
            continue
        supplemented_domains.add(domain)
        candidates.append({'keyword': term, 'source_kind': 'saved_fields_manual_supplement',
                           'review_status': 'supplement_needs_trends', 'review_reason': addition['reason'],
                           'meaning_review': 'literal_use_case_checked_not_growth_verified',
                           'evidence': [{'domain': domain, 'field': field, 'quote': quote,
                                         'checked_at': source.get('checked_at'), 'page_decision': source['decision'],
                                         'page_reason': source['reason'], 'incomplete_html': source.get('incomplete_html', False)}]})
    old_audit = json.loads((ROOT / 'site/full-domain-results.json').read_text())
    unresolved = [r for r in old_audit if r['keyword_status'] == 'needs_keyword_review' and r['domain'] not in corrections and r['domain'] not in supplemented_domains]
    effective = Counter(corrections.get(r['domain'], r)['decision'] for r in rows)
    trend_state = json.loads((ROOT / 'results/aws-full-20260928-trends/summary.json').read_text())
    summary = {'version': 'offline-curation-v1', 'updated_at': datetime.now(timezone.utc).isoformat(),
               'source_sha256': {'results': result_hash, 'reused': hashlib.sha256(reuse_path.read_bytes()).hexdigest(),
                                 'raw_candidates': hashlib.sha256(candidate_path.read_bytes()).hexdigest()},
               'domain_total': len(rows), 'original_decisions': dict(Counter(r['decision'] for r in rows)),
               'corrected_decisions': dict(effective), 'page_annotations': len(corrections),
               'changed_decisions': sum(r['original_decision'] != r['decision'] for r in corrections.values()),
               'page_annotation_reasons': dict(Counter(r['reason'] for r in corrections.values())),
               'original_candidates': len(raw_candidates['candidates']), 'supplemented_phrases': len(candidates)-len(raw_candidates['candidates']),
               'total_phrases': len(candidates), 'phrase_statuses': dict(Counter(r['review_status'] for r in candidates)),
               'supplemented_domains': len(supplemented_domains),
               'unextracted_domains_still_needing_review': len(unresolved),
               'trend_queries_successful': trend_state.get('queried', 0), 'trend_block': trend_state.get('error'),
               'note': 'Only domain names were filtered by the 51 roots. The original literal extractor also required an exact root in page phrases, which misses plural forms and other real uses; supplements correct observed examples, not all semantic omissions. No valuable/rising keywords have been confirmed.'}
    atomic_json(ROOT / 'site/full-curation-summary.json', summary)
    atomic_json(ROOT / 'site/full-keyword-reviewed.json', candidates)
    atomic_json(ROOT / 'site/full-domain-review.json', list(corrections.values()))
    atomic_json(ROOT / 'results/aws-full-20260928-trends/semantic-review-remaining.json', unresolved)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    run()
