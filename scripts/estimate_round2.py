#!/usr/bin/env python3
"""Conditional anchor sensitivity calculations, not measured monthly volumes."""
import json
from pathlib import Path
from statistics import mean

DATA = Path(__file__).resolve().parents[1] / 'data/runs/2026-09-26'


def main():
    captures = {c['id']: c for c in json.loads((DATA / 'round2-browser-captures.json').read_text())['captures']}
    anchors = {a['keyword'].lower(): a for a in json.loads((DATA / 'round2-anchor-research.json').read_text())['anchors']
               if a.get('source_checked_by_direct_open') and a['market'] == 'United States'}
    rows = []
    for capture_id, targets in [('calibration-12m', ['sprite sheet maker', 'image compressor']),
                                ('agents-calibration-12m', ['agent governance', 'AI agent governance', 'agent observability'])]:
        c = captures[capture_id]
        values = dict(zip(c['terms'], c['series']))
        for target in targets:
            for reference in c['terms']:
                a = anchors.get(reference.lower())
                if not a:
                    continue
                t, r = mean(values[target]), mean(values[reference])
                estimate = a['volume'] * t / r
                interior = a['volume'] * mean(values[target][1:-1]) / mean(values[reference][1:-1])
                rows.append({'keyword': target, 'capture_id': capture_id, 'query_url': c['url'],
                             'anchor_keyword': reference, 'anchor_volume': a['volume'],
                             'anchor_report_month': a['report_month'], 'anchor_source_url': a['source_url'],
                             'target_mean': t, 'anchor_mean': r, 'target_nonzero_weeks': sum(x > 0 for x in values[target]),
                             'weeks': len(values[target]), 'conditional_monthly_estimate': estimate,
                             'edge_week_sensitivity_estimate': interior,
                             'meaning': '若参照词滚动月均与本图时间及查询口径可比，则得到此量级试算；不是观测到的目标词搜索量。'})
    c = captures['calibration-12m']
    values = dict(zip(c['terms'], c['series']))
    prediction = 22200 * mean(values['invoice maker']) / mean(values['free invoice generator'])
    crosscheck = {'target': 'invoice maker', 'anchor': 'free invoice generator',
                  'anchor_volume': 22200, 'predicted_by_ratio': prediction,
                  'independent_provider_estimate': 14800, 'prediction_to_provider_ratio': prediction / 14800,
                  'conclusion': '同供应商同报告月份的两个基准不能精确互相还原；跨度仅表示基准敏感性，不是置信区间。'}
    ranges = []
    for term in dict.fromkeys(r['keyword'] for r in rows):
        selected = [r['conditional_monthly_estimate'] for r in rows if r['keyword'] == term]
        ranges.append({'keyword': term, 'min_anchor_scenario': min(selected), 'max_anchor_scenario': max(selected),
                       'not_a_confidence_interval': True, 'not_current_month_forecast': True})
    recent = []
    c = captures['agents-calibration-12m']
    for term in ['agent governance', 'AI agent governance', 'agent observability']:
        v = c['series'][c['terms'].index(term)]
        recent.append({'keyword': term, 'recent_complete_4week_labels': [c['dates'][-5], c['dates'][-2]],
                       'recent_complete_4week_mean': mean(v[-5:-1]),
                       'preceding_13week_labels': [c['dates'][-18], c['dates'][-6]],
                       'preceding_13week_mean': mean(v[-18:-5]),
                       'peak': max(v), 'peak_week': c['dates'][v.index(max(v))]})
    payload = {
        'method': '条件性月均量级 = 公开基准月均估算 × 目标词同图53周算术均值 / 基准词同图53周算术均值。使用完整序列计算均值，不用界面四舍五入后的整数均值。另计算去掉首尾两周的敏感性结果。',
        'limitations': ['美国／Google网页搜索／全部类别／Search term。', 'Trends 为当前过去12个月；基准来自2026-07/08报告，供应商没有逐词给出精确统计起止日期，时间未严格对齐。', '基准为供应商滚动月均估算，查询变体合并口径未核实；结果仅供探索量级。', '用不同基准算出的最小值、最大值是情景跨度，不是概率置信区间，不保证真实量在其中。', '年度平均不代表当前月；下降中的词尤其不能拿年度均量作为下月流量预测。', '低量词、零值、偶发尖峰受抽样、取整和噪声影响，本轮没有为全部32词强行估值。', '未核查SEO竞争度、排名或可获得点击量，没有确认建站机会。'],
        'anchor_crosscheck': crosscheck, 'rows': rows, 'ranges': ranges, 'agent_recent_comparison': recent,
    }
    (DATA / 'round2-estimates.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'ranges': ranges, 'anchor_crosscheck': crosscheck, 'agent_recent_comparison': recent}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
