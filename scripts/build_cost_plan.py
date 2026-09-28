#!/usr/bin/env python3
"""Offline request-budget plan. Rebuildable from the portable site snapshots."""
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def refresh_cache(path, domains):
    sources = [ROOT / "data/runs/2026-09-26/probes.json",
               ROOT / "data/runs/2026-09-26-month/probes.jsonl",
               ROOT / "data/runs/2026-09-26-tld/probes.jsonl"]
    records, provenance = {}, []
    for source in sources:
        if not source.exists():
            raise ValueError(f"Missing local evidence {source}; use the published cache index without --refresh-cache")
        raw = source.read_text()
        rows = json.loads(raw) if source.suffix == ".json" else [json.loads(s) for s in raw.splitlines() if s.strip()]
        provenance.append({"path": str(source.relative_to(ROOT)), "sha256": sha(source), "records": len(rows)})
        for row in rows:
            domain = row["domain"]
            if domain not in domains:
                continue
            evidence = {"domain": domain, "fetchedAt": row.get("fetched_at"),
                        "source": str(source.relative_to(ROOT)), "fetchStatus": row.get("fetch_status"),
                        "note": "曾经检查的记录；不代表现在可访问或通过当前规则。先复用旧证据，不立即重抓。"}
            if domain not in records or (evidence["fetchedAt"] or "") > (records[domain]["fetchedAt"] or ""):
                records[domain] = evidence
    save(path, {"sources": provenance, "records": sorted(records.values(), key=lambda r: r["domain"])})


def merge_results(cache_doc, paths):
    records = {r["domain"]: r for r in cache_doc["records"]}
    sources = list(cache_doc["sources"])
    for path in paths:
        rows = [json.loads(s) for s in path.read_text().splitlines() if s.strip()]
        if rows and rows[-1].get("stop_batch"):
            raise ValueError("The batch paused after a block/failure. Inspect it before preparing a new request batch.")
        for row in rows:
            captured = row["checked_at"]
            datetime.fromisoformat(captured.replace("Z", "+00:00"))
            if row["domain"] not in records or captured > (records[row["domain"]].get("fetchedAt") or ""):
                records[row["domain"]] = {"domain": row["domain"], "fetchedAt": captured,
                                           "source": "local-results/" + path.name,
                                           "fetchStatus": row["reason"], "note": "已在异机检查；本轮先复用，未确认新词机会。"}
        checksum = sha(path)
        if not any(r.get("sha256") == checksum for r in sources):
            sources.append({"path": "local-results/" + path.name, "sha256": checksum, "records": len(rows)})
    return {"sources": sources, "records": sorted(records.values(), key=lambda r: r["domain"])}


def reasons(row, config):
    name = row["domain"].split(".")[0]
    broad = set(config["broadRoots"])
    issues = []
    if set(row["roots"]) <= broad:
        issues.append("broad_roots_only")
    if not any(m["root"] not in broad and (m["start"] == 0 or m["end"] == len(name)) for m in row["matches"]):
        issues.append("no_specific_root_at_name_edge")
    if len(name) > config["maxPriorityNameLength"]:
        issues.append("long_name")
    if sum(c.isdigit() for c in name) > config["maxPriorityDigits"]:
        issues.append("many_digits")
    if name.count("-") > config["maxPriorityHyphens"] or "--" in name:
        issues.append("many_hyphens")
    if re.search(r"(.)\1{3}", name):
        issues.append("repeated_characters")
    return issues


def round_robin(rows, roots, count, seed):
    ordered = sorted(rows, key=lambda r: hashlib.sha256((seed + "\0" + r["domain"]).encode()).hexdigest())
    # Materialize each root's pool to avoid late-bound generator closures.
    pools = {root: iter([r for r in ordered if root in r["roots"]]) for root in roots}
    picked, seen = [], set()
    while len(picked) < count:
        before = len(picked)
        for root, pool in pools.items():
            row = next((r for r in pool if r["domain"] not in seen), None)
            if row:
                picked.append({**row, "sampling_root": root})
                seen.add(row["domain"])
            if len(picked) == count:
                break
        if len(picked) == before:
            break
    return picked


def build(args):
    source = ROOT / "site/roots-data.json"
    config_path = ROOT / "scripts/data/cost-policy.json"
    cache_path = ROOT / "site/probe-cache-index.json"
    data, config = json.loads(source.read_text()), json.loads(config_path.read_text())
    rows = data["domains"]
    if args.refresh_cache:
        refresh_cache(cache_path, {r["domain"] for r in rows})
    cache_doc = json.loads(cache_path.read_text())
    if args.reuse_results:
        cache_doc = merge_results(cache_doc, args.reuse_results)
        save(cache_path, cache_doc)
    cutoff = args.as_of - timedelta(days=config["cacheDays"])
    cached = {}
    for r in cache_doc["records"]:
        if r["fetchedAt"]:
            day = datetime.fromisoformat(r["fetchedAt"].replace("Z", "+00:00")).date()
            if cutoff <= day <= args.as_of:
                cached[r["domain"]] = r
    root_ids = [r["id"] for r in data["roots"]]
    families, audit = {}, []
    broad_count = sum(set(r["roots"]) <= set(config["broadRoots"]) for r in rows)
    for row in rows:
        why = reasons(row, config)
        item = {**row, "priorityReasons": why, "lane": "exploration" if why else "priority"}
        if row["domain"] in cached:
            audit.append({**item, "action": "reuse_historical", "cached": cached[row["domain"]]})
        else:
            families.setdefault(row["domain"].split(".")[0], []).append(item)
    reps = []
    for family in families.values():
        family.sort(key=lambda r: hashlib.sha256((config["seed"] + "\0" + r["domain"]).encode()).hexdigest())
        representative = family[0]
        representative["sameNameAlternatives"] = [r["domain"] for r in family[1:]]
        reps.append(representative)
        for item in family:
            audit.append({**item, "action": "representative" if item is representative else "same_name_deferred", "representative": representative["domain"]})
    priority = [r for r in reps if r["lane"] == "priority"]
    exploration = [r for r in reps if r["lane"] == "exploration"]
    picked_p = round_robin(priority, root_ids, config["prioritySlots"], config["seed"])
    picked_e = round_robin(exploration, root_ids, config["explorationSlots"], config["seed"])
    picked = []
    # Spread exploration across the run so an early stop does not lose it all.
    for offset in range(0, max(len(picked_p), len(picked_e) * 4), 4):
        picked.extend(picked_p[offset:offset + 4])
        picked.extend(picked_e[offset // 4:offset // 4 + 1])
    summary = {"inputDomains": len(rows), "broadOnlyDomains": broad_count,
               "reuseHistorical": sum(r["domain"] in cached for r in rows),
               "unprobedNow": sum(r["domain"] not in cached for r in rows),
               "sameNameRepresentatives": len(reps),
               "sameNameDeferred": sum(len(r["sameNameAlternatives"]) for r in reps),
               "priorityPool": len(priority), "explorationPool": len(exploration),
               "queued": len(picked), "priorityQueued": len(picked_p), "explorationQueued": len(picked_e),
               "newRequests": 0}
    inputs = {"domains": {"path": "site/roots-data.json", "sha256": sha(source)},
              "cache": {"path": "site/probe-cache-index.json", "sha256": sha(cache_path)},
              "config": {"path": "scripts/data/cost-policy.json", "sha256": sha(config_path)}}
    meta = {"asOf": str(args.as_of), "status": "prepared_not_executed", "version": config["version"],
            "sourceWindow": data["meta"]["sourceWindow"], "inputs": inputs}
    queue = {"meta": meta, "selection": "80 priority + 20 exploration; per-lane root round-robin in fixed SHA256 order; one representative per exact first-label spelling; historical cache excluded for 7 days", "domains": picked}
    plan = {"meta": meta, "summary": summary, "config": config, "queue": picked,
            "limits": ["仅调整请求优先级，没有证明剩余域名无价值。", "同名不同后缀不代表同一个网站，仅为本轮节约预算暂选一个。", "优先池不是有效网站数；100 是试跑预算，不是只有100个合格。", "旧记录不证明现在可用；过期后可重新核验。", "不要求词典收录，保留新造词探索预算。"]}
    save(ROOT / "site/cost-plan.json", plan)
    (ROOT / "site/cost-plan.js").write_text("window.FINDKEYWORDS_COST_PLAN=" + json.dumps(plan, ensure_ascii=False, separators=(",", ":")) + ";\n")
    save(ROOT / "site/prescreen-queue.json", queue)
    save(ROOT / f"data/runs/{args.as_of}-cost-plan/audit.json", {"meta": meta, "summary": summary, "domains": audit})
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-cache", action="store_true", help="Read local historical probe files; never network")
    parser.add_argument("--reuse-results", action="append", type=Path, default=[], help="Merge a completed local results.jsonl into the cache; offline")
    parser.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    build(parser.parse_args())
