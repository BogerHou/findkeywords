#!/usr/bin/env python3
"""Audit every domain; form a reproducible, quota-based website probe queue.

This offline name screen does not establish registration or launch dates and does
not identify search demand. Source dates are extracted from source filenames.
"""
import argparse
from collections import Counter
from contextlib import ExitStack
from datetime import date, datetime, timezone
import hashlib
import heapq
import ipaddress
import json
from pathlib import Path
import re
import sqlite3
import sys

from screen_names import TERMS


VERSION = "month-name-screen-v1"
DEFAULT_SEED = "findkeywords-month-v1"
# Supplements, not replacements for the original 43 substring roots. Short,
# especially ambiguous fragments such as 'ai', 'app' and 'pro' are not added.
EXTRA_TERMS = """check translate translation summarize summary transcribe
extract editor maker merge split optimize optimizer convert calculate
budget tax booking schedule calendar learn study tutor quiz practice
verification verify validation validate governance permission observability
compliance audit monitor workflow automate automation receipt expense
nutrition calorie workout meal gardening seedling sprite pixel vector
heic avif webp exif favicon encrypt decrypt password redact anonymize
accessibility contrast sitemap robots diff regex formatter validator
roadmap mindmap whiteboard synthesize speech voice podcast caption""".split()

CHANNELS = (
    ("legacy_terms", 50, "原 43 词根通道"),
    ("expanded_terms", 25, "补充任务词根通道"),
    ("name_exploration", 20, "无词根字符模式探索"),
    ("unrestricted_exploration", 5, "其余合规域名探索"),
)
CHANNEL_ORDER = {item[0]: i for i, item in enumerate(CHANNELS)}
LABEL_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
THREE_DIGITS = re.compile(r"\d{3}")
EXPLORATION_PATTERN = re.compile(r"[a-z]+(?:-[a-z]+){0,2}\Z")


def json_line(file, record):
    file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def source_date(path):
    match = DATE_PATTERN.search(path.name)
    if match:
        try:
            return date.fromisoformat(match.group()).isoformat()
        except ValueError:
            return None
    return None


def normalize_domain(raw):
    """Validate hostname syntax only, without DNS or a public-suffix lookup."""
    value = raw.strip().lower()
    if not value:
        return None, "blank_line"
    if any(char.isspace() for char in value):
        return None, "embedded_whitespace"
    if any(char in value for char in "/:@?#\\"):
        return None, "not_a_bare_domain"
    if value.endswith("."):
        value = value[:-1]  # Accept one DNS root dot; empty labels still fail.
    try:
        value = value.encode("idna").decode("ascii")
    except UnicodeError:
        return None, "idna_encoding_failed"
    if len(value) > 253:
        return None, "hostname_too_long"
    labels = value.split(".")
    if len(labels) < 2:
        return None, "missing_dot"
    if any(not LABEL_PATTERN.fullmatch(label) for label in labels):
        return None, "invalid_dns_label"
    if not re.search(r"[a-z]", labels[-1]):
        return None, "numeric_top_level_label"
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return value, None
    return None, "ip_address"


def classify(domain):
    name = domain.split(".", 1)[0]
    legacy = [term for term in TERMS if term in name]
    extra = [term for term in EXTRA_TERMS if term in name]
    flags = []
    if len(name) >= 34:
        flags.append("first_label_at_least_34_characters")
    if THREE_DIGITS.search(name):
        flags.append("contains_three_consecutive_digits")
    if name.startswith("xn--"):
        flags.append("punycode_first_label")
    legacy_pass = bool(legacy) and len(name) < 34 and not THREE_DIGITS.search(name)
    extra_pass = (
        not legacy and bool(extra) and len(name) <= 40
        and not THREE_DIGITS.search(name) and not name.startswith("xn--")
    )
    exploration_pass = (
        not legacy and not extra and 5 <= len(name) <= 30
        and bool(EXPLORATION_PATTERN.fullmatch(name))
        and bool(re.search("[aeiou]", name)) and not name.startswith("xn--")
    )
    if name.startswith("xn--"):
        channel = "unrestricted_exploration"
        reason = "punycode_name_kept_in_unrestricted_channel_not_matched_as_words"
    elif legacy_pass:
        channel = "legacy_terms"
        reason = "contains_original_root_and_passes_original_character_rules"
    elif extra_pass:
        channel = "expanded_terms"
        reason = "no_original_root_but_contains_supplementary_task_root"
    elif exploration_pass:
        channel = "name_exploration"
        reason = "no_root_hit_and_passes_published_character_pattern"
    else:
        channel = "unrestricted_exploration"
        reason = "valid_domain_outside_the_other_three_channels"
    return {
        "channel": channel,
        "channels": [channel],
        "reason_code": reason,
        "name_matches": legacy,
        "additional_name_matches": extra,
        "original_rule_pass": legacy_pass,
        "name_flags": flags,
    }


def sample_hash(domain, seed):
    return hashlib.sha256((seed + "\0" + domain).encode("utf-8")).hexdigest()


def allocate_quotas(limit, counts):
    """Largest remainder first; then fixed-order round-robin fills shortages."""
    initial = {key: limit * percent // 100 for key, percent, _ in CHANNELS}
    remainder_order = sorted(
        CHANNELS, key=lambda item: (-(limit * item[1] % 100), CHANNEL_ORDER[item[0]])
    )
    for key, _, _ in remainder_order[:limit - sum(initial.values())]:
        initial[key] += 1
    final = {key: min(initial[key], counts[key]) for key in initial}
    missing = min(limit, sum(counts.values())) - sum(final.values())
    while missing:
        for key, _, _ in CHANNELS:
            if final[key] < counts[key]:
                final[key] += 1
                missing -= 1
                if not missing:
                    break
    return initial, final


def rules_document(seed, limit):
    return {
        "version": VERSION,
        "original_terms": TERMS,
        "additional_terms": EXTRA_TERMS,
        "additional_terms_rationale": (
            "补充原名单遗漏的常见任务、内容格式和技术主题。仍是人工制定的固定英文子串表，"
            "没有语义模型或统计验证，不代表新词、需求或商业价值；如 tax 也可能是偶然子串。"
        ),
        "name_unit": "标准化为 IDNA/ASCII 后域名第一个点之前的标签；未使用公共后缀表，也不声称取得可注册根域名。",
        "idn_priority_override": "首标签以 xn-- 开始的 IDN 全部分入其余合规探索通道，避免将编码中偶然出现的 qr/csv 等片段当作工具词。仍记录全部子串命中及 original_rule_pass；原 43 词表与三个字符条件作为独立审计特征不变。",
        "channels_are_exclusive": True,
        "channel_rules": [
            {"id": "legacy_terms", "percent": 50, "condition":
             "非 punycode 首标签，且命中原 43 词根任一子串 AND 长度 <34 AND 无连续 3 个数字；原词表和三个条件未改，IDN 按公开优先级另入探索通道。"},
            {"id": "expanded_terms", "percent": 25, "condition":
             "未命中任何原词根 AND 命中补充词根 AND 长度 <=40 AND 无连续 3 个数字 AND 首标签非 punycode。"},
            {"id": "name_exploration", "percent": 20, "condition":
             "未命中两张词表 AND 首标签长度 5–30 AND 仅 a–z 字母及最多两个内部连字符 AND 至少一个 a/e/i/o/u AND 非 punycode；字符模式不等于可读性或有意义。"},
            {"id": "unrestricted_exploration", "percent": 5, "condition":
             "所有其余格式合规域名，包括数字名、长名、IDN 和未通过其他字符条件的词根命中；没有业务价值排除。"},
        ],
        "sampling": {
            "requested_probe_limit": limit,
            "seed": seed,
            "hash": "SHA-256(UTF-8(seed + NUL + normalized_domain))",
            "order_within_channel": "完整 256 位哈希升序，极小概率的哈希相同以域名字典序打破平局。",
            "quota_rounding": "先对百分比分配向下取整，余数按小数部分从大到小分配；同余数按通道声明次序。",
            "shortage_refill": "某通道数量不足时，剩余名额按通道声明次序循环，每轮给仍有候选的通道 1 名，直到达到 limit 或全部取完。",
            "queue_order": "通道声明次序，然后通道内哈希升序；不是价值排名。",
            "omitted_meaning": "未进入网页探测队列只表示本轮配额未覆盖；并非无价值或不新。",
        },
        "input_rules": {
            "normalization": "去行首尾空白、转小写、移除最多一个末尾根点、用 Python 标准库 IDNA 编码为 ASCII。",
            "accepted_syntax": "至少两个标签，总长 <=253；每标签 1–63 位 a–z/0–9/- 且首尾非连字符，末标签含英文字母。",
            "rejection": "只排除空行、非法编码和不符合以上域名格式的输入；不验证 TLD 是否真实存在，不做 DNS 查询。",
            "deduplication": "标准化域名全局去重，Unicode 与 punycode 两种等价表示会合并，数量可能低于旧版原字符串去重；文件按来源日期再路径排序，保留首次来源和行号，所有后续出现均写 duplicate_occurrences.jsonl。",
            "source_date": "只从文件名提取 YYYY-MM-DD；是名单来源日期，不能当作注册日期、证书签发日期或网站上线日期。",
            "date_window": "可选 --start-date/--end-date 仅约束输入文件的名单日期，不核验单个域名的年龄。",
        },
        "limitations": [
            "未读取网页；H1/title/description、注册日期、上线日期、搜索需求和竞争度均待后续验证。",
            "免费来源可能是截断样本；全部输入之和不是全球当月全部新域名。",
            "固定词表偏向英文和已知任务；两条探索通道降低这种选择偏差，但不能消除偏差。",
            "所有格式合规域名保留在 all_domains.jsonl 与对应通道 TXT；没有按名称宣布其无价值。",
        ],
    }


def self_test():
    assert len(TERMS) == 43
    assert normalize_domain(" Example.COM. ") == ("example.com", None)
    assert normalize_domain("https://example.com")[0] is None
    assert normalize_domain("foo..com")[0] is None
    assert normalize_domain("-foo.com")[0] is None
    assert normalize_domain("foo.123")[0] is None
    assert normalize_domain("中文.com")[0] == "xn--fiq228c.com"
    assert classify("agentpermissionmatrix.com")["channel"] == "legacy_terms"
    assert classify("magento.com")["name_matches"] == ["agent"]
    assert classify("taxriskcheck.com")["channel"] == "expanded_terms"
    assert classify("personal-budget.app")["channel"] == "expanded_terms"
    assert classify("zunavelo.com")["channel"] == "name_exploration"
    assert classify("12345.com")["channel"] == "unrestricted_exploration"
    assert classify("calculator100.com")["channel"] == "unrestricted_exploration"
    assert classify("xn--fiq228c.com")["channel"] == "unrestricted_exploration"
    assert classify("xn--cn2-qr6el54e.com")["channel"] == "unrestricted_exploration"
    assert classify("xn--cn2-qr6el54e.com")["original_rule_pass"] is True
    abundant = dict.fromkeys(CHANNEL_ORDER, 9999)
    assert allocate_quotas(3000, abundant)[1] == dict(zip(CHANNEL_ORDER, [1500, 750, 600, 150]))
    scarce = dict(zip(CHANNEL_ORDER, [1, 2, 20, 20]))
    assert sum(allocate_quotas(10, scarce)[1].values()) == 10
    assert sum(allocate_quotas(100, scarce)[1].values()) == 43
    assert sample_hash("example.com", DEFAULT_SEED) == sample_hash("example.com", DEFAULT_SEED)
    assert sample_hash("example.com", DEFAULT_SEED) != sample_hash("other.com", DEFAULT_SEED)
    print("Rule, normalization, quota, and stable-hash checks passed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path, help="UTF-8 TXT domain lists")
    parser.add_argument("--output", type=Path, help="A new output directory")
    parser.add_argument("--probe-limit", type=int, default=3000)
    parser.add_argument("--seed", default=DEFAULT_SEED)
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.files or args.output is None:
        parser.error("files and --output are required unless --self-test is used")
    if args.probe_limit < 0:
        parser.error("--probe-limit must be nonnegative")
    if args.start_date and args.end_date and args.start_date > args.end_date:
        parser.error("--start-date must not exceed --end-date")
    files = sorted(set(path.resolve() for path in args.files),
                   key=lambda path: (source_date(path) or "9999-99-99", str(path)))
    for path in files:
        if not path.is_file():
            parser.error(f"Input file does not exist: {path}")
        batch_date = source_date(path)
        if args.start_date or args.end_date:
            if not batch_date:
                parser.error(f"Cannot apply a date window to undated file: {path}")
            parsed = date.fromisoformat(batch_date)
            if ((args.start_date and parsed < args.start_date)
                    or (args.end_date and parsed > args.end_date)):
                parser.error(f"Source date outside the requested window: {path}")
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Output directory must be empty; use a new directory to preserve earlier audits")
    output.mkdir(parents=True, exist_ok=True)
    (output / "channels").mkdir()
    rules = rules_document(args.seed, args.probe_limit)
    (output / "rules.json").write_text(json.dumps(rules, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts, rejection_counts, batch_records = Counter(), Counter(), []
    heaps = {key: [] for key in CHANNEL_ORDER}
    counters = Counter()
    with ExitStack() as stack:
        database = sqlite3.connect(output / "deduplication.sqlite3")
        stack.callback(database.close)
        database.execute("PRAGMA journal_mode=OFF")
        database.execute("PRAGMA synchronous=OFF")
        database.execute("PRAGMA cache_size=-32768")
        database.execute("CREATE TABLE seen(domain TEXT PRIMARY KEY, discovery_order INTEGER NOT NULL, source_path TEXT NOT NULL, source_date TEXT, source_line INTEGER NOT NULL) WITHOUT ROWID")
        all_file = stack.enter_context((output / "all_domains.jsonl").open("w", encoding="utf-8"))
        invalid_file = stack.enter_context((output / "invalid_inputs.jsonl").open("w", encoding="utf-8"))
        duplicates_file = stack.enter_context((output / "duplicate_occurrences.jsonl").open("w", encoding="utf-8"))
        channel_files = {
            key: stack.enter_context((output / "channels" / f"{key}.txt").open("w", encoding="utf-8"))
            for key in CHANNEL_ORDER
        }
        for path in files:
            file_date, checksum, batch_counts = source_date(path), hashlib.sha256(), Counter()
            with path.open("rb") as source:
                for line_number, binary_line in enumerate(source, 1):
                    checksum.update(binary_line)
                    counters["raw_lines"] += 1
                    batch_counts["raw_lines"] += 1
                    try:
                        raw = binary_line.decode("utf-8-sig" if line_number == 1 else "utf-8").rstrip("\r\n")
                        domain, error = normalize_domain(raw)
                    except UnicodeDecodeError:
                        raw, domain, error = binary_line.decode("utf-8", errors="replace").rstrip("\r\n"), None, "invalid_utf8"
                    origin = {"source_path": str(path), "source_date": file_date, "source_line": line_number}
                    if error:
                        rejection_counts[error] += 1
                        batch_counts["invalid_or_blank_lines"] += 1
                        json_line(invalid_file, {**origin, "raw": raw, "reason_code": error})
                        continue
                    counters["valid_occurrences"] += 1
                    batch_counts["valid_occurrences"] += 1
                    discovery_order = counters["unique_valid_domains"] + 1
                    cursor = database.execute(
                        "INSERT OR IGNORE INTO seen VALUES (?, ?, ?, ?, ?)",
                        (domain, discovery_order, str(path), file_date, line_number),
                    )
                    if not cursor.rowcount:
                        counters["duplicate_occurrences"] += 1
                        batch_counts["duplicate_occurrences"] += 1
                        json_line(duplicates_file, {"domain": domain, **origin})
                        continue
                    counters["unique_valid_domains"] += 1
                    batch_counts["unique_valid_domains"] += 1
                    decision = classify(domain)
                    if decision["original_rule_pass"]:
                        counters["original_rule_pass_after_idna_normalization"] += 1
                    if "punycode_first_label" in decision["name_flags"]:
                        counters["punycode_first_label_domains"] += 1
                    channel = decision["channel"]
                    counts[channel] += 1
                    digest = sample_hash(domain, args.seed)
                    record = {
                        "domain": domain, "input_domain": raw.strip(), **origin, "discovery_order": discovery_order,
                        **decision, "sampling_hash": digest,
                        "registration_status": "not_checked", "launch_status": "not_checked",
                    }
                    json_line(all_file, record)
                    channel_files[channel].write(domain + "\n")
                    if args.probe_limit:
                        # Negative hash turns Python's min-heap into a bounded
                        # max-heap: its root is the worst retained sample.
                        heap = heaps[channel]
                        entry = (-int(digest, 16), tuple(-ord(c) for c in domain) + (0,), record)
                        if len(heap) < args.probe_limit:
                            heapq.heappush(heap, entry)
                        elif entry[:2] > heap[0][:2]:
                            heapq.heapreplace(heap, entry)
                    if counters["unique_valid_domains"] % 10000 == 0:
                        database.commit()
            database.commit()
            batch_records.append({"path": str(path), "source_date": file_date,
                                  "sha256": checksum.hexdigest(), **dict(batch_counts)})
            print(f"Read {path.name}: {batch_counts['raw_lines']:,} lines; "
                  f"{batch_counts['unique_valid_domains']:,} new unique valid domains", file=sys.stderr)
        initial_quota, final_quota = allocate_quotas(args.probe_limit, counts)
        queue = []
        for key, _, label in CHANNELS:
            ranked = sorted((entry[2] for entry in heaps[key]), key=lambda row: (row["sampling_hash"], row["domain"]))
            for rank, record in enumerate(ranked[:final_quota[key]], 1):
                queue.append({
                    **record, "queue_rank": len(queue) + 1, "sampling_rank_within_channel": rank,
                    "selection_group": key, "selection_reason": f"{label}：{record['reason_code']}；固定 SHA-256 次序第 {rank} 名，通道实际配额 {final_quota[key]}。这不是机会评分。",
                    "source": "dated domain-list input; provider details in acquisition manifest",
                    "source_date_meaning": "list_batch_date_not_registration_or_launch_date",
                })
        (output / "probe_candidates.json").write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        boundaries = {}
        for key in CHANNEL_ORDER:
            selected = [row for row in queue if row["channel"] == key]
            boundaries[key] = ({"last_sampling_hash": selected[-1]["sampling_hash"],
                                "last_domain": selected[-1]["domain"]} if selected else None)
        manifest = {
            "schema_version": 1, "rule_version": VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_window": {"start": str(args.start_date) if args.start_date else None,
                              "end": str(args.end_date) if args.end_date else None,
                              "meaning": "input list dates only; domain age and launch date unverified"},
            "input_files": batch_records,
            "counts": {**dict(counters), "invalid_or_blank_lines": sum(rejection_counts.values()),
                       "probe_queue": len(queue), "valid_domains_not_in_probe_queue": counters["unique_valid_domains"] - len(queue)},
            "rejection_counts": dict(rejection_counts),
            "channels": [{"id": key, "label": label, "share_percent": percent,
                          "all_valid_count": counts[key], "initial_quota": initial_quota[key],
                          "final_quota": final_quota[key], "last_selected": boundaries[key],
                          "domain_list": f"channels/{key}.txt"} for key, percent, label in CHANNELS],
            "rules": rules,
            "artifacts": {
                "all_domains": "all_domains.jsonl", "probe_queue": "probe_candidates.json",
                "invalid_inputs": "invalid_inputs.jsonl", "duplicate_occurrences": "duplicate_occurrences.jsonl",
                "deduplication_database": "deduplication.sqlite3", "rules": "rules.json",
            },
            "audit_reproduction": "按同一 seed 和 rules 对每条合规域名计算 SHA-256；在其唯一通道内按 (hash, domain) 升序取 final_quota 条。all_domains.jsonl 中每条均保留原文件、名单日期、行号、词根命中和原因代码。跨文件重复出现另存 duplicate_occurrences.jsonl。",
        }
        (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(output / "manifest.json"), "counts": manifest["counts"],
                      "channel_counts": dict(counts)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
