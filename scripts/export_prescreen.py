#!/usr/bin/env python3
"""Export saved page fields and request outcomes without downloading anything."""
import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path


def export(batch):
    raw = (batch / "results.jsonl").read_bytes()
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    summary = json.loads((batch / "summary.json").read_text())
    run = json.loads((batch / "run.json").read_text())
    if len(rows) != summary["completed"] or not rows:
        raise ValueError("Cannot export an empty or inconsistent completed batch")
    body_bytes, compact = 0, []
    for row in rows:
        for request in row["requests"]:
            if request.get("body_file"):
                evidence = (batch / request["body_file"]).resolve()
                evidence.relative_to(batch.resolve() / "evidence")
                body_bytes += len(gzip.decompress(evidence.read_bytes()))
        item = {k: row[k] for k in ("domain", "checked_at", "decision", "reason", "policy_version")}
        item["source"] = {"lane": row["source"].get("lane")}
        item["incomplete_html"] = row.get("incomplete_html", False)
        page = row.get("page") or row.get("page_prefix")
        if page:
            item["page"] = {k: page.get(k) for k in ("title", "description", "h1")}
        item["requests"] = [{k: q.get(k) for k in ("url", "stage", "http_status", "status", "request_count", "error_kind")}
                            for q in row["requests"]]
        compact.append(item)
    result = {
        "rows": compact, "summary": summary, "run": run,
        "results_sha256": hashlib.sha256(raw).hexdigest(),
        "metrics": {
            "saved_decoded_response_bytes": body_bytes,
            "response_bytes_note": "Saved decoded bodies only; excludes headers, DNS, TLS and bytes read beyond cutoff",
            "first_checked_at": rows[0]["checked_at"], "last_checked_at": rows[-1]["checked_at"],
        },
    }
    content = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()
    (batch / "export.json").write_bytes(content)
    (batch / "export.b64").write_text(base64.b64encode(gzip.compress(content, mtime=0)).decode())
    print(json.dumps({"export_sha256": hashlib.sha256(content).hexdigest(), "summary": summary,
                      "metrics": result["metrics"]}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    export(parser.parse_args().input)
