#!/usr/bin/env python3
"""Expand losslessly packed browser DOM table transcriptions; no network access."""
import json
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/runs/2026-09-26'
EVIDENCE = DATA / 'round2-evidence'


def unpack(value):
    result = []
    for token in value.split(','):
        number, _, count = token.partition('x')
        result.extend([int(number)] * (int(count) if count else 1))
    return result


def main():
    captures = []
    files = ['dom-series-packed.json', 'annual-series-packed.json',
             'agent-calibration-packed.json', 'small-tools-packed.json',
             'small-image-kitchen-packed.json']
    for filename in files:
        payload = json.loads((EVIDENCE / filename).read_text())
        for row in payload if isinstance(payload, list) else [payload]:
            daily = row['id'].endswith('-90d')
            # Every original DOM date label was checked in the browser against
            # these consecutive daily / weekly sequences before transcription.
            start = date(2026, 6, 26) if daily else date(2025, 9, 21)
            dates = []
            for i in range(row['n']):
                d = start + timedelta(days=i if daily else i * 7)
                label = f'{d:%b} {d.day}' + ('' if daily else f', {d.year}')
                dates.append(label)
            assert (dates[0], dates[-1]) == (row['date_first'], row['date_last'])
            series = [unpack(v) for v in row['packed_series']]
            assert len(series) == len(row['terms']) == len(row['display_averages'])
            assert all(len(v) == row['n'] and all(0 <= n <= 100 for n in v) for v in series)
            captures.append({k: row[k] for k in ('id', 'captured_at', 'url', 'terms', 'display_averages')} |
                            {'status': 'chart', 'period': 'Past 90 days' if daily else 'Past 12 months',
                             'dates': dates, 'series': series, 'transcription_source': filename})
    checks = {r['id']: r for r in json.loads((EVIDENCE / 'browser-sequence-checks.json').read_text())}
    for c in captures:
        assert [sum(v) for v in c['series']] == checks[c['id']]['sums']
        assert [sum(n * (i + 1) for i, n in enumerate(v)) for v in c['series']] == checks[c['id']]['weighted']
    captures.append(json.loads((EVIDENCE / 'narrow-no-chart.json').read_text()))
    payload = {
        'method': 'AI 通过浏览器读取实际 Google Trends 页面 DOM 表格，逐组检查表头已更新为当前查询词后采集。数列用连续相同数值压缩后转录，再无损展开；不是 Google 官方 CSV 导出。',
        'filters': {'market': 'US', 'category': 'All categories', 'channel': 'Web Search', 'query_type': 'Search term', 'interface': 'Classic Explore', 'signed_in': False},
        'date_verification': '浏览器已逐项验证六组日序列标签为2026-06-26至2026-09-26连续93日，五组周序列标签为2025-09-21至2026-09-20连续53周。移除日期标签中的Unicode双向文本控制符，其余标签内容不变。',
        'transcription_verification': '55条序列均已核对点数、数值总和、按位置加权总和与浏览器内存中的直接DOM采集结果一致；这只验证转录，不证明Google数据完全代表真实需求。',
        'limitations': ['没有官方CSV导出；截图仅在浏览器工具输出中。', '相对日期链接随打开日期变化，取数也可能受采样影响。', '主表日统计排除最后一天；年度表保留53周，首尾周可能不完整。', '零指数和整组数据不足均不等于零搜索量。'],
        'captures': captures,
    }
    (DATA / 'round2-browser-captures.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    print(f'{len(captures)} recorded comparisons expanded; no live queries performed.')


if __name__ == '__main__':
    main()
