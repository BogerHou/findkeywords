#!/usr/bin/env python3
"""Render the second keyword round from recorded browser tables, using stdlib.

Usage: python3 -B scripts/render_round2.py
The script never queries a service or estimates absolute search volume.
"""
from __future__ import annotations

import html
import json
import math
from pathlib import Path
import re
from statistics import mean
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DATE = "2026-09-26"
DATA = ROOT / "data" / "runs" / DATE
OUT = ROOT / "reports"
CANDIDATES = DATA / "round2-candidates.json"
CAPTURES = DATA / "round2-browser-captures.json"
ANCHORS = DATA / "round2-anchor-research.json"
ASSESSMENT = DATA / "round2-assessment.json"
ESTIMATES = DATA / "round2-estimates.json"


def text(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def esc(value: object) -> str:
    return html.escape(text(value), quote=True)


def md(value: object) -> str:
    value = html.escape(re.sub(r"\s+", " ", text(value)).strip(), quote=False)
    return re.sub(r"([\\`*_\[\]|~])", r"\\\1", value)


def safe_url(value: object) -> str | None:
    if not isinstance(value, str) or any(ord(c) < 33 for c in value):
        return None
    if any(c in value for c in '<>"\\'):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme in {"https", "http"} and parsed.hostname and parsed.username is None and parsed.password is None:
            return value
    except ValueError:
        pass
    return None


def link(label: object, url: object) -> str:
    valid = safe_url(url)
    return f'<a href="{esc(valid)}" target="_blank" rel="noopener noreferrer">{esc(label)}</a>' if valid else esc(label)


def md_link(label: object, url: object) -> str:
    valid = safe_url(url)
    return f'[{md(label)}](<{valid}>)' if valid else md(label)


def load(path: Path, required: bool = True) -> dict:
    if not path.exists() and not required:
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name}: expected a JSON object")
    return value


def number(value: object) -> str:
    return "—" if value is None else f"{value:.2f}".rstrip("0").rstrip(".")


def validate_capture(capture: dict) -> None:
    terms = capture.get("terms", [])
    if not isinstance(terms, list) or not terms or not all(isinstance(term, str) and term for term in terms):
        raise ValueError(f"{capture.get('id')}: invalid terms")
    if len(set(terms)) != len(terms):
        raise ValueError(f"{capture.get('id')}: duplicate terms")
    status = capture.get("status", "chart")
    if status == "insufficient_data":
        if any(capture.get(key) for key in ("dates", "series", "display_averages")):
            raise ValueError(f"{capture.get('id')}: insufficient_data must not include numeric data")
        return
    if status != "chart":
        raise ValueError(f"{capture.get('id')}: unexpected status {status!r}")
    dates, series = capture.get("dates", []), capture.get("series", [])
    if not isinstance(dates, list) or not dates or not isinstance(series, list) or len(series) != len(terms):
        raise ValueError(f"{capture.get('id')}: chart shape does not match terms")
    for values in series:
        if not isinstance(values, list) or len(values) != len(dates):
            raise ValueError(f"{capture.get('id')}: series length does not match dates")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 100 for v in values):
            raise ValueError(f"{capture.get('id')}: chart values must be finite numbers between 0 and 100")
    display = capture.get("display_averages", [])
    if display and len(display) != len(terms):
        raise ValueError(f"{capture.get('id')}: display averages do not match terms")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in display):
        raise ValueError(f"{capture.get('id')}: invalid display average")


def is_primary(capture: dict) -> bool:
    return text(capture.get("id")).endswith("-90d") and "calibration" not in text(capture.get("id")).lower()


def stats(capture: dict, term_index: int, primary: bool) -> dict:
    if capture.get("status", "chart") == "insufficient_data":
        return {"status": "数据不足", "average": None, "nonzero": "—", "recent": None, "previous": None, "display": None, "raw_count": 0, "used_count": 0, "used_range": "无图表日期", "recent_range": "—", "previous_range": "—", "omitted_date": None}
    values = capture["series"][term_index]
    dates = capture["dates"]
    display = capture.get("display_averages", [])
    used = values[:-1] if primary else values
    used_dates = dates[:-1] if primary else dates
    recent = used[-14:] if primary and len(used) >= 28 else []
    previous = used[-28:-14] if recent else []
    return {
        "status": "有图表", "average": mean(used) if used else None,
        "nonzero": f"{sum(v > 0 for v in used)} / {len(used)}", "recent": mean(recent) if recent else None,
        "previous": mean(previous) if previous else None, "display": display[term_index] if display else None,
        "raw_count": len(values), "used_count": len(used),
        "used_range": f"{used_dates[0]} — {used_dates[-1]}" if used_dates else "无可用日期",
        "recent_range": f"{used_dates[-14]} — {used_dates[-1]}" if recent else "不足 28 个点",
        "previous_range": f"{used_dates[-28]} — {used_dates[-15]}" if previous else "不足 28 个点",
        "omitted_date": dates[-1] if primary else None,
    }


def data_links(paths: list[Path]) -> tuple[str, str]:
    h, m = [], []
    for path in paths:
        if path.exists():
            relative = "../" + path.relative_to(ROOT).as_posix()
            h.append(f'<a href="{esc(relative)}" download>{esc(path.name)}</a>')
            m.append(f'[{md(path.name)}](<{path}>)')
    return " · ".join(h), " · ".join(m)


def generic_html(value: object) -> str:
    if isinstance(value, dict):
        return "<dl>" + "".join(f"<dt>{esc(k)}</dt><dd>{generic_html(v)}</dd>" for k, v in value.items()) + "</dl>"
    if isinstance(value, list):
        return "<ul>" + "".join(f"<li>{generic_html(v)}</li>" for v in value) + "</ul>"
    return f'<span>{esc(value)}</span>'


def main() -> None:
    candidates_data, browser = load(CANDIDATES), load(CAPTURES)
    anchors, assessment = load(ANCHORS, False), load(ASSESSMENT, False)
    estimates = load(ESTIMATES, False)
    candidates = candidates_data.get("candidates", [])
    if not isinstance(candidates, list) or len(candidates) != 32:
        raise ValueError("round2-candidates.json must preserve all 32 candidates")
    terms = [row["original_keyword"] for row in candidates]
    if len(set(terms)) != 32:
        raise ValueError("Candidate keywords must be unique")
    captures = browser.get("captures", [])
    if not isinstance(captures, list):
        raise ValueError("captures must be an array")
    capture_ids = set()
    first = {}
    for capture in captures:
        if not isinstance(capture, dict) or not isinstance(capture.get("id"), str) or capture["id"] in capture_ids:
            raise ValueError("Every capture must have a unique string id")
        capture_ids.add(capture["id"])
        validate_capture(capture)
        if is_primary(capture):
            if capture.get("status", "chart") == "chart" and len(capture["dates"]) != 93:
                raise ValueError(f"{capture['id']}: expected 93 daily points for this round; inspect granularity before rendering")
            for index, term in enumerate(capture["terms"]):
                first.setdefault(term, (capture, index))
    covered = sum(term in first for term in terms)
    charted = sum(term in first and first[term][0].get("status", "chart") == "chart" for term in terms)
    insufficient = covered - charted
    raw_h, raw_m = data_links([CANDIDATES, CAPTURES, ANCHORS, ASSESSMENT, ESTIMATES])
    methods = [
        "保留上一轮的 32 个原始候选词（16 个来源域名），不因曲线为零或数据不足而删除。词面分类只帮助安排查询，不能证明新词、搜索规模或低竞争。",
        "主表使用捕获 ID 以 -90d 结尾且不是 calibration 的首次同词记录；查询词逐字匹配原词。整组数据不足与图表中的零值分开显示，均不能解释为零次搜索。",
        "本轮主表日序列每词有 93 个原始点。排除最后一个日期以避免不完整当日后，使用前 92 个点计算均值和非零点数；未把指数换算成搜索次数。",
        "最近 14 天均值 = 去掉最后一天后的最后 14 个点之和 / 14；前 14 天均值 = 紧邻此前 14 个点之和 / 14。没有自动据此宣称增长，周期、噪声和抽样仍需判断。",
        "页面平均值是浏览器直接显示的值；计算均值来自转录序列且主表排除了最后一天，两者口径不同，不能混同。日期保持页面原标签，查询时刻保留原时区。",
        "每个比较图分别归一化；不同图、不同组、不同时间范围的指数不可直接比较。组内低值可能被更大词压低，页面显示 0 不能证明没有搜索。",
        "12 个月及 calibration 补充记录使用全部转录点计算均值和非零点数，保留页面的时间粒度；不作最近两个 14 天的比较。",
        "这些数据由 AI 通过 Google Trends 网页 DOM／无障碍表读取并转录，不是 Google 官方 CSV。JSON、查询链接、查询时刻与完整序列都可以核验；重新打开可能得到不同抽样结果。",
        "公开供应商的月搜索量是模型估算的滚动月均，不等于报告月份的实际月总量，也不等于网站访问量。量级试算单独列出前提与基准敏感性。",
        "有图表仅表示所在比较组有图表，不代表该词序列非零或有足够需求；五个窄词还另作同组复查，整组数据不足记录保留在 JSON 中。",
    ]
    content = [f'<header><p class="eyebrow">关键词研究 · 第二轮 · {DATE}</p><h1>候选关键词趋势核验</h1><p>32 个原词全部保留。先核验可见趋势，再判断能否比较量级。</p><div class="stats"><span><b>32</b>候选词</span><span><b>{covered}</b>已录入 90 天查询</span><span><b>{charted}</b>有图表</span><span><b>{insufficient}</b>整组数据不足</span><span><b>{32-covered}</b>尚无对应记录</span></div></header>']
    markdown = [f"# 关键词研究第二轮：{DATE}", "", f"32 个候选词全部保留；已录入 90 天查询 {covered} 个，其中有图表 {charted} 个、整组数据不足 {insufficient} 个；尚无对应记录 {32-covered} 个。", ""]
    content.append('<section class="notice"><strong>读数边界</strong><p>同图指数用于相对比较，不是搜索次数。不同组指数不可直接比较；后面的量级试算不是实测搜索量，没有确认任何词为新词、增长机会或低竞争词。</p></section>')
    content.append('<section><h2>方法与可核验记录</h2><ol>' + ''.join(f'<li>{esc(v)}</li>' for v in methods) + '</ol>' + f'<p><strong>记录方法：</strong>{esc(browser.get("method"))}</p><p><strong>查询条件：</strong>{esc(browser.get("filters"))}</p><p class="raw">原始 JSON：{raw_h}</p></section>')
    markdown += ["## 方法与证据", ""] + [f"{i}. {md(v)}" for i,v in enumerate(methods,1)] + ["", f"记录方法：{md(browser.get('method'))}", "", f"查询条件：{md(browser.get('filters'))}", "", f"原始 JSON：{raw_m}", ""]
    if assessment:
        content.append('<section><h2>本轮判断与后续优先项</h2><p>以下是 AI 对已记录证据的解释，未确认商业机会。</p>' + generic_html(assessment) + '</section>')
        markdown += ["## 本轮判断与后续优先项", "", "以下是 AI 对已记录证据的解释，未确认商业机会。", ""]
        markdown += [f"- **{md(k)}**：{md(v)}" for k,v in assessment.items()] + [""]
    if estimates.get('rows'):
        note = '以下为不同基准下的条件性月均量级试算，不是当前月搜索量；上下跨度不是置信区间。尤其不能把 Agent 词年内高峰抬高的年均量当成当前需求。'
        content.append('<section><h2>参照词量级试算：保留不同基准结果</h2><p>' + esc(note) + '</p><p>' + esc(estimates['method']) + '</p><div class="table-wrap"><table><thead><tr><th>目标词</th><th>基准词月均量</th><th>目标 / 基准同图均值</th><th>条件性月均试算</th><th>核验链接</th></tr></thead><tbody>')
        markdown += ['## 参照词量级试算', '', note, '', md(estimates['method']), '', '| 目标词 | 基准词月均量 | 目标 / 基准同图均值 | 条件性月均试算 | 查询 |', '|---|---|---:|---:|---|']
        for r in estimates['rows']:
            anchor = f"{r['anchor_keyword']} · {r['anchor_volume']:,} · {r['anchor_report_month']}报告"
            ratio = f"{r['target_mean']:.4f} / {r['anchor_mean']:.4f}"
            result = f"约 {r['conditional_monthly_estimate']:,.0f}"
            content.append(f'<tr><td>{esc(r["keyword"])}</td><td>{link(anchor,r["anchor_source_url"])}</td><td>{esc(ratio)}</td><td>{esc(result)}</td><td>{link("同图查询",r["query_url"])}</td></tr>')
            markdown.append(f'| {md(r["keyword"])} | {md_link(anchor,r["anchor_source_url"])} | {md(ratio)} | {md(result)} | {md_link(r["capture_id"],r["query_url"])} |')
        check = estimates['anchor_crosscheck']
        warning = f"交叉检查：用 free invoice generator 的 22,200 作为基准，会把 invoice maker 推算成约 {check['predicted_by_ratio']:,.0f}，而同一供应商同报告月份给的是 14,800，偏高约 {(check['prediction_to_provider_ratio']-1)*100:.1f}%。因此只适合探索量级，不能输出精确结论。"
        content.append('</tbody></table></div><p class="notice">' + esc(warning) + '</p><ul>' + ''.join(f'<li>{esc(v)}</li>' for v in estimates['limitations']) + '</ul></section>')
        markdown += ['', warning, ''] + [f'- {md(v)}' for v in estimates['limitations']] + ['']
    content.append('<section><h2>32 个候选词：90 天主表</h2><label class="search">搜索原词、域名、证据或分组<input id="search" type="search" placeholder="例如 agent、sprite、EXIF" autocomplete="off"></label><p id="count" aria-live="polite">显示 32 / 32 个候选词</p><div class="table-wrap"><table id="candidates"><thead><tr><th>原词与来源</th><th>同图记录</th><th>计算均值<br>排除最后一天</th><th>非零点 / 使用点</th><th>最近 14 天均值</th><th>前 14 天均值</th><th>原始证据与核验</th></tr></thead><tbody>')
    markdown += ["## 32 个候选词：90 天主表", "", "计算均值及非零占比排除了最后一天。最近与前 14 天的窗口见每词详情；不同图的数值不可直接横比。", "", "| 原词 | 来源域名 | 记录 | 均值 | 非零点 / 使用点 | 最近 14 天均值 | 前 14 天均值 |", "|---|---|---|---:|---|---:|---:|"]
    details_md = []
    for row in candidates:
        term = row["original_keyword"]
        found = first.get(term)
        domain = row.get("source_domain", "")
        evidence = f'{row.get("source_field", "")}：{row.get("evidence_quote", "")}'
        classification = " / ".join(row.get("name_level_hypotheses", []))
        source_h = link(domain, "https://" + domain)
        metric = {"average":None,"nonzero":"—","recent":None,"previous":None,"display":None}
        record_h, detail_h, record_m = '尚无对应记录', '', '尚无对应记录'
        if found:
            capture, index = found
            metric = stats(capture, index, True)
            record_h = f'{esc(capture["id"])}<br><span class="status">{esc(metric["status"])}</span>'
            date_range = f'{capture["dates"][0]} — {capture["dates"][-1]}' if capture.get("dates") else '数据不足，无图表日期'
            detail_h = '<dl>' + ''.join(f'<dt>{esc(k)}</dt><dd>{esc(v)}</dd>' for k,v in [
                ('查询时间',capture.get('captured_at')),('请求期间',capture.get('period')),('页面日期原标签',date_range),
                ('同图词', ' / '.join(capture['terms'])),('页面显示平均值',number(metric['display'])),
                ('计算使用日期',metric['used_range']),('原始点 / 使用点',f'{metric["raw_count"]} / {metric["used_count"]}'),
                ('排除的最后日期',metric['omitted_date']),('最近 14 天窗口',metric['recent_range']),('前 14 天窗口',metric['previous_range'])]) + '</dl>'
            detail_h += '<p>' + link('打开原同图查询',capture.get('url')) + '</p>'
            if capture.get('series'):
                detail_h += f'<details><summary>原始日期与该词完整序列</summary><pre>{esc(json.dumps({"dates":capture["dates"],"series":capture["series"][index]},ensure_ascii=False,indent=2))}</pre></details>'
            record_m = md_link(capture['id'],capture.get('url')) + ' · ' + md(metric['status'])
            details_md += [f"### {md(row['id'])} · {md(term)}", "", f"来源：{md(domain)}；分组：{md(row.get('comparison_group'))}；词面假设：{md(classification)}。", "", f"页面证据（{md(row.get('source_field'))}）：{md(row.get('evidence_quote'))}", "", f"{md(row.get('source_summary'))}", "", f"查询：{md_link(capture['id'],capture.get('url'))}；时间：{md(capture.get('captured_at'))}；期间：{md(capture.get('period'))}；页面日期原标签：{md(date_range)}。", "", f"同图词：{md(' / '.join(capture['terms']))}。页面显示均值：{number(metric['display'])}。原始点 / 使用点：{metric['raw_count']} / {metric['used_count']}；排除日期：{md(metric['omitted_date'])}。", "", f"计算使用日期：{md(metric['used_range'])}；最近 14 天：{md(metric['recent_range'])}；前 14 天：{md(metric['previous_range'])}。", ""]
        else:
            details_md += [f"### {md(row['id'])} · {md(term)}", "", f"来源：{md(domain)}；分组：{md(row.get('comparison_group'))}；词面假设：{md(classification)}。", "", f"页面证据（{md(row.get('source_field'))}）：{md(row.get('evidence_quote'))}", "", "尚无对应 90 天记录，未填入零值。", ""]
        content.append(f'<tr><td><strong>{esc(term)}</strong><br>{source_h}<br><small>{esc(row.get("comparison_group"))} · {esc(classification)}</small></td><td>{record_h}</td><td>{number(metric["average"])}</td><td>{esc(metric["nonzero"])}</td><td>{number(metric["recent"])}</td><td>{number(metric["previous"])}</td><td><details><summary>查看证据与查询条件</summary><p>{esc(evidence)}</p><p>{esc(row.get("source_summary"))}</p>{detail_h}</details></td></tr>')
        markdown.append(f'| {md(term)} | {md(domain)} | {record_m} | {number(metric["average"])} | {md(metric["nonzero"])} | {number(metric["recent"])} | {number(metric["previous"])} |')
    content.append('</tbody></table></div></section>')
    markdown += ["", "## 每词证据与查询条件", ""] + details_md
    supplement = [capture for capture in captures if not is_primary(capture)]
    content.append('<section><h2>补充比较：12 个月与校准探索</h2><p>计算均值使用全部转录点，保留原图粒度。这里不计算月搜索量。</p>')
    markdown += ["## 补充比较：12 个月与校准探索", "", "计算均值使用全部转录点，保留原图粒度；这里不计算月搜索量。", ""]
    for capture in supplement:
        date_range = f'{capture["dates"][0]} — {capture["dates"][-1]}' if capture.get('dates') else '数据不足，无图表日期'
        content.append(f'<article><h3>{esc(capture["id"])}</h3><p>{link("打开同图查询",capture.get("url"))} · 查询时间：{esc(capture.get("captured_at"))} · 期间：{esc(capture.get("period"))} · 页面日期原标签：{esc(date_range)}</p><div class="table-wrap"><table><thead><tr><th>查询原词</th><th>状态</th><th>计算均值（全部点）</th><th>页面显示均值</th><th>非零点 / 总点</th></tr></thead><tbody>')
        markdown += [f"### {md(capture['id'])}", "", f"{md_link('打开同图查询',capture.get('url'))}；查询时间：{md(capture.get('captured_at'))}；期间：{md(capture.get('period'))}；日期原标签：{md(date_range)}。", "", "| 查询原词 | 状态 | 计算均值（全部点） | 页面显示均值 | 非零点 / 总点 |", "|---|---|---:|---:|---|"]
        for index, term in enumerate(capture['terms']):
            metric = stats(capture,index,False)
            content.append(f'<tr><td>{esc(term)}</td><td>{esc(metric["status"])}</td><td>{number(metric["average"])}</td><td>{number(metric["display"])}</td><td>{esc(metric["nonzero"])}</td></tr>')
            markdown.append(f'| {md(term)} | {md(metric["status"])} | {number(metric["average"])} | {number(metric["display"])} | {md(metric["nonzero"])} |')
        content.append('</tbody></table></div></article>')
        markdown.append('')
    if not supplement:
        content.append('<p>尚无补充记录。</p>')
        markdown += ['尚无补充记录。','']
    content.append('</section>')
    if anchors:
        content.append('<section><h2>公开搜索量参照：保留口径限制</h2><p>供应商估算的滚动月均不等于报告月份的月总量。被采用的基准及条件性试算见前表；暂不采用的线索也明确保留。</p>' + generic_html(anchors.get('conclusion',{})) + '<div class="table-wrap"><table><thead><tr><th>词与来源</th><th>供应商月均估算</th><th>地区 / 报告月份</th><th>统计口径与可用性</th></tr></thead><tbody>')
        markdown += ['## 公开搜索量参照：保留口径限制','','供应商估算的滚动月均不等于报告月份的月总量。被采用的基准及条件性试算见前表。','',md(anchors.get('conclusion',{})),'','| 词与来源 | 供应商月均估算 | 地区 / 报告月份 | 统计口径与可用性 |','|---|---:|---|---|']
        for anchor in anchors.get('anchors',[]):
            scope = f'{anchor.get("market", "—")} / {anchor.get("report_month", "—")}'
            caveat = '；'.join(text(anchor.get(key)) for key in ['averaging_window','usability','reason'] if anchor.get(key))
            content.append(f'<tr><td>{link(anchor.get("keyword"),anchor.get("source_url"))}<br>{esc(anchor.get("provider"))}</td><td>{esc(anchor.get("volume"))}</td><td>{esc(scope)}</td><td>{esc(caveat)}</td></tr>')
            markdown.append(f'| {md_link(anchor.get("keyword"),anchor.get("source_url"))} | {md(anchor.get("volume"))} | {md(scope)} | {md(caveat)} |')
        content.append('</tbody></table></div><details><summary>供应商指标定义与一次实际查询结果</summary>' + generic_html({'metric_definition':anchors.get('metric_definition'), 'interactive_attempt':anchors.get('interactive_attempt')}) + '</details></section>')
        markdown += ['',f"指标定义：{md(anchors.get('metric_definition'))}",'',f"实际查询结果：{md(anchors.get('interactive_attempt'))}",'']
    content.append(f'<footer>原始记录：{raw_h}<p>报告由本地已保存数据生成；点击外部查询链接是重新请求，不等于重放原始结果。</p></footer>')
    css = '''*{box-sizing:border-box}body{margin:0;background:#f5f6f8;color:#192c3b;font:15px/1.7 system-ui,-apple-system,"PingFang SC",sans-serif}main{max-width:1480px;margin:auto;padding:40px 28px 70px}h1{font-size:34px;line-height:1.25;margin:8px 0}h2{font-size:22px}h3{font-size:17px}.eyebrow{color:#496375;font-weight:650}.stats{display:flex;flex-wrap:wrap;gap:24px;margin:26px 0}.stats span{min-width:125px}.stats b{display:block;font-size:30px;line-height:1.3}section{background:#fff;border:1px solid #dde4e9;border-radius:8px;padding:24px;margin:24px 0}.notice{border-left:5px solid #bb8727;background:#fffaf0}a{color:#145e8a;text-underline-offset:3px}li{margin:7px 0}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;vertical-align:top;padding:13px 12px;border-bottom:1px solid #e3e8ed}th{background:#edf2f5;font-size:13px;white-space:nowrap}td:nth-child(1){min-width:200px}td:last-child{min-width:235px}small{color:#597080}.status{color:#675027}details summary{cursor:pointer;color:#145e8a}details p{margin:10px 0}dl{margin:12px 0}dt{font-weight:650;margin-top:8px}dd{margin:0 0 8px;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;background:#f5f7f9;padding:12px;max-height:400px;overflow:auto}.search{display:block;font-weight:600}.search input{display:block;width:min(100%,600px);border:1px solid #9dafbc;border-radius:5px;padding:11px 13px;margin-top:8px;font:inherit}.raw,footer{font-size:13px;overflow-wrap:anywhere}article{margin:22px 0}footer{color:#566d7d}[hidden]{display:none!important}@media(max-width:650px){main{padding:20px 12px}section{padding:16px}.stats{gap:15px}h1{font-size:27px}}'''
    js = '''const input=document.getElementById('search');const rows=[...document.querySelectorAll('#candidates tbody tr')];input.addEventListener('input',()=>{const q=input.value.trim().toLocaleLowerCase();let n=0;for(const row of rows){row.hidden=!row.textContent.toLocaleLowerCase().includes(q);if(!row.hidden)n++;}document.getElementById('count').textContent=`显示 ${n} / ${rows.length} 个候选词`;});'''
    document = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>关键词第二轮核验 · '+DATE+'</title><style>'+css+'</style></head><body><main>'+''.join(content)+'</main><script>'+js+'</script></body></html>\n'
    OUT.mkdir(exist_ok=True)
    (OUT / f'round2-{DATE}.html').write_text(document,encoding='utf-8')
    (OUT / f'round2-{DATE}.md').write_text('\n'.join(markdown)+'\n',encoding='utf-8')
    print(f'Rendered reports/round2-{DATE}.html and .md; all 32 candidates retained; {covered} have 90-day records.')


if __name__ == '__main__':
    main()
