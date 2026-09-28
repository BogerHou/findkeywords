#!/usr/bin/env python3
"""Independent suffix-group/name screen, with auditable deterministic sampling.

No network calls. Name spelling is a clue, not evidence of meaning or a new site.
"""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import heapq
import json
from pathlib import Path
import re
import sqlite3
import sys

from screen_names import TERMS
from screen_month import EXTRA_TERMS


ROOT = Path(__file__).resolve().parents[1]
LEXICON = ROOT / "scripts/data/name-lexicon-web2.txt"
LEXICON_SOURCE = ROOT / "scripts/data/name-lexicon-web2-source.json"
VERSION = "tld-readable-names-v1"
DEFAULT_SEED = "findkeywords-tld-readable-v1"
GROUPS_FILE = ROOT / "scripts/data/tld-name-groups.json"
PATH_LABELS = {
    "dictionary_segments": "通用词典完整分词",
    "readable_coinage": "可读字符形态探索",
    "short_abbreviation": "短缩写探索",
    "alphanumeric_exploration": "少量数字名称探索",
}
EXCLUSION_LABELS = {
    "encoded_idn": "IDN 编码名称暂未做多语言分词，保留在旧完整输入中",
    "name_length_outside_2_32": "名称长度不在 2–32 字符",
    "too_many_hyphens": "超过两个连字符或存在连续连字符",
    "numeric_only": "名称全部为数字",
    "repeated_character_run": "存在至少四个连续相同字符",
    "too_many_digits": "数字超过两位或占比超过40%",
    "alphanumeric_not_short_enough": "带数字名称超过16字符",
    "alphanumeric_no_name_clue": "带数字名称的字母部分未达到词典/可读/短缩写线索",
    "no_dictionary_or_readability_clue": "未取得完整词典分词或本轮可读字符形态线索",
}


def checksum(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_hash(domain, seed):
    return hashlib.sha256((seed + "\0" + domain).encode()).hexdigest()


def segmentation(value, words):
    """Fewest full dictionary words, then lexical token order; max five words."""
    if value in words:
        return (value,)
    if len(value) < 6:
        return None
    best = {0: ()}
    for start in range(len(value) - 2):
        prefix = best.get(start)
        if prefix is None or len(prefix) >= 5:
            continue
        for end in range(start + 3, len(value) + 1):
            piece = value[start:end]
            if piece not in words:
                continue
            proposal = prefix + (piece,)
            previous = best.get(end)
            if previous is None or (len(proposal), proposal) < (len(previous), previous):
                best[end] = proposal
    return best.get(len(value))


def lexical_parts(value, words):
    parts = []
    for chunk in value.split("-"):
        tokens = segmentation(chunk, words)
        if tokens is None:
            return None
        parts.extend(tokens)
    return tuple(parts) if len(parts) <= 5 else None


def readable(value):
    """Transparent permissive spelling shape; deliberately not a language model."""
    bare = value.replace("-", "")
    if not 5 <= len(bare) <= 20 or not bare.isalpha():
        return False
    vowel_count = sum(c in "aeiouy" for c in bare)
    return (
        .20 <= vowel_count / len(bare) <= .70
        and not re.search(r"[^aeiouy]{5}|[aeiouy]{4}", bare)
        and all(len(part) >= 2 for part in value.split("-"))
    )


def classify(domain, words):
    """Return (path, exclusion_reason, lexical_segments); never uses task roots."""
    labels = domain.split(".")
    name = labels[0]
    if name.startswith("xn--"):
        return None, "encoded_idn", ()
    if not 2 <= len(name) <= 32:
        return None, "name_length_outside_2_32", ()
    if name.count("-") > 2 or "--" in name:
        return None, "too_many_hyphens", ()
    if name.replace("-", "").isdigit():
        return None, "numeric_only", ()
    if re.search(r"(.)\1{3}", name):
        return None, "repeated_character_run", ()
    digits = sum(c.isdigit() for c in name)
    if digits:
        if digits > 2 or digits / len(name.replace("-", "")) > .40:
            return None, "too_many_digits", ()
        if len(name) > 16:
            return None, "alphanumeric_not_short_enough", ()
        letters = re.sub("[0-9-]", "", name)
        tokens = lexical_parts(letters, words)
        if tokens or readable(letters) or 2 <= len(letters) <= 5:
            return "alphanumeric_exploration", None, tokens or ()
        return None, "alphanumeric_no_name_clue", ()
    tokens = lexical_parts(name, words)
    if tokens:
        return "dictionary_segments", None, tokens
    if "-" not in name and 2 <= len(name) <= 5:
        return "short_abbreviation", None, ()
    if readable(name):
        return "readable_coinage", None, ()
    return None, "no_dictionary_or_readability_clue", ()


def quotas(limit, counts, groups):
    shares = [(g['id'], g['percent']) for g in groups]
    initial = {group: limit * percent // 100 for group, percent in shares}
    order = sorted(range(len(shares)), key=lambda i: (-(limit * shares[i][1] % 100), i))
    for i in order[:limit - sum(initial.values())]:
        initial[shares[i][0]] += 1
    final = {group: min(initial[group], counts[group]) for group, _ in shares}
    missing = min(limit, sum(counts.values())) - sum(final.values())
    while missing:
        for group, _ in shares:
            if final[group] < counts[group]:
                final[group] += 1
                missing -= 1
                if missing == 0:
                    break
    return initial, final


def load_groups(path):
    doc = json.loads(path.read_text(encoding='utf-8'))
    groups = doc['groups']
    ids = [g['id'] for g in groups]
    suffixes = [t for g in groups for t in g['suffixes']]
    if len(ids) != len(set(ids)) or len(suffixes) != len(set(suffixes)):
        raise ValueError('Group IDs and explicit suffix assignments must be unique')
    if not all(isinstance(g['percent'], int) and 0 <= g['percent'] <= 100 for g in groups) or sum(g['percent'] for g in groups) != 100:
        raise ValueError('Group integer shares must total 100')
    if len([g for g in groups if g.get('fallback')]) != 1:
        raise ValueError('Exactly one group must have fallback: true')
    return groups


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_excluded(paths):
    seen, info = set(), []
    for path in paths:
        count = 0
        with path.open(encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                try:
                    domain = json.loads(line)["domain"]
                except (ValueError, KeyError, TypeError) as exc:
                    raise ValueError(f"Invalid exclusion record {path}:{n}: {exc}")
                seen.add(domain.lower().rstrip("."))
                count += 1
        info.append({"path": str(path.resolve()), "records": count, "sha256": checksum(path)})
    return seen, info


def rules(seed, limit, lexicon_info, groups):
    return {
        "version": VERSION,
        "purpose": "独立于行业词根表，按后缀与可复算名称线索建立新的首页探测样本。",
        "suffix_groups": groups,
        "channel_rules": [{"id": g['id'], "condition": "后缀在" + ("剩余全部合规输入后缀" if g.get('fallback') else ', '.join('.'+t for t in g['suffixes'])) + "，且通过相同的名称线索规则；没有行业词根要求。"} for g in groups],
        "suffix_rationale": "人为探索预算，默认传统45%、产品技术25%、其他常见20%、其余后缀10%；可用--groups-file调整。未查询注册/续费价格；后缀不证明权威、内容质量、注册者投入或搜索价值。",
        "name_unit": "域名第一个标签用于名称，最后一个标签用于后缀组；未用公共后缀表推断可注册根域名，例如 foo.co.uk 按 foo 与 uk 处理。输入已在旧流程完成格式校验与全局去重；未另查IANA后缀清单。",
        "no_task_root_requirement": True,
        "ordered_exclusions": EXCLUSION_LABELS,
        "paths_in_priority_order": [
            {"id": "alphanumeric_exploration", "condition": "带数字名称优先独立分类：长度2–16，数字≤2且占去连字符长度≤40%；去数字与连字符后的字母部分可完整分词，或满足可读模式，或长度2–5。保留 b2b 等缩写/少量数字，不承诺数字的含义。"},
            {"id": "dictionary_segments", "condition": "无数字名称按每个连字符分块，每块必须全部由词典中长度3–32的词覆盖；总计最多5词。优先词数最少，再按词元字典序确定唯一切分。没有行业或关键词白名单。"},
            {"id": "short_abbreviation", "condition": "词典无法完整覆盖时，保留2–5个纯字母且无连字符的短名称；不要求元音。缩写与短随机串在此无法区分。"},
            {"id": "readable_coinage", "condition": "余下无数字名称去连字符后长度5–20；每个连字符分块≥2字母；a/e/i/o/u/y占20%–70%；无连续5个非元音或连续4个元音。只是形态线索，仍会纳入随机串并漏掉真实品牌。"},
        ],
        "lexicon": lexicon_info,
        "sampling": {
            "seed": seed, "requested_probe_limit": limit,
            "hash": "SHA-256(UTF-8(seed + NUL + normalized_domain))",
            "group_percent": {g['id']:g['percent'] for g in groups},
            "ranking": "每个后缀组独立对未探测候选按完整哈希、域名字典序升序排列。组内不保证每一个后缀的单独最低数量。",
            "quotas": "先按配置份额取整，小数余数从大到小补齐；同余数按组声明顺序。某组不足时，其余名额按组声明顺序循环每次补1。",
            "previous_probes": "所有 --exclude-probed 文件中的域名仍记录名称判定与重合数量，但不会进入新请求队列。",
            "queue_order": "按组声明顺序，再按各组内固定哈希；不是网站价值排名。",
        },
        "limitations": [
            "词典或字符模式不能确认名称有意义；词典偏英语，年代旧，含罕见词及专名。",
            "筛选失败只表示本通道未覆盖，不能认定域名无意义或无价值；旧完整输入仍保留。",
            "IDN 编码名称暂未做多语言分词；可由其他独立通道处理。所有后缀均有分组，没有被后缀直接排除。",
            "名单日期是供应商批次日期；注册日期、首次上线、网页用途、关键词需求均尚未由名称筛选核实。",
        ],
    }


def self_test(words, groups):
    assert classify("gardenwater.com", words)[0] == "dictionary_segments"
    assert classify("gardenwater.com", words)[2] == ("garden", "water")
    assert classify("zunavelo.ai", words)[0] == "readable_coinage"
    assert classify("b2b.net", words)[0] == "alphanumeric_exploration"
    assert classify("qzx.ai", words)[0] == "short_abbreviation"
    assert classify("qzxvkjpb.com", words)[1] == "no_dictionary_or_readability_clue"
    assert classify("123456.com", words)[1] == "numeric_only"
    assert classify("hello123.com", words)[1] == "too_many_digits"
    assert classify("zzzzable.com", words)[1] == "repeated_character_run"
    assert classify("gardenwater.org", words)[0] == "dictionary_segments"
    assert classify("gardenwater.cc", words)[0] == "dictionary_segments"
    assert classify("gardenwater.xyz", words)[0] == "dictionary_segments"
    assert classify("xn--fiq228c.com", words)[1] == "encoded_idn"
    abundant = dict.fromkeys((g['id'] for g in groups), 9999)
    assert sum(quotas(3000, abundant, groups)[1].values()) == 3000
    scarce = {g['id']:i + 1 for i,g in enumerate(groups)}
    assert sum(quotas(100, scarce, groups)[1].values()) == sum(scarce.values())
    assert stable_hash("gardenwater.com", DEFAULT_SEED) == stable_hash("gardenwater.com", DEFAULT_SEED)
    print("Independent-name classification, dictionary segmentation and quota checks passed.")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, help="Existing month-screen deduplication.sqlite3")
    p.add_argument("--output", type=Path, help="New empty output directory")
    p.add_argument("--probe-limit", type=int, default=3000)
    p.add_argument("--exclude-probed", type=Path, action="append", default=[])
    p.add_argument("--seed", default=DEFAULT_SEED)
    p.add_argument("--groups-file", type=Path, default=GROUPS_FILE)
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args()
    groups = load_groups(a.groups_file)
    words = set(LEXICON.read_text(encoding="utf-8").splitlines())
    lexicon_info = json.loads(LEXICON_SOURCE.read_text(encoding="utf-8"))
    if checksum(LEXICON) != lexicon_info["snapshot_sha256"]:
        raise SystemExit("Lexicon checksum differs from documented snapshot")
    if a.self_test:
        self_test(words, groups)
        return
    if not a.input or not a.output or a.probe_limit < 0:
        p.error("--input and --output are required; --probe-limit must be nonnegative")
    if not a.input.is_file():
        p.error("Input SQLite file does not exist")
    output = a.output.resolve()
    if output.exists() and any(output.iterdir()):
        p.error("Use a new empty output directory to preserve earlier audits")
    output.mkdir(parents=True, exist_ok=True)
    excluded, exclusion_files = load_excluded(a.exclude_probed)
    document = rules(a.seed, a.probe_limit, lexicon_info, groups)
    write_json(output / "rules.json", document)
    counts, rejections, passed_tld, available_tld, path_counts = (Counter() for _ in range(5))
    path_by_tld = {}
    overlap_by_tld, input_tld, selected_tld, passed_group, available_group, diagnostic = (Counter() for _ in range(6))
    suffix_group = {t:g['id'] for g in groups for t in g['suffixes']}
    fallback_group = next(g['id'] for g in groups if g.get('fallback'))
    examples = {"passed": {}, "excluded": {}}
    heaps = {g['id']: [] for g in groups}
    origin_ids, sources = {}, []
    database = sqlite3.connect(a.input.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        database.execute("PRAGMA query_only=ON")
        database.execute("PRAGMA cache_size=-32768")
        with (output / "eligible_domains.csv").open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["domain", "tld", "suffix_group", "name_path", "dictionary_segments", "legacy_matches", "additional_matches", "source_id", "source_date", "source_line", "previously_probed"])
            cursor = database.execute("SELECT domain,source_path,source_date,source_line,discovery_order FROM seen ORDER BY domain")
            for domain, source_path, source_date, source_line, discovery_order in cursor:
                counts["input_unique_domains"] += 1
                tld = domain.rsplit('.', 1)[1]
                input_tld[tld] += 1
                group_id = suffix_group.get(tld, fallback_group)
                if source_path not in origin_ids:
                    origin_ids[source_path] = len(sources)
                    sources.append({"id": origin_ids[source_path], "path": source_path, "date": source_date})
                path, reason, tokens = classify(domain, words)
                if domain in excluded:
                    counts["previously_probed_in_input"] += 1
                if not path:
                    rejections[reason] += 1
                    group = examples["excluded"].setdefault(reason, [])
                    if len(group) < 5:
                        group.append(domain)
                    continue
                counts["eligible_domains"] += 1
                passed_tld[tld] += 1
                passed_group[group_id] += 1
                path_counts[path] += 1
                path_by_tld.setdefault(tld, Counter())[path] += 1
                name = domain.split('.', 1)[0]
                legacy = [term for term in TERMS if term in name]
                extra = [term for term in EXTRA_TERMS if term in name]
                diagnostic['eligible_with_legacy_terms' if legacy else 'eligible_without_legacy_terms'] += 1
                diagnostic['eligible_with_any_terms' if legacy or extra else 'eligible_without_any_terms'] += 1
                is_old = domain in excluded
                writer.writerow([domain, tld, group_id, path, "|".join(tokens), "|".join(legacy), "|".join(extra), origin_ids[source_path], source_date, source_line, int(is_old)])
                group = examples["passed"].setdefault(path, [])
                if len(group) < 5:
                    group.append({"domain": domain, "dictionary_segments": tokens})
                if is_old:
                    counts["eligible_previously_probed"] += 1
                    overlap_by_tld[tld] += 1
                    continue
                available_tld[tld] += 1
                available_group[group_id] += 1
                if a.probe_limit:
                    digest = stable_hash(domain, a.seed)
                    record = {
                        "domain": domain, "tld": tld, "name_path": path,
                        "dictionary_segments": tokens, "source_path": source_path,
                        "source_date": source_date, "source_line": source_line,
                        "discovery_order": discovery_order, "sampling_hash": digest,
                        "suffix_group": group_id, "name_matches": legacy, "additional_name_matches": extra,
                    }
                    entry = (-int(digest, 16), tuple(-ord(c) for c in domain) + (0,), record)
                    heap = heaps[group_id]
                    if len(heap) < a.probe_limit:
                        heapq.heappush(heap, entry)
                    elif entry[:2] > heap[0][:2]:
                        heapq.heapreplace(heap, entry)
                if counts["input_unique_domains"] % 100000 == 0:
                    print(json.dumps(dict(counts), ensure_ascii=False), file=sys.stderr, flush=True)
    finally:
        database.close()
    initial, final = quotas(a.probe_limit, available_group, groups)
    queue, boundaries = [], {}
    for group_def in groups:
        group_id = group_def['id']
        rows = sorted((v[2] for v in heaps[group_id]), key=lambda r: (r["sampling_hash"], r["domain"]))[:final[group_id]]
        for rank, row in enumerate(rows, 1):
            selected_tld[row['tld']] += 1
            queue.append({
                **row, "channel": group_id, "channels": [group_id],
                "selection_group": group_id,
                "reason_code": row["name_path"], "name_flags": [],
                "registration_status": "not_checked", "launch_status": "not_checked",
                "sampling_rank_within_channel": rank, "queue_rank": len(queue) + 1,
                "selection_reason": f"独立后缀与名称通道：{group_def['label']}（.{row['tld']}）；{PATH_LABELS[row['name_path']]}；固定哈希次序第{rank}名，组实际配额{final[group_id]}。未要求命中行业词根；名称线索不是意义或机会确认。",
                "source": "same dated WhoisDS monthly subset as previous screen; see input acquisition audit",
                "source_date_meaning": "list_batch_date_not_registration_or_launch_date",
            })
        boundaries[group_id] = ({"last_sampling_hash": rows[-1]["sampling_hash"], "last_domain": rows[-1]["domain"]} if rows else None)
    counts["eligible_unprobed"] = sum(available_tld.values())
    counts["probe_queue"] = len(queue)
    counts["eligible_unprobed_not_selected"] = counts["eligible_unprobed"] - len(queue)
    counts["excluded_by_this_channel"] = sum(rejections.values())
    counts['unique_valid_domains'] = counts['input_unique_domains']
    counts['name_eligible_domains'] = counts['eligible_domains']
    counts['excluded_previously_probed'] = counts['eligible_previously_probed']
    counts['selected_without_legacy_terms'] = sum(not r['name_matches'] for r in queue)
    counts['selected_without_any_terms'] = sum(not r['name_matches'] and not r['additional_name_matches'] for r in queue)
    assert counts["input_unique_domains"] == counts["eligible_domains"] + sum(rejections.values())
    assert counts["eligible_domains"] == counts["eligible_unprobed"] + counts["eligible_previously_probed"]
    assert not any(row["domain"] in excluded for row in queue)
    write_json(output / "probe_candidates.json", queue)
    write_json(output / "source_files.json", sources)
    write_json(output / "rule_examples.json", examples)
    manifest = {
        "schema_version": 1, "rule_version": VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input": {"path": str(a.input.resolve()), "sha256": checksum(a.input), "table": "seen", "mode": "read only", "unique_domains": counts["input_unique_domains"]},
        "counts": dict(counts), "rejection_counts": dict(rejections),
        "channels": [{"id": g['id'], "label": g['label'], "share_percent":g['percent'], "all_valid_count":passed_group[g['id']], "available_unprobed":available_group[g['id']], "initial_quota":initial[g['id']], "final_quota":final[g['id']], "last_selected":boundaries[g['id']]} for g in groups],
        "rules": document, "name_rules": document['paths_in_priority_order'],
        "term_diagnostics": {"original_terms":TERMS, "additional_terms":EXTRA_TERMS, "meaning":"Substrings for audit only; no term match participates in eligibility or sampling.", **dict(diagnostic)},
        "tld_counts": [{"tld": tld, "group":suffix_group.get(tld, fallback_group), "input":input_tld[tld], "eligible":passed_tld[tld], "unprobed_eligible":available_tld[tld], "previously_probed":overlap_by_tld[tld], "selected":selected_tld[tld]} for tld in sorted(input_tld, key=lambda t: (-input_tld[t],t))],
        "passed_by_tld": dict(passed_tld), "eligible_unprobed_by_tld": dict(available_tld),
        "previously_probed_overlap_by_tld": dict(overlap_by_tld),
        "name_paths": dict(path_counts), "name_paths_by_tld": {k: dict(v) for k, v in path_by_tld.items()},
        "exclusion_files": exclusion_files, "previously_probed_unique_domains": len(excluded),
        "sampling": {"initial_group_quotas": initial, "actual_group_quotas": final, "boundaries": boundaries, "seed": a.seed},
        "source_window": {"start": min(s["date"] for s in sources if s["date"]), "end": max(s["date"] for s in sources if s["date"]), "meaning": "provider list dates, not registration or launch dates"},
        "artifacts": {"eligible_domains": "eligible_domains.csv", "probe_queue": "probe_candidates.json", "source_files": "source_files.json", "examples": "rule_examples.json", "rules": "rules.json"},
        "audit_reproduction": "从只读SQLite seen表逐域名执行此版本规则；通过清单CSV含名称路径/分词/词根诊断/来源编号及旧探测重合；source_files.json将编号还原到原始路径。排除原因按首个匹配规则计数。所有失败域名仍在原SQLite；按同一词典和脚本可复算单域判定。对未探测通过者依后缀组内SHA256取前N，N见sampling.actual_group_quotas。词典、脚本与配置文件均随项目保存。",
    }
    write_json(output / "manifest.json", manifest)
    print(json.dumps({"manifest": str(output / "manifest.json"), "counts": dict(counts), "group_quotas": final}, ensure_ascii=False))


if __name__ == "__main__":
    main()
