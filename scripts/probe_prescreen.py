#!/usr/bin/env python3
"""Prepare offline; run a bounded HTTPS pilot on an explicitly configured Mac/Linux host.

No network activity on import, prepare, --help, or run without --execute.
Only the run command with --execute performs DNS/HTTPS requests.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import sys
import time
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import probe_domains as probe

VERSION = "prescreen-2026-09-28-v2"
ROOT = Path(__file__).resolve().parents[1]
NETWORK_CONFIG = ROOT / "config/network.local.json"
UA = "FindKeywordsResearch"
POLICY = {
    "version": VERSION, "concurrency": 1, "min_request_interval_seconds": 2,
    "min_host_interval_seconds": 5, "transfer_timeout_seconds": 8,
    "request_deadline_seconds": 15, "max_decoded_response_bytes": 131072,
    "max_robots_bytes": 32768,
    "max_redirects": 2, "automatic_retries": 0, "https_only": True,
    "stop_on_any_429": True, "stop_after_consecutive_blocks": 3,
    "stop_after_consecutive_transport_failures": 10,
    "minimum_visible_characters": 160, "maximum_batch_domains": 100,
}
CHALLENGE = re.compile(r"just a moment|access denied|verify (?:that )?you are human|"
                       r"checking your browser|security verification|attention required|验证码|人机验证", re.I)
PARKED = re.compile(r"(?:this |the )?domain (?:name )?(?:is )?(?:for sale|parked)|"
                    r"buy this domain|domain parking|域名出售|此域名正在出售", re.I)
PLACEHOLDER = re.compile(r"coming soon[.!…]*|under construction[.!…]*|welcome to nginx[.!]*|"
                         r"apache2? (?:\w+ )?default page|default (?:web ?site|page)|"
                         r"index of /.*|网站建设中[！。]*|即将上线[！。]*", re.I)
SOFT_404 = re.compile(r"(?:404\s*[-:|]?\s*)?(?:page )?not found[.!]*|404|页面不存在", re.I)


def dump(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def machine_marker():
    # An accidental-use guard, not a security boundary or network-route proof.
    value = "\0".join((socket.gethostname(), str(Path.home()), sys.platform))
    return hashlib.sha256(value.encode()).hexdigest()


def network_init(args):
    path = args.network_config
    if path.exists():
        raise SystemExit("Local network configuration already exists; inspect it before replacing it.")
    path.parent.mkdir(parents=True, exist_ok=True)
    dump(path, {"version": 1, "machine": machine_marker(), "label": args.label,
                "created_at": probe.iso_time(probe.utc_now()),
                "note": "Local opt-in only; verify this computer's actual network route separately."})
    path.chmod(0o600)
    print(json.dumps({"local_config": str(path), "network_requests": 0}))


def validate_network(path):
    if sys.platform not in {"darwin", "linux"}:
        raise SystemExit("The probe currently supports macOS and Linux.")
    if not path.exists():
        raise SystemExit("No local network configuration. On the request computer, run network-init first. No requests made.")
    config = json.loads(path.read_text())
    if config.get("machine") != machine_marker():
        raise SystemExit("This network configuration belongs to a different computer. Do not copy it through Git.")
    if any(v for k, v in os.environ.items() if k.lower() in {"http_proxy", "https_proxy", "all_proxy"}):
        raise SystemExit("Proxy environment detected; verify direct egress on the request computer. No requests made.")
    return config


def classify_page(html: str, fields: dict) -> tuple[str, str]:
    """Conservative heuristics: short pages are unknown, never proven unused."""
    title_and_h1 = [fields["title"], *fields["h1"]]
    heading = " | ".join(title_and_h1)
    text = fields["visible_text"]
    if CHALLENGE.search(heading) or (len(text) < 800 and CHALLENGE.search(text)):
        return "recheck", "challenge"
    if any(SOFT_404.fullmatch(s.strip()) for s in title_and_h1 if s.strip()):
        return "skip", "soft_404"
    # Require a short page plus prominent parking/placeholder wording. A long
    # article discussing domain sales is not automatically rejected.
    if len(text) < 1200 and PARKED.search(heading):
        return "skip", "parking_page"
    if len(text) < 800 and any(PLACEHOLDER.fullmatch(s.strip()) for s in title_and_h1 if s.strip()):
        return "skip", "placeholder_page"
    if len(text) < POLICY["minimum_visible_characters"]:
        return "recheck", "javascript_or_thin" if re.search(r"<script\b", html, re.I) else "thin_or_empty"
    if not any(s.strip() for s in title_and_h1) and not fields["description"]:
        return "recheck", "missing_keyword_evidence"
    return "pass", "html_with_content"


class Deferred(Exception):
    def __init__(self, reason, *, decision="recheck", stop=False):
        self.reason, self.decision, self.stop = reason, decision, stop


def check_response(result: dict, stage: str):
    status = result.get("http_status")
    if status == 429:
        raise Deferred("rate_limited", stop=True)
    if result.get("error_kind") == "local_ca_error":
        raise Deferred("local_ca_error", stop=True)
    if status in (401, 403):
        raise Deferred("http_blocked")
    if result["status"] != "ok":
        if stage == "homepage" and status in (404, 410):
            raise Deferred("homepage_missing", decision="skip")
        raise Deferred(result.get("error_kind") or f"{stage}_{result['status']}")


@contextmanager
def deadline(seconds):
    def expired(signum, frame):
        raise TimeoutError("request deadline reached, including DNS")
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


class Transport:
    def __init__(self):
        self.last_request = float("-inf")
        self.last_host = {}

    def get(self, url, *, stage="homepage"):
        host = urlsplit(url).hostname
        delay = max(self.last_request + POLICY["min_request_interval_seconds"],
                    self.last_host.get(host, float("-inf")) + POLICY["min_host_interval_seconds"]) - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self.last_request = self.last_host[host] = time.monotonic()
        with deadline(POLICY["request_deadline_seconds"]):
            # No redirects hidden in curl, no HTTP fallback or Fake-IP DoH.
            limit = POLICY["max_robots_bytes"] if stage == "robots" else POLICY["max_decoded_response_bytes"]
            return probe.fetch_public(url, max_redirects=0, allow_fake_ip_doh=False, max_response_bytes=limit)


class DomainCheck:
    def __init__(self, row, transport, evidence_dir=None):
        self.domain = probe.normalize_domain(row["domain"])
        self.hosts = {self.domain, "www." + self.domain}
        self.transport, self.evidence_dir = transport, evidence_dir
        self.robots_cache = {}
        self.row = {"domain": self.domain, "source": row, "policy_version": VERSION,
                    "checked_at": probe.iso_time(probe.utc_now()), "requests": [], "stop_batch": False}

    def validate_url(self, url):
        p = urlsplit(url)
        if p.scheme != "https":
            raise Deferred("https_downgrade")
        if p.hostname not in self.hosts or p.username or p.password or p.port not in (None, 443):
            raise Deferred("external_or_unsupported_redirect")

    def get(self, url, stage):
        self.validate_url(url)
        try:
            result = self.transport.get(url, stage=stage)
        except (TimeoutError, OSError) as exc:
            result = {"status": "network_error", "error_kind": "timeout" if isinstance(exc, TimeoutError) else "transport_error",
                      "error": str(exc), "http_status": None, "body": b"", "request_count": None}
        info = {key: value for key, value in result.items() if key != "body"}
        info.update(url=url, stage=stage)
        body = result.get("body", b"")
        if body:
            digest = hashlib.sha256(body).hexdigest()
            info["body_sha256"] = digest
            if self.evidence_dir is not None:
                self.evidence_dir.mkdir(parents=True, exist_ok=True)
                path = self.evidence_dir / (digest + ".gz")
                if not path.exists():
                    path.write_bytes(gzip.compress(body, mtime=0))
                info["body_file"] = "evidence/" + path.name
        self.row["requests"].append(info)
        return result

    def fetch(self, url, stage):
        seen = set()
        for hop in range(POLICY["max_redirects"] + 1):
            self.validate_url(url)
            if url in seen:
                raise Deferred("redirect_loop")
            seen.add(url)
            if stage == "homepage":
                self.check_robots(url)
            result = self.get(url, stage)
            if result.get("http_status") in probe.REDIRECT_CODES:
                if result.get("curl_exit_code") not in (None, 0):
                    check_response(result, stage)
                if not result.get("location") or hop == POLICY["max_redirects"]:
                    raise Deferred("redirect_limit_or_missing_location")
                url = urljoin(url, result["location"])
                continue
            return result
        raise Deferred("redirect_limit")

    def check_robots(self, url):
        host = urlsplit(url).hostname
        if host not in self.robots_cache:
            robots_url = f"https://{host}/robots.txt"
            result = self.fetch(robots_url, "robots")
            if result.get("http_status") in (404, 410) and result.get("curl_exit_code") in (None, 0):
                self.robots_cache[host] = None
            else:
                check_response(result, "robots")
                text = probe.decode_html(result.get("body", b""), result.get("content_type"))
                if re.search(r"<(?:!doctype|html|head|body)\b", text, re.I):
                    raise Deferred("robots_returned_html")
                # Python's stdlib parser does not implement wildcard/end-anchor
                # rules fully. Defer these rather than silently ignoring them.
                if re.search(r"^\s*(?:allow|disallow)\s*:[^\n]*[*$]", text, re.I | re.M):
                    raise Deferred("robots_complex_rules")
                parser = RobotFileParser(robots_url)
                parser.parse(text.splitlines())
                self.robots_cache[host] = parser
        parser = self.robots_cache[host]
        if parser:
            if not parser.can_fetch(UA, url):
                raise Deferred("robots_disallowed")
            delay, rate = parser.crawl_delay(UA), parser.request_rate(UA)
            if (delay and delay > 5) or (rate and rate.seconds / rate.requests > 5):
                raise Deferred("robots_slower_schedule_required")

    def run(self):
        try:
            result = self.fetch(f"https://{self.domain}/", "homepage")
            if result["status"] == "too_large" and result.get("body"):
                parser = probe.PageParser()
                parser.feed(probe.decode_html(result["body"], result.get("content_type")))
                self.row.update(page_prefix=parser.extracted(), incomplete_html=True)
            check_response(result, "homepage")
            self.row["final_url"] = result.get("final_url")
            ctype = (result.get("content_type") or "").split(";")[0].lower().strip()
            if ctype not in ("text/html", "application/xhtml+xml"):
                raise Deferred("non_html" if ctype else "missing_content_type",
                               decision="skip" if ctype else "recheck")
            html = probe.decode_html(result.get("body", b""), result.get("content_type"))
            parser = probe.PageParser()
            parser.feed(html)
            parser.close()
            self.row["page"] = parser.extracted()
            self.row["decision"], self.row["reason"] = classify_page(html, self.row["page"])
        except Deferred as exc:
            self.row.update(decision=exc.decision, reason=exc.reason, stop_batch=exc.stop)
        except (ValueError, UnicodeError) as exc:
            self.row.update(decision="recheck", reason="parse_or_url_error", error=str(exc)[:300])
        return self.row


def prepare(args):
    source_bytes = args.input.read_bytes()
    data = json.loads(source_bytes)
    rows = sorted(data["domains"], key=lambda r: hashlib.sha256(r["domain"].encode()).hexdigest())
    pools = {r["id"]: iter([d for d in rows if r["id"] in d["roots"]]) for r in data["roots"]}
    selected, seen = [], set()
    while len(selected) < args.limit:
        before = len(selected)
        for root, pool in pools.items():
            candidate = next((r for r in pool if r["domain"] not in seen), None)
            if candidate:
                seen.add(candidate["domain"])
                selected.append({**candidate, "sampling_root": root})
            if len(selected) == args.limit:
                break
        if len(selected) == before:
            break
    args.output.mkdir(parents=True, exist_ok=False)
    dump(args.output / "queue.json", {"policy": POLICY, "selection": "51 roots round-robin; SHA256(domain) order within each root; deduplicated; not value ranking",
                                    "source": str(args.input), "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
                                    "source_domain_window": data["meta"]["sourceWindow"], "domains": selected})
    print(json.dumps({"prepared_domains": len(selected), "network_requests": 0, "output": str(args.output)}, ensure_ascii=False))


def run(args):
    queue_bytes = args.input.read_bytes()
    rows = json.loads(queue_bytes)["domains"]
    if not args.execute:
        print(json.dumps({"mode": "offline_preview", "queued": len(rows), "max_this_run": args.limit,
                          "network_requests": 0, "note": "Configured Mac/Linux host only: --execute performs requests",
                          "policy": POLICY}))
        return
    network = validate_network(args.network_config)
    if not shutil.which("curl"):
        raise SystemExit("curl is required on the server")
    import fcntl
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / ".lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("This output directory is already in use")
        manifest = {"queue_sha256": hashlib.sha256(queue_bytes).hexdigest(), "policy": POLICY,
                    "network_label": network["label"], "machine": network["machine"]}
        manifest_path = args.output / "run.json"
        if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
            raise SystemExit("Queue or policy changed; use a new output directory")
        dump(manifest_path, manifest)
        result_path = args.output / "results.jsonl"
        saved = [json.loads(line) for line in result_path.read_text().splitlines()] if result_path.exists() else []
        done = {r["domain"] for r in saved}
        pending = [r for r in rows if r["domain"] not in done][:args.limit]
        probe.TIMEOUT_SECONDS = POLICY["transfer_timeout_seconds"]
        transport, blocked, failed, stop_reason = Transport(), 0, 0, None
        if saved and saved[-1].get("stop_batch"):
            raise SystemExit("Previous run paused after a block or transport failures. Inspect results and Retry-After; do not auto-resume. A reviewed retry requires a new queue/output.")
        with result_path.open("a", encoding="utf-8") as out:
            for item in pending:
                try:
                    record = DomainCheck(item, transport, args.output / "evidence").run()
                except KeyboardInterrupt:
                    stop_reason = "interrupted; completed rows saved"
                    break
                blocked = blocked + 1 if record["reason"] in {"http_blocked", "challenge"} else 0
                failed = failed + 1 if record["reason"] in {"dns_error", "connect_error", "timeout", "tls_handshake_error", "tls_certificate_error", "transport_error"} else 0
                if blocked >= 3 or failed >= 10:
                    record["stop_batch"] = True
                    record["batch_stop_reason"] = "consecutive_blocks" if blocked >= 3 else "consecutive_transport_failures"
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                out.flush()
                os.fsync(out.fileno())
                saved.append(record)
                done.add(record["domain"])
                print(f"{len(done)}/{len(rows)} {record['domain']} {record['decision']} {record['reason']}", flush=True)
                if record["stop_batch"]:
                    stop_reason = record.get("batch_stop_reason", record["reason"])
                    break
        summary = {"policy_version": VERSION, "queued": len(rows), "completed": len(done),
                   "pending": len(rows) - len(done), "decisions": dict(Counter(r["decision"] for r in saved)),
                   "reasons": dict(Counter(r["reason"] for r in saved)), "stop_reason": stop_reason,
                   "note": "Technical precheck only; not verified launch dates or rising search keywords."}
        dump(args.output / "summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("network-init", help="Offline: opt in this request computer, never upload this config")
    init.add_argument("--label", required=True)
    init.add_argument("--network-config", type=Path, default=NETWORK_CONFIG)
    for name in ("prepare", "run"):
        p = sub.add_parser(name)
        p.add_argument("--input", type=Path, required=True)
        p.add_argument("--output", type=Path, required=True)
        p.add_argument("--limit", type=int, default=100)
        if name == "run":
            p.add_argument("--execute", action="store_true")
            p.add_argument("--network-config", type=Path, default=NETWORK_CONFIG)
    args = parser.parse_args()
    if args.command == "network-init":
        network_init(args)
        return
    if not 1 <= args.limit <= POLICY["maximum_batch_domains"]:
        parser.error("--limit must be between 1 and 100 for this pilot")
    (prepare if args.command == "prepare" else run)(args)


if __name__ == "__main__":
    main()
