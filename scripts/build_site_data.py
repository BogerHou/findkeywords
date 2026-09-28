#!/usr/bin/env python3
"""Build the review site's read-only snapshot from saved research evidence."""

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN_DATE = "2026-09-26"
RUN = ROOT / "data" / "runs" / RUN_DATE


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def status_for(keyword):
    # These are saved editorial judgments, not automated rankings or scores.
    if keyword == "sprite sheet maker":
        return "review", "继续核验", "当前 AI 分析判断：三个公开基准试算为千级月均量级，可继续核验搜索结果与竞争；尚未证明新词、当前增长或低竞争。"
    if keyword == "GIF to sprite sheet":
        return "review", "继续核验", "当前 AI 分析判断：可保留为精灵图相关任务；近 90 天仅 7 个完整日非零，年度也较稀疏，不输出绝对搜索量。"
    if keyword in {"agent governance", "AI agent governance", "agent observability"}:
        return "cooling", "高峰后回落", "当前 AI 分析判断：年度同图峰值在 2026-06-07 当周，最近 4 个完整周低于此前 13 周；暂不按最近起势推进。不是机会评分。"
    if keyword == "agent permission matrix":
        return "insufficient", "证据不足", "当前 AI 分析判断：近 90 天只有一个非零日，不能据孤峰证明持续需求或估算搜索规模。不是零搜索量判定。"
    if keyword in {"AI Governance Toolkit", "step-level agent evaluation", "AI sprite sheet generator", "paper-reel load restraint", "seed starting capacity planner"}:
        return "insufficient", "证据不足", "当前 AI 分析判断：窄词组复查的主图提示数据不足，暂缺足够需求证据；不等于实际搜索量为零。"
    return "pending", "待进一步判断", "当前 AI 分析判断：已查询 Trends，尚未形成机会结论；还需结合走势、可比规模与搜索竞争核验。不是自动评分。"


def metrics_for(capture, keyword):
    if capture is None or capture.get("status") != "chart":
        return None
    series = capture["series"][capture["terms"].index(keyword)]
    # The last day was still in progress when captured. Preserve it in captures,
    # but exclude it from this summary, as in the round-two report.
    complete = series[:-1]
    if not complete:
        return None
    average = lambda values: sum(values) / len(values) if values else None
    return {
        "mean": average(complete),
        "nonzero": sum(value > 0 for value in complete),
        "total": len(complete),
        "recent14": average(complete[-14:]),
        "previous14": average(complete[-28:-14]),
    }


def build():
    candidates = read_json(RUN / "round2-candidates.json")
    selected = read_json(RUN / "selected_domains.json")
    probes = read_json(RUN / "probes.json")
    reviews = read_json(RUN / "reviews_tools.json") + read_json(RUN / "reviews_novel.json")
    capture_document = read_json(RUN / "round2-browser-captures.json")
    captures = capture_document["captures"]
    anchors = read_json(RUN / "round2-anchor-research.json")
    estimates = read_json(RUN / "round2-estimates.json")
    audit = read_json(ROOT / "reports" / f"screening-audit-data-{RUN_DATE}.json")
    provenance = read_json(RUN / "provenance.json")
    assessment = read_json(RUN / "round2-assessment.json")
    matches = read_json(RUN / "name_matches.json")

    selected_by_domain = {row["domain"]: row for row in selected}
    probes_by_domain = {row["domain"]: row for row in probes}
    reviews_by_domain = {row["domain"]: row for row in reviews}
    candidate_reviews = [row for row in reviews if row["decision"] == "candidate"]
    expected_keywords = Counter(
        (review["domain"], keyword["keyword"])
        for review in candidate_reviews for keyword in review.get("keywords", [])
    )
    require(set(selected_by_domain) == set(probes_by_domain) == set(reviews_by_domain), "Selected, probed and reviewed domain coverage differs")
    require(len(selected_by_domain) == len(selected) == 52, "Expected 52 unique selected domains")
    require(len(candidates["candidates"]) == 32, "Expected 32 original candidate keywords")
    require(Counter((c["source_domain"], c["original_keyword"]) for c in candidates["candidates"]) == expected_keywords, "Candidate keywords do not exactly match the original 16 reviews")
    require(len(captures) == len({c["id"] for c in captures}) == 12, "Expected 12 unique comparison captures")
    for capture in captures:
        if capture["status"] == "chart":
            require(len(capture["terms"]) == len(capture["series"]), f"Series count mismatch: {capture['id']}")
            require(all(len(s) == len(capture["dates"]) for s in capture["series"]), f"Date count mismatch: {capture['id']}")

    keywords = []
    for candidate in candidates["candidates"]:
        keyword = candidate["original_keyword"]
        related_captures = [c for c in captures if keyword in c["terms"]]
        primary = next((c for c in related_captures if c["id"].endswith("-90d")), None)
        require(primary is not None, f"No 90-day capture for {keyword}")
        rows = [row for row in estimates["rows"] if row["keyword"] == keyword]
        values = [row["conditional_monthly_estimate"] for row in rows]
        status, label, reason = status_for(keyword)
        keywords.append({
            "id": candidate["id"],
            "keyword": keyword,
            "domain": candidate["source_domain"],
            "sourceField": candidate["source_field"],
            "evidenceQuote": candidate["evidence_quote"],
            "sourceSummary": candidate["source_summary"],
            "groupId": candidate["comparison_group_id"],
            "group": candidate["comparison_group"],
            "classification": candidate["name_level_hypotheses"],
            "status": status,
            "statusLabel": label,
            "statusReason": reason,
            "primaryCaptureId": primary["id"],
            "captureIds": [c["id"] for c in related_captures],
            "estimates": rows,
            "estimateRange": {"min": min(values), "max": max(values)} if values else None,
            "metrics": metrics_for(primary, keyword),
        })

    domains = []
    for source in selected:
        domain = source["domain"]
        probe, review = probes_by_domain[domain], reviews_by_domain[domain]
        domains.append({
            "domain": domain,
            "sourceDate": source["source_date"],
            "selectionGroup": source["selection_group"],
            "selectionReason": source["selection_reason"],
            "nameMatches": source["name_matches"],
            "registrationStatus": probe.get("registration_status"),
            "registrationDate": probe.get("registration_date"),
            "registrationSource": probe.get("registration_source"),
            "fetchStatus": probe.get("fetch_status"),
            "finalUrl": probe.get("final_url"),
            "title": probe.get("title"),
            "description": probe.get("description"),
            "h1": probe.get("h1", []),
            "decision": review["decision"],
            "summary": review["summary"],
            "keywords": [k["keyword"] for k in review.get("keywords", [])],
        })

    funnel = audit["funnel"]
    stages = [
        ("原始域名", "unique_domains", "两份 WhoisDS 名单合并去重；尚未逐个检查网站，也不是 SSL 证书入口。"),
        ("命中 43 个词根", "at_least_one_substring", "域名第一个标签包含至少一个预设字符串，没有语义判断。"),
        ("名称少于 34 字符", "after_label_length_lt_34", "在命中词根的域名中按名称长度筛选。"),
        ("无连续三个数字", "after_no_three_consecutive_digits", "排除包含连续三个数字的名称，仍可包含其他数字。"),
    ]
    screening_funnel = []
    previous = funnel["raw_rows"]
    for label, field, reason in stages:
        count = funnel[field]
        screening_funnel.append({"label": label, "count": count, "removed": previous - count, "reason": reason})
        previous = count
    screening_funnel.append({"label": "AI 主观选样", "count": len(domains), "removed": previous - len(domains), "reason": "40 个任务名称＋12 个概念线索；没有统一评分或完整排序，未入选不代表无价值。"})

    resources_spec = [
        ("第二轮完整报告", "32 个词、12 组对比、5 个词的条件性量级试算。", f"reports/round2-{RUN_DATE}.html", "report"),
        ("第一轮域名报告", "52 个域名的注册查询、网页内容与原始关键词依据。", f"reports/pilot-{RUN_DATE}.html", "report"),
        ("筛选规则审计", "精确规则、数量、误筛漏筛例子、52 个原始入选理由。", f"reports/screening-audit-{RUN_DATE}.md", "method"),
        ("Trends 差异核验", "Agent Permission Matrix 的条件差异与证据限制。", f"reports/trends-audit-{RUN_DATE}.md", "method"),
        ("完整 Trends 数列", "浏览器 DOM 表格转录；保留 12 次查询的时间、条件与数列。", f"data/runs/{RUN_DATE}/round2-browser-captures.json", "data"),
        ("量级试算与敏感性", "逐词、逐参照词的计算结果及基准交叉校验。", f"data/runs/{RUN_DATE}/round2-estimates.json", "data"),
        ("公开基准来源", "Semrush 公开数值、报告月份、核验结果与未解决口径。", f"data/runs/{RUN_DATE}/round2-anchor-research.json", "data"),
        ("原始域名探测记录", "全部 52 个域名的页面摘录、重定向与 RDAP 来源。", f"data/runs/{RUN_DATE}/probes.json", "data"),
        ("名称筛选审计数据", "精确数量、词根、批次、例子及文件校验值。", f"reports/screening-audit-data-{RUN_DATE}.json", "data"),
        ("原始选样记录", "全部 52 个入选域名和当时保存的原始理由。", f"data/runs/{RUN_DATE}/selected_domains.json", "data"),
        ("1,210 个词根命中域名", "机械筛选的完整输出，不代表有意义或已确认需求。", f"data/runs/{RUN_DATE}/name_matches.json", "data"),
    ]
    resources = []
    for title, description, path, kind in resources_spec:
        require((ROOT / path).is_file(), f"Missing resource: {path}")
        resources.append({"title": title, "description": description, "path": "../" + path, "type": kind})

    result = {
        "meta": {
            "title": "FindKeywords",
            "runDate": RUN_DATE,
            "builtAt": datetime.now(timezone.utc).isoformat(),
            "schemaVersion": 1,
            "mode": "保存的研究快照；不会自动抓取或更新外部网站",
            "market": "美国",
            "channel": "网页搜索",
            "filters": capture_document["filters"],
            "captureMethod": capture_document["method"],
            "captureLimitations": capture_document["limitations"],
            "metricsNote": "只汇总该词首次 90 天对比，排除最后一个未完成日；recent14、previous14 是相邻两个 14 日段的算术均值。同图内可比较，不可跨图比较指数高低。",
            "estimateRangeNote": "不同公开基准的情景范围；不是置信区间，不是当前月实测或网站流量预测。",
            "statusNote": "状态是本轮 AI 分析判断，不是评分；待判断不代表无数据。",
            "sourceNote": "原始入口为 WhoisDS 新域名名单，尚未接入 SSL 证书日志。",
            "registrationCounts": dict(Counter(d["registrationStatus"] for d in domains)),
            "statusCounts": dict(Counter(k["status"] for k in keywords)),
        },
        "summary": {
            "rawDomains": sum(s["count"] for s in provenance["sources"]),
            "nameMatches": len(matches),
            "selectedDomains": len(domains),
            "candidateDomains": len(candidate_reviews),
            "keywords": len(keywords),
            "comparisons": len(captures),
            "estimatedKeywords": len({r["keyword"] for r in estimates["rows"]}),
        },
        "keywords": keywords,
        "domains": domains,
        "captures": captures,
        "anchors": anchors["anchors"],
        "calibration": {
            "method": estimates["method"],
            "limitations": estimates["limitations"],
            "anchorCrosscheck": estimates["anchor_crosscheck"],
            "agentRecentComparison": estimates["agent_recent_comparison"],
        },
        "screening": {
            "terms": audit["actual_name_rule"]["terms"],
            "funnel": screening_funnel,
            "batches": audit["batches"],
            "examples": audit["examples"],
        },
        "assessment": assessment,
        "resources": resources,
    }
    expected = {"rawDomains": 140000, "nameMatches": 1210, "selectedDomains": 52, "candidateDomains": 16, "keywords": 32, "comparisons": 12, "estimatedKeywords": 5}
    require(result["summary"] == expected, f"Unexpected summary: {result['summary']}")
    require(result["meta"]["statusCounts"] == {"review": 2, "cooling": 3, "insufficient": 6, "pending": 21}, "Unexpected editorial status mapping")
    return result


def main():
    data = build()
    output = ROOT / "site"
    output.mkdir(exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
    # Keep the JS assignment valid for older JS parsers and safe if copied inline.
    script_json = text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029").replace("</", "<\\/")
    (output / "data.json").write_text(text + "\n", encoding="utf-8")
    (output / "data.js").write_text("window.FINDKEYWORDS_DATA = " + script_json + ";\n", encoding="utf-8")
    require(read_json(output / "data.json") == data, "JSON output round trip failed")
    require(json.loads(script_json) == data, "JS payload differs from JSON payload")
    print("已生成网站数据：32 个关键词，52 个域名，12 组对比，5 个词的量级试算。")


if __name__ == "__main__":
    main()
