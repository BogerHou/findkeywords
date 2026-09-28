#!/usr/bin/env python3
"""Publish saved browser-audit coverage without replacing numerical validation."""
import re
from urllib.parse import parse_qs, urlparse
from assemble_trends30 import load_captures
from build_trends30 import RUN, START, END, dump, read
from trends30_validation import require


def main():
    captures = load_captures()
    initial = read(RUN / 'browser-validation-initial.json')
    baseline = [c for c in captures if re.fullmatch(r'g\d{2}|r0[1-6]', c['id'])]
    require(len(baseline) == initial['captures'], 'initial browser-audit coverage mismatch')
    expected_dates = ['Aug '+str(i) for i in range(27, 32)] + ['Sep '+str(i) for i in range(1, 26)]
    audits = {}
    for path in sorted(RUN.glob('audit-*.json')):
        doc = read(path)
        records = doc if isinstance(doc, list) else doc.get('queries', doc.get('records', []))
        for record in records:
            require(record['id'] not in audits, 'duplicate browser audit '+record['id'])
            audits[record['id']] = record
    verified = []
    for cap in captures:
        if cap in baseline:
            continue
        name = cap['id']
        require(name in audits, 'missing saved browser audit '+name)
        audit = audits[name]
        params = parse_qs(urlparse(audit['url']).query)
        inputs = audit.get('expected_terms', audit.get('inputTerms', audit.get('inputs')))
        require(inputs == cap['terms'] == params['q'][0].split(','), name+': observed URL/input mismatch')
        require(params.get('geo') == ['US'] and params.get('date') == [START+' '+END], name+': observed scope mismatch')
        require(audit['dates'] == (expected_dates if cap['status'] == 'chart' else []), name+': observed date labels mismatch')
        verified.append({'id': name, 'actual_url': audit['url'], 'observed_date_labels': audit['dates'],
                         'terms': inputs, 'status': cap['status'], 'captured_at': cap['captured_at']})
    result = {'method': '保存的浏览器输入、实际URL、表头与日期核对；另有逐日数列双校验。',
              'captures': len(captures), 'chart_series': sum(len(c['series']) for c in captures),
              'initial_audit': initial, 'additional_audited_records': verified,
              'all_saved_captures_have_browser_audit': True,
              'no_data_captures': [c['id'] for c in captures if c['status'] == 'no_data'],
              'limits': '这是转录与参数核验，不是Google数据质量认证；页面错误没有记为无数据，重开页面的采样可能变化。'}
    dump(RUN / 'public/browser-validation.json', result)
    print(f'Published browser-audit coverage for {len(captures)} captures ({len(verified)} new detailed records).')


if __name__ == '__main__':
    main()
