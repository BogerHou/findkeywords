#!/usr/bin/env python3
"""Apply the user's root list to ALL saved domain names and saved keywords, offline.

Historical screenings stay reproducible. This is the current root-first entry,
not a new crawl, a semantic judgement, or a Google Trends query.
"""
import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'scripts/data/keyword-roots.json'
DOMAIN_INPUT = ROOT / 'data/runs/2026-09-26-month/screening/all_domains.jsonl'
DOMAIN_MANIFEST = DOMAIN_INPUT.with_name('manifest.json')
KEYWORD_INPUT = ROOT / 'site/trends30-data.json'
VERSION = 'root-screen-v1'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


class RootMatcher:
    def __init__(self, config):
        self.roots = config['roots']
        terms = [r['term'].lower() for r in self.roots]
        if len(terms) != len(set(terms)) or not all(re.fullmatch('[a-z]+', t) for t in terms):
            raise ValueError('Roots must be unique English words.')
        # Longest alternatives take precedence at the same starting position.
        choices = '|'.join(re.escape(t) for t in sorted(terms, key=lambda t: (-len(t), t)))
        self.domain_pattern = re.compile(choices, re.I)
        self.keyword_pattern = re.compile(r'(?<!\w)(?:' + choices + r')(?!\w)', re.I)
        self.order = {t: i for i, t in enumerate(terms)}

    def matches(self, text, domain=False):
        if domain:
            text = text.split('.', 1)[0]
            if text.lower().startswith('xn--'):
                return []
        pattern = self.domain_pattern if domain else self.keyword_pattern
        return [{'root': m.group().lower(), 'start': m.start(), 'end': m.end(),
                 'text': m.group()} for m in pattern.finditer(text)]

    def roots_for(self, matches):
        return sorted({m['root'] for m in matches}, key=self.order.get)


def self_test():
    matcher = RootMatcher(read(CONFIG))
    assert len(matcher.roots) == 51
    roots = lambda text, domain=False: matcher.roots_for(matcher.matches(text, domain))
    assert roots('PDF Converter') == ['converter']
    assert roots('convert PDF online') == ['convert', 'online']
    assert roots('image-generator') == ['generator']
    assert roots('makers templates conversion') == []  # No silent stemming.
    assert roots('reformat misinformation') == []
    assert roots('pdfconverter.com', True) == ['converter']
    assert roots('convert-converter.net', True) == ['convert', 'converter']
    assert roots('viewer.online', True) == ['viewer']  # Never match the TLD.
    assert roots('xn--generator.com', True) == []
    assert roots('assistantgenerator2026.xyz', True) == ['generator', 'assistant']
    assert roots('generatormaker.com', True) == ['generator', 'maker']
    assert roots('abc.com', True) == []
    print('Root matching checks passed (boundaries, overlaps, IDN, suffix, no hidden expansion).')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-date', default='2026-09-28')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    run_date = date.fromisoformat(args.run_date)
    config = read(CONFIG)
    matcher = RootMatcher(config)
    manifest = read(DOMAIN_MANIFEST)
    output = ROOT / f'data/runs/{run_date.isoformat()}-roots'
    domains, domain_counts = [], Counter()
    total = skipped_idn = 0
    digest = hashlib.sha256()
    with DOMAIN_INPUT.open('rb') as source:
        for line in source:
            digest.update(line)
            item = json.loads(line)
            total += 1
            domain = item['domain']
            skipped_idn += domain.startswith('xn--')
            hits = matcher.matches(domain, domain=True)
            if not hits:
                continue
            roots = matcher.roots_for(hits)
            domains.append({'domain': domain, 'roots': roots, 'matches': hits,
                            'sourceDate': item['source_date'],
                            'sourceFile': Path(item['source_path']).name,
                            'sourceLine': item['source_line']})
            domain_counts.update(roots)
    if total != manifest['counts']['unique_valid_domains']:
        raise ValueError('Domain source count differs from saved audit manifest.')
    if len({d['domain'] for d in domains}) != len(domains):
        raise ValueError('Duplicate matching domain in input.')
    domains.sort(key=lambda d: d['domain'])
    historical = read(KEYWORD_INPUT)
    keywords, keyword_counts = [], Counter()
    for item in historical['terms']:
        hits = matcher.matches(item['keyword'])
        if not hits:
            continue
        roots = matcher.roots_for(hits)
        keywords.append({'keyword': item['keyword'], 'roots': roots, 'matches': hits,
                         'sources': item['sources'], 'historicalStatus': item['statusLabel'],
                         'historicalCaptureId': item['primaryCaptureId'],
                         'currentTrendStatus': 'pending'})
        keyword_counts.update(roots)
    keywords.sort(key=lambda k: k['keyword'].casefold())
    rules = [
        '只使用用户提供的 51 个英文词根，全部启用；保持原顺序，不自动补充同义词、复数或词形变化。',
        '关键词忽略大小写，按完整单词匹配；空格、连字符、标点可作边界。converter 不重复记为 convert，templates 不自动记为 template。',
        '域名只检查第一个点前的名称，忽略后缀；连写名称用子串匹配。同一位置优先较长词根、重叠片段不重复计数；不同位置可命中多个词根。',
        '匹配记录保留原文本和从 0 开始、左闭右开的字符位置。同一域名对同一词根只计一次，总候选数按域名去重，各词根计数不可相加。',
        '复用已标准化、去重的全量域名名单，不沿用旧抽样配额，不按后缀或名称长度再删减；xn-- 编码首标签不当作英文单词解析。',
        '域名命中仅为名称线索，仍可能偶然命中；要继续抓取 Title、Description、H1 等实际内容并核实搜索词。域名没有命中也不等于没有价值。',
        '已提取关键词单独按关键词文本筛选，保留网页字段与引文；不因来源域名命中就假设关键词也命中。',
        '本步是离线词根筛选，未重新抓取网站或查询 Google Trends；历史结果只作背景，不升级为本轮新词机会。'
    ]
    start, end = run_date - timedelta(days=30), run_date - timedelta(days=1)
    meta = {'version': VERSION, 'runDate': run_date.isoformat(),
            'builtAt': datetime.now(timezone.utc).isoformat(),
            'configVersion': config['version'],
            'goal': config['goal'], 'status': 'root_screen_complete_trends_pending',
            'sourceWindow': manifest['source_window'],
            'historicalTrendWindow': {k: historical['meta'][k] for k in ('start', 'end')},
            'nextTrendWindow': {'start': start.isoformat(), 'end': end.isoformat(), 'days': 30},
            'note': '使用 8/27–9/25 历史域名名单重筛；不是 9/28 最新 30 天的新域名采集。'}
    summary = {'roots': len(config['roots']), 'inputDomains': total,
               'matchedDomains': len(domains), 'excludedEncodedNames': skipped_idn,
               'unmatchedDomains': total - len(domains) - skipped_idn,
               'inputKeywords': len(historical['terms']), 'matchedKeywords': len(keywords),
               'currentTrendQueries': 0, 'confirmedOpportunities': 0}
    provenance = {'configPath': str(CONFIG.relative_to(ROOT)),
                  'configSha256': hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
                  'domainInput': str(DOMAIN_INPUT.relative_to(ROOT)), 'domainSha256': digest.hexdigest(),
                  'keywordInput': str(KEYWORD_INPUT.relative_to(ROOT)),
                  'keywordSha256': hashlib.sha256(KEYWORD_INPUT.read_bytes()).hexdigest(),
                  'method': VERSION}
    roots = [{**r, 'id': r['term'].lower(), 'domainCount': domain_counts[r['term'].lower()],
              'keywordCount': keyword_counts[r['term'].lower()]} for r in config['roots']]
    dataset = {'meta': meta, 'summary': summary, 'roots': roots, 'rules': rules,
               'trendReview': config['trendReview'], 'domains': domains, 'keywords': keywords,
               'provenance': provenance}
    dump(output / 'manifest.json', {'meta': meta, 'summary': summary, 'roots': roots,
                                    'rules': rules, 'provenance': provenance})
    dump(output / 'domain-matches.json', domains)
    dump(output / 'keyword-matches.json', keywords)
    dump(output / 'config.json', config)
    dump(ROOT / 'site/roots-data.json', dataset)
    dump(ROOT / 'site/roots-config.json', config)
    (ROOT / 'site/roots-data.js').write_text('window.FINDKEYWORDS_ROOTS=' + json.dumps(dataset, ensure_ascii=False, separators=(',', ':')) + ';\n', encoding='utf-8')
    (ROOT / 'site/keyword-roots.txt').write_text('\n'.join(r['term'] for r in config['roots'])+'\n', encoding='utf-8')
    report = [f'# 词根筛选 · {run_date}', '', config['goal'], '',
              f'- 用户词根：{len(roots)}，全部启用。',
              f'- 历史域名：{total:,} → 名称命中 {len(domains):,}。',
              f'- 历史已提词：{len(historical["terms"])} → 完整单词命中 {len(keywords)}。',
              '- 本轮新增 Trends 查询：0；确认新词机会：0。',
              f'- 若按本轮日期查询，完整日窗口为 {start} 至 {end}。',
              '- 数据边界：' + meta['note'], '', '## 匹配规则', '']
    report += [f'{i}. {rule}' for i, rule in enumerate(rules, 1)]
    report += ['', '## 下一步趋势核验目标', ''] + ['- '+r for r in config['trendReview']['requirements']]
    report += ['', '## 全部词根及数量', '', '| 词根 | 说明 | 域名命中 | 历史关键词命中 |', '|---|---|---:|---:|']
    report += [f'| {r["term"]} | {r["meaning"]} | {r["domainCount"]:,} | {r["keywordCount"]} |' for r in roots]
    report += ['', '## 复算', '', '```sh', f'python3 scripts/build_roots_site.py --run-date {run_date}',
               'python3 scripts/build_roots_site.py --self-test', '```', '',
               '输入文件与 SHA-256：', '', '```json', json.dumps(provenance, ensure_ascii=False, indent=2), '```', '']
    (ROOT / f'reports/roots-{run_date}.md').write_text('\n'.join(report), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
