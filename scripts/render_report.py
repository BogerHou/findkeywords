#!/usr/bin/env python3
"""Render the 2026-09-26 domain pilot into safe, standalone HTML and Markdown.

Run from any directory: python3 -B scripts/render_report.py
Only Python's standard library is required. Review evidence must be a literal
substring of its recorded source field; H1 values are joined with spaces.
"""

from __future__ import annotations

from collections import Counter
import html
import json
from pathlib import Path
import re
import sys
from urllib.parse import quote, urlencode, urlsplit


ROOT = Path(__file__).resolve().parents[1]
RUN_DATE = "2026-09-26"
DATA = ROOT / "data" / "runs" / RUN_DATE
OUTPUT = ROOT / "reports"
DECISIONS = {"candidate": "继续查趋势", "observe": "待观察", "exclude": "本轮排除"}
REGISTRATION = {"verified_recent": "近期注册", "verified_old": "注册较早", "unknown": "注册时间未知"}
FETCH = {"ok": "取得页面", "network_error": "连接失败", "http_error": "网站未允许访问或页面不可用",
         "blocked_url": "地址未通过检查", "too_large": "页面超出采样上限", "redirect_error": "跳转未完成",
         "unsupported_content_type": "非网页内容", "invalid_domain": "域名无效", "parse_error": "页面无法解析"}
FIELDS = {"title": "标题", "description": "描述", "og_description": "分享描述", "h1": "H1", "visible_text": "正文摘录"}
NOTE = "候选仅表示可以继续查趋势，不代表低竞争或已确认关键词机会。注册时间未知的域名不会列为候选。"
AUDIT_NOTE = ("2026-09-26 复核补充：名称筛选只做 43 个预设词根的子串匹配，"
              "再限制首段长度小于 34、无连续三个数字；140,000 → 1,224 → 1,221 → 1,210。"
              "其中 138,776 个仅因未命中词根而排除，不能说它们没有意义。"
              "52 个是 AI 为试跑做的主观目的选样（40 个任务名称、12 个概念线索），没有可复算排名。"
              "原文“人工选取”表述不准确；其余 1,158 个未被证明没有价值。")


def s(value: object) -> str:
    return "" if value is None else str(value)


def esc(value: object) -> str:
    return html.escape(s(value), quote=True)


def md(value: object) -> str:
    value = html.escape(re.sub(r"\s+", " ", s(value)).strip(), quote=False)
    return re.sub(r"([\\`*_\[\]|~])", r"\\\1", value)


def safe_url(value: object) -> str | None:
    value = s(value)
    if any(ord(char) < 33 for char in value) or any(char in value for char in '<>"\\'):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme in {"http", "https"} and parsed.hostname and parsed.username is None and parsed.password is None:
            return value
    except ValueError:
        pass
    return None


def a(label: object, url: object) -> str:
    url = safe_url(url)
    return f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(label)}</a>' if url else esc(label)


def md_link(label: object, url: object) -> str:
    url = safe_url(url)
    return f"[{md(label)}](<{url}>)" if url else md(label)


def trends_url(keyword: str, market: str = "") -> str:
    return "https://trends.google.com/trends/explore?" + urlencode(
        {"date": "today 3-m", "geo": market, "q": keyword, "hl": "zh-CN"}, quote_via=quote)


def field_text(probe: dict, field: str) -> str:
    value = probe.get(field, "")
    return " ".join(s(part) for part in value) if field == "h1" and isinstance(value, list) else s(value)


def load_array(path: Path) -> list:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise ValueError(f"{path.name} must contain an array of objects")
    return value


def load_records() -> tuple[list[dict], list[dict]]:
    probes = load_array(DATA / "probes.json")
    by_domain = {}
    for probe in probes:
        domain = probe.get("domain")
        if not isinstance(domain, str) or not domain or domain in by_domain:
            raise ValueError(f"probes.json contains an invalid or duplicate domain: {domain!r}")
        by_domain[domain] = probe
    reviews = {}
    errors = []
    for filename in ("reviews_tools.json", "reviews_novel.json"):
        for review in load_array(DATA / filename):
            domain = review.get("domain")
            if domain not in by_domain:
                errors.append(f"{filename}: unknown domain {domain!r}")
                continue
            if domain in reviews:
                errors.append(f"{filename}: duplicate review for {domain}")
                continue
            if review.get("decision") not in DECISIONS:
                errors.append(f"{domain}: invalid decision {review.get('decision')!r}")
            keywords = review.get("keywords", [])
            if not isinstance(keywords, list):
                errors.append(f"{domain}: keywords must be an array")
                keywords = []
            for keyword in keywords:
                if not isinstance(keyword, dict):
                    errors.append(f"{domain}: keyword entry must be an object")
                    continue
                field, evidence = keyword.get("source_field"), keyword.get("evidence_quote")
                if not isinstance(keyword.get("keyword"), str) or not keyword["keyword"].strip():
                    errors.append(f"{domain}: keyword must be a nonempty string")
                if field not in FIELDS or not isinstance(evidence, str) or not evidence or evidence not in field_text(by_domain[domain], field):
                    errors.append(f"{domain}: evidence_quote is not an exact substring of {field!r}: {evidence!r}")
            reviews[domain] = review
    if errors:
        raise ValueError("Evidence validation failed:\n" + "\n".join(errors))
    records = []
    for domain, probe in by_domain.items():
        review = dict(reviews.get(domain, {"domain": domain, "page_type": "unreviewed", "decision": "observe",
                                           "summary": "尚未人工复核。", "keywords": []}))
        if review["decision"] == "candidate" and probe.get("registration_status") != "verified_recent":
            review["decision"] = "observe"
            reason = "注册时间未核实为近期，报告将其移入待观察。"
            review["review_note"] = " ".join(filter(None, [s(review.get("review_note")), reason]))
        records.append({"probe": probe, "review": review})
    order = {"candidate": 0, "observe": 1, "exclude": 2}
    records.sort(key=lambda row: (order[row["review"]["decision"]], row["probe"]["domain"]))
    path = DATA / "trends_checks.json"
    checks = []
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        checks = payload.get("checks", []) if isinstance(payload, dict) else None
        if not isinstance(checks, list) or not all(isinstance(check, dict) for check in checks):
            raise ValueError("trends_checks.json must contain a checks array of objects")
    return records, checks


def counts_for(records: list[dict]) -> dict:
    return {"total": len(records),
            "keyword_evidence_count": sum(len(row["review"].get("keywords", [])) for row in records),
            "registration": Counter(row["probe"].get("registration_status", "unknown") for row in records),
            "fetch": Counter(row["probe"].get("fetch_status", "unknown") for row in records),
            "decision": Counter(row["review"]["decision"] for row in records)}


def expansion_text(review: dict) -> str:
    values = review.get("expanded_keywords", [])
    if not isinstance(values, list):
        return s(values)
    return "、".join(s(value.get("keyword", "")) if isinstance(value, dict) else s(value) for value in values)


def scope_note(counts: dict, provenance: dict | None = None) -> str:
    prefix = ""
    if provenance and "unique_domains" in provenance and "name_matches" in provenance:
        prefix = (f"原始名单包含 {int(provenance['unique_domains']):,} 个去重域名；"
                  f"名称规则匹配 {int(provenance['name_matches']):,} 个，AI 主观选取 {counts['total']} 个试跑。")
    return prefix + f"仅对选出的 {counts['total']} 个域名抓取首页并查询注册日期。这是有目的选样，不能据此推算总体机会比例。"


def render_html(records: list[dict], checks: list[dict], counts: dict, provenance: dict | None = None) -> str:
    rows = []
    for record in records:
        probe, review = record["probe"], record["review"]
        domain, decision = probe["domain"], review["decision"]
        registration = REGISTRATION.get(probe.get("registration_status"), "注册时间未知")
        date = s(probe.get("registration_date"))[:10]
        keyword_html = []
        for keyword in review.get("keywords", []):
            term = keyword["keyword"]
            keyword_html.append(f'''<div class="keyword"><strong>{esc(term)}</strong>
<span class="links">{a("全球90天", trends_url(term))} · {a("美国90天", trends_url(term, "US"))}</span>
<small>{esc(FIELDS[keyword["source_field"]])}：<q>{esc(keyword["evidence_quote"])}</q></small></div>''')
        expansions = expansion_text(review)
        if expansions:
            keyword_html.append(f'<p class="muted">推测扩展词（未验证）：{esc(expansions)}</p>')
        evidence = []
        for field in ("title", "description", "og_description", "h1"):
            evidence.append(f'<dt>{esc(FIELDS[field])}</dt><dd>{esc(field_text(probe, field)) or "—"}</dd>')
        if probe.get("fetch_error"):
            evidence.append(f'<dt>抓取说明</dt><dd>{esc(probe["fetch_error"])}</dd>')
        evidence.append(f'<dt>访问结果</dt><dd>{esc(FETCH.get(probe.get("fetch_status"), probe.get("fetch_status")))}'
                        f'{" · HTTP " + esc(probe["http_status"]) if probe.get("http_status") else ""}</dd>')
        if probe.get("final_url"):
            evidence.append(f'<dt>实际页面</dt><dd>{a(probe["final_url"], probe["final_url"])}</dd>')
        if probe.get("registration_source"):
            evidence.append(f'<dt>注册日期来源</dt><dd>{a("RDAP记录", probe["registration_source"])}</dd>')
        if probe.get("registration_error"):
            evidence.append(f'<dt>注册查询说明</dt><dd>{esc(probe["registration_error"])}</dd>')
        search_text = " ".join([domain, s(review.get("summary")), s(review.get("page_type")),
                                s(probe.get("title")), " ".join(k["keyword"] for k in review.get("keywords", []))])
        rows.append(f'''<tr data-decision="{esc(decision)}" data-search="{esc(search_text.casefold())}">
<td><div class="domain">{a(domain, "https://" + domain + "/")}</div>
<p class="muted">{esc(registration)}{(" · " + esc(date)) if date else ""}</p>
<details><summary>查看页面依据</summary><dl>{''.join(evidence)}</dl></details></td>
<td><span class="badge {esc(decision)}">{esc(DECISIONS[decision])}</span><p>{esc(review.get("summary"))}</p>
{f'<p class="muted">{esc(review["review_note"])}</p>' if review.get("review_note") else ''}</td>
<td>{''.join(keyword_html) or '<span class="muted">暂无可核验关键词</span>'}</td></tr>''')
    registration_line = " · ".join(f"{label} {counts['registration'].get(key, 0)}" for key, label in REGISTRATION.items())
    fetch_line = " · ".join(f"{FETCH.get(key, key)} {value}" for key, value in counts["fetch"].items())
    check_html = '<p class="muted">本报告尚未记录趋势核查结论。可点击关键词旁的链接手动检查。</p>'
    if checks:
        check_rows = []
        for check in checks:
            check_rows.append(f'''<li><strong>{a(check.get("keyword"), check.get("url"))}</strong>
<span class="muted">{esc(check.get("market"))} · {esc(check.get("timeframe"))}</span>
<p>{esc(check.get("observation"))}</p><p>结论：{esc(check.get("verdict"))}</p></li>''')
        check_html = '<ul class="checks">' + "".join(check_rows) + '</ul>'
    return '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>新注册域名关键词试跑 · 2026-09-26</title>
<style>
:root{color-scheme:light;font-family:system-ui,-apple-system,"PingFang SC",sans-serif;color:#172b35;background:#f5f7f8}
*{box-sizing:border-box}body{margin:0;line-height:1.65}main{max-width:1440px;margin:auto;padding:40px 28px 70px}
h1{font-size:30px;line-height:1.3;margin:0 0 12px}h2{font-size:20px;margin:28px 0 12px}p{margin:8px 0}
a{color:#09666a;text-underline-offset:3px;overflow-wrap:anywhere}.intro{max-width:900px}.muted,small{color:#5a6e78;font-size:13px}
.note{padding:12px 16px;background:#e9f3f1;border-left:3px solid #287b6d}.metrics{display:flex;gap:12px;flex-wrap:wrap;margin:24px 0 12px}
.metric{padding:14px 20px;background:white;border:1px solid #dfe6e9;min-width:155px}.metric b{display:block;font-size:28px}
.filters{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:24px 0 12px}input,select{font:inherit;padding:8px 10px;border:1px solid #bdccd2;background:white;border-radius:4px}input{width:min(400px,100%)}
.table-wrap{overflow-x:auto;background:white;border:1px solid #dfe6e9}table{border-collapse:collapse;width:100%;table-layout:fixed;min-width:850px}th{text-align:left;background:#eaf0f2;font-size:13px;letter-spacing:.03em}th,td{padding:17px 18px;vertical-align:top;border-bottom:1px solid #e2e9ec}th:nth-child(1){width:27%}th:nth-child(2){width:35%}th:nth-child(3){width:38%}
.domain{font-weight:650;overflow-wrap:anywhere}.badge{display:inline-block;padding:2px 9px;border-radius:4px;font-size:12px;background:#edf0f2;color:#46555c}.candidate{background:#daf0e8;color:#176748}.observe{background:#fff0d3;color:#775516}.exclude{background:#edf0f2;color:#54636a}
.keyword{margin-bottom:15px}.keyword:last-child{margin:0}.keyword strong{font-weight:650}.links{display:block;font-size:12px}.keyword small{display:block;margin-top:4px}q{quotes:"“" "”"}.checks{padding-left:22px;max-width:1000px}.checks li{margin:16px 0}
summary{cursor:pointer;color:#39616d;font-size:13px}details{margin-top:12px}dl{font-size:12px;overflow-wrap:anywhere}dt{font-weight:650;margin-top:10px}dd{margin:3px 0 0;color:#526771}footer{margin-top:26px;font-size:12px;color:#5a6e78}[hidden]{display:none!important}
@media(max-width:700px){main{padding:25px 14px}h1{font-size:25px}.metric{flex:1;min-width:130px;padding:10px 14px}}
</style></head><body><main>''' + f'''
<header><h1>新注册域名关键词试跑</h1><p class="muted">{RUN_DATE} · 首页证据与注册日期核验</p>
<p class="intro">从域名名称筛选样本，核对注册时间，再从页面标题、描述和正文提取有原文依据的关键词。这里记录的是站点主题与可能目标词，尚未证明它们已经带来搜索流量。</p>
<p class="intro">{esc(scope_note(counts, provenance))}</p>
<div class="note"><p>{esc(AUDIT_NOTE)}</p><p><a href="screening-audit-2026-09-26.md">全部筛选规则、反例与 52 个原始选择理由</a> · <a href="screening-audit-data-2026-09-26.json">逐级复算数据</a> · <a href="trends-audit-2026-09-26.md">Trends 查询条件与 90 天／一年对照</a> · <a href="evidence/pilot-before-audit-2026-09-26.html">修订前报告</a></p></div>
<p class="note">{esc(NOTE)}</p></header>
<div class="metrics"><div class="metric"><b>{counts['total']}</b>已探测域名</div>''' + "".join(
        f'<div class="metric"><b>{counts["decision"].get(key, 0)}</b>{esc(label)}</div>' for key, label in DECISIONS.items()) + f'''</div>
<p class="muted">注册核验：{esc(registration_line)}</p><p class="muted">页面获取：{esc(fetch_line)}</p>
<p class="muted">已核对 {counts['keyword_evidence_count']} 条关键词及其页面引文。</p>
<h2>趋势核查记录</h2><p class="muted">美国仅作为试跑示例，目标市场尚未确认。以下记录不等于已确认机会。</p>{check_html}
<h2>域名与关键词</h2><div class="filters"><label for="search">搜索</label><input id="search" type="search" placeholder="域名、关键词或判断说明" autocomplete="off">
<label for="decision">状态</label><select id="decision"><option value="all">全部</option>''' + "".join(
        f'<option value="{esc(key)}">{esc(label)}</option>' for key, label in DECISIONS.items()) + f'''</select>
<span id="shown" class="muted" aria-live="polite">显示 {counts['total']} 个域名</span></div>
<div class="table-wrap"><table><thead><tr><th>域名与注册时间</th><th>本轮判断</th><th>页面关键词与原文依据</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<footer>关键词引文已逐项核对为原始字段的子串。H1按空格连接后核对。趋势链接使用近90天范围；打开时所见日期会随时间变化。
<br>页面为静态抓取，无法据此排除网站另有动态内容。未取得页面、注册日期未知或没有工具词库数据，都不直接证明不存在需求。</footer>
</main>''' + '''<script>
const search=document.getElementById('search'), decision=document.getElementById('decision');
const rows=Array.from(document.querySelectorAll('tbody tr'));
function applyFilters(){const query=search.value.trim().toLocaleLowerCase(), choice=decision.value;let shown=0;
for(const row of rows){row.hidden=!(choice==='all'||row.dataset.decision===choice)||!row.dataset.search.includes(query);if(!row.hidden)shown++;}
document.getElementById('shown').textContent='显示 '+shown+' / '+rows.length+' 个域名';}
search.addEventListener('input',applyFilters);decision.addEventListener('change',applyFilters);
</script></body></html>'''


def render_markdown(records: list[dict], checks: list[dict], counts: dict, provenance: dict | None = None) -> str:
    lines = [f"# 新注册域名关键词试跑 · {RUN_DATE}", "", NOTE, "",
             "本报告记录页面主题与可能目标词，不证明网站已靠这些词获得流量。", "",
             scope_note(counts, provenance), "",
             AUDIT_NOTE, "",
             "[全部筛选规则及52个原始选择理由](screening-audit-2026-09-26.md) · [逐级复算数据](screening-audit-data-2026-09-26.json) · [Trends 查询对照](trends-audit-2026-09-26.md) · [修订前报告](evidence/pilot-before-audit-2026-09-26.md)", "",
             f"共探测 **{counts['total']}** 个域名。", "",
             "| 本轮判断 | 数量 |", "| --- | ---: |"]
    lines.extend(f"| {label} | {counts['decision'].get(key, 0)} |" for key, label in DECISIONS.items())
    lines += ["", "注册核验：" + "；".join(f"{label} {counts['registration'].get(key, 0)}" for key, label in REGISTRATION.items()) + "。",
              "", "页面获取：" + "；".join(f"{md(FETCH.get(key, key))} {value}" for key, value in counts["fetch"].items()) + "。",
              "", f"已核对 {counts['keyword_evidence_count']} 条关键词及其页面引文。",
              "", "## 趋势核查记录", "", "美国仅作为试跑示例，目标市场尚未确认。以下记录不等于已确认机会。", ""]
    if not checks:
        lines += ["尚未记录趋势核查结论。关键词旁提供全球、美国近90天的手动检查链接。", ""]
    for check in checks:
        lines += [f"- **{md_link(check.get('keyword'), check.get('url'))}** · {md(check.get('market'))} · {md(check.get('timeframe'))}",
                  f"  观察：{md(check.get('observation'))}；结论：{md(check.get('verdict'))}", ""]
    for record in records:
        probe, review = record["probe"], record["review"]
        domain = probe["domain"]
        lines += [f"## {md(domain)}", "",
                  f"**{DECISIONS[review['decision']]}** · {REGISTRATION.get(probe.get('registration_status'), '注册时间未知')}"
                  + (f" · {md(s(probe.get('registration_date'))[:10])}" if probe.get("registration_date") else ""), "",
                  md(review.get("summary")), ""]
        if review.get("review_note"):
            lines += [md(review["review_note"]), ""]
        if review.get("keywords"):
            for keyword in review["keywords"]:
                term = keyword["keyword"]
                lines += [f"- **{md(term)}** · {md_link('全球90天', trends_url(term))} · {md_link('美国90天', trends_url(term, 'US'))}",
                          f"  {FIELDS[keyword['source_field']]}原文：{md(keyword['evidence_quote'])}"]
            lines.append("")
        else:
            lines += ["暂无可核验关键词。", ""]
        if expansion_text(review):
            lines += ["推测扩展词（未验证）：" + md(expansion_text(review)), ""]
        lines += ["<details>", "<summary>页面依据</summary>", ""]
        for field in ("title", "description", "og_description", "h1"):
            lines.append(f"- {FIELDS[field]}：{md(field_text(probe, field)) or '—'}")
        if probe.get("fetch_error"):
            lines.append(f"- 抓取说明：{md(probe['fetch_error'])}")
        lines.append(f"- 页面：{md_link(probe.get('final_url') or domain, probe.get('final_url'))}")
        if probe.get("registration_source"):
            lines.append(f"- 注册日期来源：{md_link('RDAP记录', probe['registration_source'])}")
        if probe.get("registration_error"):
            lines.append(f"- 注册查询说明：{md(probe['registration_error'])}")
        lines += ["", "</details>", ""]
    lines += ["关键词引文已逐条核对；H1按空格连接后核对。未渲染网页原始HTML或完整正文。",
              "趋势链接使用相对日期范围，打开时所见日期会随时间变化。", ""]
    return "\n".join(lines)


def main() -> int:
    try:
        records, checks = load_records()
        counts = counts_for(records)
        provenance_path = DATA / "provenance.json"
        provenance = json.loads(provenance_path.read_text(encoding="utf-8")) if provenance_path.exists() else None
        if provenance is not None and not isinstance(provenance, dict):
            raise ValueError("provenance.json must contain an object")
        html_report = render_html(records, checks, counts, provenance)
        markdown_report = render_markdown(records, checks, counts, provenance)
        OUTPUT.mkdir(parents=True, exist_ok=True)
        base = OUTPUT / f"pilot-{RUN_DATE}"
        base.with_suffix(".html").write_text(html_report, encoding="utf-8")
        base.with_suffix(".md").write_text(markdown_report, encoding="utf-8")
        print(json.dumps({"output_html": str(base.with_suffix('.html')), "output_md": str(base.with_suffix('.md')),
                          "counts": counts, "trends_checks": len(checks)}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
