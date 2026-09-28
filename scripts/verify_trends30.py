#!/usr/bin/env python3
"""Read-only verification of remaining-queue coverage and published snapshots."""
import argparse
import json
import re
from datetime import date
from urllib.parse import parse_qs, urlparse
from assemble_trends30 import load_background, load_backgrounds, load_captures
from build_trends30 import ROOT, RUN, START, END, DATES, analyze, capture_disclosures, read, remaining_groups
from trends30_validation import capture_time, keyword_key, remaining_coverage, require


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-complete', action='store_true', help='Fail if any queued or sourced keyword has no actual capture')
    parser.add_argument('--check-site', action='store_true', help='Also compare generated JSON/JS, public records, primary captures and protocol')
    args = parser.parse_args()
    captures = load_captures()
    backgrounds = load_backgrounds()
    sourced = {keyword_key(t['keyword']) for part in range(1, 4) for t in read(RUN / f'terms-{part}.json')['terms']}
    sourced.update(keyword_key(t['keyword']) for t in read(RUN / 'query-variants.json'))
    covered = {keyword_key(t) for cap in captures for t in cap['terms']}
    require(covered <= sourced, 'captured keyword has no saved webpage source')
    coverage = remaining_coverage(remaining_groups(), captures, sourced)
    result = {'sourcedTerms': len(sourced), 'queriedTerms': len(covered), 'pendingTerms': len(sourced - covered),
              'captureRecords': len(captures), 'duplicateCaptureIds': 0, 'backgroundRecords': len(backgrounds), 'remainingQueue': coverage}
    if args.require_complete:
        require(coverage['plannedTerms'] > 0, 'missing original remaining queue')
        require(not coverage['missingGroupIds'], 'unqueried original groups: ' + ', '.join(coverage['missingGroupIds']))
        require(covered == sourced, 'unqueried sourced keywords: ' + ', '.join(sorted(sourced - covered)))
    if args.check_site:
        doc = read(ROOT / 'site/trends30-data.json')
        require(doc['captures'] == captures, 'site captures differ from validated packed records; rebuild snapshot')
        require(read(RUN / 'captures.json') == captures, 'assembled snapshot is stale')
        require(read(RUN / 'public/captures.json') == captures, 'public captures are stale')
        require(read(RUN / 'backgrounds.json') == backgrounds, 'assembled backgrounds are stale')
        require(read(RUN / 'public/backgrounds.json') == backgrounds == doc['backgrounds'], 'public/site background records are stale')
        latest_backgrounds = {keyword_key(b['keyword']): b for b in backgrounds}
        if load_background():
            require(read(RUN / 'background.json') == read(RUN / 'public/background.json') == load_background(), 'legacy background was changed or is stale')
        terms = doc['terms']
        require(len(terms) == len(sourced) and {keyword_key(t['keyword']) for t in terms} == sourced, 'site term coverage/duplicates mismatch')
        by_word = {}
        for cap in captures:
            for index, word in enumerate(cap['terms']):
                by_word.setdefault(keyword_key(word), []).append((cap, index))
        for term in terms:
            require(term.get('background') == latest_backgrounds.get(keyword_key(term['keyword'])), f'{term["keyword"]}: latest background mismatch')
            evidence = by_word.get(keyword_key(term['keyword']), [])
            require(term['captureIds'] == [c['id'] for c, _ in evidence], f'{term["keyword"]}: capture references mismatch')
            if not evidence:
                require(term['status'] == 'pending' and term['primaryCaptureId'] is None and term['metrics'] is None, f'{term["keyword"]}: unqueried term counted as queried')
                continue
            cap, index = max(evidence, key=lambda pair: (capture_time(pair[0]), pair[0]['id']))
            expected_status, _, metrics = analyze(cap['series'][index]) if cap['status'] == 'chart' else ('no_data', '', None)
            require((term['primaryCaptureId'], term['status'], term['metrics']) == (cap['id'], expected_status, metrics), f'{term["keyword"]}: latest primary/status/metrics mismatch')
        summary = doc['summary']
        expected_status = 'complete' if sourced and covered == sourced else 'partially_queried' if covered else 'not_queried'
        require((summary['terms'], summary['queried'], summary['pending'], summary['captures']) == (len(sourced), len(covered), len(sourced-covered), len(captures)), 'summary counts mismatch')
        require(summary['remainingQueue'] == coverage and summary['status'] == doc['meta']['status'] == expected_status, 'summary/status coverage mismatch')
        require((summary['backgroundChecks'], summary['backgroundKeywords']) == (len(backgrounds), len(latest_backgrounds)), 'background counts mismatch')
        disclosures = capture_disclosures(captures)
        require(all(summary.get(key) == value for key, value in disclosures.items()), 'query-mode coverage or signal-pattern disclosure is stale')
        groups = remaining_groups()
        singles = {keyword_key(c['terms'][0]) for c in captures if len(c['terms']) == 1}
        pending_candidates = []
        for term in terms:
            key = keyword_key(term['keyword'])
            if key in singles or key not in by_word:
                continue
            cap, index = by_word[key][-1]
            if cap['status'] == 'chart' and analyze(cap['series'][index])[0] in ('emerging', 'rising'):
                pending_candidates.append(term['keyword'])
        session_path = RUN / 'query-session.json'
        expected_collection = read(session_path) if session_path.exists() else {}
        expected_collection.update(queried=len(covered), pending=len(sourced-covered),
                                   pendingGroups=[g for g in groups if g['id'] in coverage['missingGroupIds']],
                                   pendingKeywords=[t['keyword'] for t in terms if keyword_key(t['keyword']) not in covered],
                                   pendingCandidateRechecks=pending_candidates)
        if not sourced-covered:
            expected_collection['status'] = 'queue_complete'
        else:
            require(expected_collection.get('status') != 'queue_complete', 'source query session says complete while keywords remain unqueried')
        require(doc.get('collection') == expected_collection, 'site query-session state or pending groups/keywords/candidate rechecks are stale')
        require(read(RUN / 'public/query-session.json') == expected_collection, 'public query-session snapshot is stale')

        browser_audit = read(RUN / 'public/browser-validation.json')
        initial = read(RUN / 'browser-validation-initial.json')
        baseline = {c['id'] for c in captures if re.fullmatch(r'g\d{2}|r0[1-6]', c['id'])}
        require(len(baseline) == initial['captures'], 'initial browser-audit coverage mismatch')
        require(browser_audit.get('initial_audit') == initial, 'public initial browser audit is stale')
        require(browser_audit.get('captures') == len(captures) and browser_audit.get('chart_series') == sum(len(c['series']) for c in captures), 'public browser-audit totals are stale')
        require(browser_audit.get('all_saved_captures_have_browser_audit') is True, 'public browser-audit coverage is not verified')
        details = browser_audit.get('additional_audited_records', [])
        detail_ids = [row['id'] for row in details]
        require(len(detail_ids) == len(set(detail_ids)) and set(detail_ids) == {c['id'] for c in captures}-baseline, 'public browser-audit detailed IDs are stale, missing or duplicated')
        require(browser_audit.get('no_data_captures') == [c['id'] for c in captures if c['status'] == 'no_data'], 'public browser-audit no-data IDs are stale')
        observed_labels = [date.fromisoformat(d).strftime('%b ') + str(date.fromisoformat(d).day) for d in DATES]
        cap_by_id = {c['id']: c for c in captures}
        for row in details:
            cap = cap_by_id[row['id']]
            require((row.get('terms'), row.get('status'), row.get('captured_at')) == (cap['terms'], cap['status'], cap['captured_at']), row['id']+': public browser-audit record differs from capture')
            require(row.get('observed_date_labels') == (observed_labels if cap['status'] == 'chart' else []), row['id']+': public browser-audit dates differ')
            params = parse_qs(urlparse(row.get('actual_url', '')).query)
            require(params.get('q') == [','.join(cap['terms'])] and params.get('date') == [START+' '+END] and params.get('geo') == ['US'], row['id']+': public browser-audit URL differs')
            require(params.get('gprop', ['']) == [''] and params.get('cat', ['0']) == ['0'], row['id']+': public browser-audit property/category differs')
        js = (ROOT / 'site/trends30-data.js').read_text()
        prefix = 'window.FINDKEYWORDS_TRENDS30 = '
        require(js.startswith(prefix) and json.loads(js[len(prefix):].rstrip().removesuffix(';')) == doc, 'site JS/JSON mismatch')
        for relative in ('trend-protocol.json', 'public/trend-protocol.json'):
            protocol = read(ROOT / 'data/runs/2026-09-26-tld' / relative)
            require(protocol['status'] == expected_status and protocol['coverage'] == summary, f'{relative}: stale protocol coverage')
        result['publishedSnapshot'] = 'verified'
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
