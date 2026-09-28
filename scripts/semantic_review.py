"""Validate persisted assistant reviews against saved page fields; no network."""
import hashlib
import json
import re


DOMAIN_STATUSES = {'supplemented', 'insufficient_fields', 'entity_or_personal',
                   'conflicting_fields', 'site_shell', 'needs_query_formulation'}
TERM_STATUSES = {'meaning_checked', 'needs_qualifier', 'entity_query'}


def canonical(text):
    return re.sub(r'\s+', ' ', text).strip().casefold()


def fields(row):
    page = row.get('page') or row.get('page_prefix') or {}
    return {key: page.get(key, [] if key == 'h1' else '') for key in ('title', 'description', 'h1')}


def fields_hash(row):
    return hashlib.sha256(json.dumps(fields(row), ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def validate_ledger(ledger, by_domain, candidates, supplements):
    """Reject stale evidence, duplicate reviews and invented phrase/source links."""
    if ledger.get('version') != 1:
        raise ValueError('Unsupported semantic review version')
    domain_reviews, term_reviews = {}, {}
    original = {canonical(r['keyword']): r for r in candidates}
    additions = {(s['domain'], canonical(s['keyword'])) for s in supplements}
    for review in ledger.get('domains', []):
        domain = review['domain']
        if domain in domain_reviews or domain not in by_domain or review['status'] not in DOMAIN_STATUSES:
            raise ValueError('Invalid or duplicate domain review: ' + domain)
        if review['source_fields_sha256'] != fields_hash(by_domain[domain]):
            raise ValueError('Domain fields changed since review: ' + domain)
        if review.get('source_fields') != fields(by_domain[domain]):
            raise ValueError('Domain review omitted or altered its saved fields: ' + domain)
        if not review.get('reason') or not review.get('reviewed_at') or not review.get('batch_id'):
            raise ValueError('Missing review provenance: ' + domain)
        selected = review.get('selected_keywords', [])
        if (review['status'] == 'supplemented') != bool(selected):
            raise ValueError('Supplement review needs selected phrases: ' + domain)
        if any((domain, canonical(term)) not in additions for term in selected):
            raise ValueError('Domain review references a missing supplement: ' + domain)
        domain_reviews[domain] = review
    for review in ledger.get('terms', []):
        key = canonical(review['keyword'])
        if key in term_reviews or key not in original or review['status'] not in TERM_STATUSES:
            raise ValueError('Invalid or duplicate term review: ' + key)
        evidence = review['evidence']
        source = by_domain.get(evidence['domain'])
        if not source or review['source_fields_sha256'] != fields_hash(source):
            raise ValueError('Term source changed: ' + key)
        page = fields(source)
        values = page[evidence['field']] if evidence['field'] == 'h1' else [page[evidence['field']]]
        if evidence['quote'] not in values or key not in canonical(evidence['quote']):
            raise ValueError('Term not supported by quoted field: ' + key)
        if not any(all(e.get(k) == evidence[k] for k in ('domain', 'field', 'quote')) for e in original[key]['evidence']):
            raise ValueError('Term review does not match original source: ' + key)
        if not all(review.get(k) for k in ('reason', 'meaning', 'reviewed_at', 'batch_id')):
            raise ValueError('Missing term review provenance: ' + key)
        term_reviews[key] = review
    return domain_reviews, term_reviews
