#!/usr/bin/env python3
"""Build an offline, auditable website snapshot from one completed prescreen batch."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(batch, site, label):
    if batch.is_file():
        # A compact export carries page fields and per-request status. Full raw
        # records and response bodies remain on the capture host, with its hash.
        exported = json.loads(batch.read_text())
        rows, summary, run = exported["rows"], exported["summary"], exported["run"]
        source_hash = exported["results_sha256"]
        metrics = exported.get("metrics", {})
    else:
        raw = (batch / "results.jsonl").read_bytes()
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
        summary = json.loads((batch / "summary.json").read_text())
        run = json.loads((batch / "run.json").read_text())
        source_hash, metrics = hashlib.sha256(raw).hexdigest(), {}
    domains = [r["domain"] for r in rows]
    if len(domains) != len(set(domains)) or len(rows) != summary["completed"]:
        raise ValueError("Duplicate domains or summary/record count mismatch")
    if dict(Counter(r["decision"] for r in rows)) != summary["decisions"]:
        raise ValueError("Summary decisions do not match saved records")
    if summary["completed"] + summary["pending"] != summary["queued"]:
        raise ValueError("Invalid completion counts")
    if any(r["policy_version"] != run["policy"]["version"] for r in rows):
        raise ValueError("Mixed policies in one batch")
    review_path = site / "prescreen-review.json"
    review = json.loads(review_path.read_text()) if review_path.exists() else None
    if review and review["resultsSha256"] != source_hash:
        raise ValueError("Content review belongs to another run; archive it before building a new batch")
    reviews = {r["domain"]: r for r in review["items"]} if review else {}
    public_rows = []
    requests, unknown = 0, 0
    for row in rows:
        for request in row["requests"]:
            count = request.get("request_count")
            if count is None:
                unknown += 1
            else:
                requests += count
        public_rows.append({
            "domain": row["domain"], "checkedAt": row["checked_at"],
            "decision": row["decision"], "reason": row["reason"],
            "lane": row["source"].get("lane"),
            "page": row.get("page") or row.get("page_prefix"),
            "incomplete": bool(row.get("incomplete_html")),
            "review": reviews.get(row["domain"]),
            "requests": [{k: r.get(k) for k in ("url", "stage", "http_status", "status", "error_kind", "body_sha256", "retry_after")}
                         for r in row["requests"]],
        })
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(), "label": label,
        "summary": summary, "policy": run["policy"],
        "queueSha256": run["queue_sha256"],
        "resultsSha256": source_hash, "metrics": metrics,
        "knownHttpAttempts": requests, "unknownAttemptRecords": unknown,
        "rows": public_rows, "contentReview": review,
        "note": "网页技术预筛；自动分类仍需内容复核。未核实首次上线日期，未查询 Google Trends，不代表已发现增长关键词。",
    }
    site.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    (site / "prescreen-results.json").write_text(text)
    (site / "prescreen-results.js").write_text("window.FINDKEYWORDS_PRESCREEN_RESULTS = " + text.rstrip() + ";\n")
    print(json.dumps({"completed": len(rows), "decisions": summary["decisions"], "network_requests": 0}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--site", type=Path, default=ROOT / "site")
    parser.add_argument("--label", default="AWS Lightsail · 首批100域名")
    args = parser.parse_args()
    build(args.input, args.site, args.label)
