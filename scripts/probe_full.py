#!/usr/bin/env python3
"""Resumable AWS sweep. Runs only with --execute and machine-local network opt-in."""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
import fcntl
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import re
import signal
import time
from urllib.parse import urlsplit

import probe_prescreen as pre

VERSION = 'full-prescreen-2026-09-28-v1'
POLICY = {**pre.POLICY, 'version': VERSION, 'concurrency': 8, 'min_request_interval_seconds': 0.5,
          'maximum_batch_domains': 20000, 'stop_on_any_429': False,
          'rate_limit_action': 'Stop that origin; no automatic retry. No proxy/IP rotation.',
          'stop_after_consecutive_blocks': 50, 'stop_after_consecutive_transport_failures': None,
          'global_stop_reasons': ['local_ca_error', 'worker_error', 'disk_error'],
          'note': 'Separate full-sweep policy authorized 2026-09-28. Pilot v2 records remain unchanged.'}
BASE_CLASSIFY = pre.classify_page
_lock = _last = None


def classify_page(html, fields):
    values = [fields.get('title', ''), *fields.get('h1', [])]
    text = fields.get('visible_text', '')
    if len(text) < 1200 and any(re.match(r'^\s*[a-z0-9.-]+\.[a-z]{2,}\s+(?:is\s+)?for sale\b', s, re.I) for s in values):
        return 'skip', 'parking_page'
    if len(text) < 800 and any(re.fullmatch(r'\s*launching soon[.!…]*\s*', s, re.I) for s in values):
        return 'skip', 'placeholder_page'
    if any(re.fullmatch(r'(?:h1\s+)?lorem ipsum[.!]*', s.strip(), re.I) for s in values) and re.search(r'lorem ipsum', fields.get('description', ''), re.I):
        return 'skip', 'template_placeholder'
    return BASE_CLASSIFY(html, fields)


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n')
    temp.replace(path)


def load_records(path, allowed=None):
    if not path.exists():
        return []
    raw = path.read_bytes()
    if raw and not raw.endswith(b'\n'):
        raise ValueError('Partial last record; inspect and repair before resuming: ' + str(path))
    rows = [json.loads(x) for x in raw.splitlines()]
    names = [r['domain'] for r in rows]
    if len(names) != len(set(names)) or (allowed is not None and not set(names) <= allowed):
        raise ValueError('Duplicate or out-of-queue results')
    return rows


class SharedTransport(pre.Transport):
    def get(self, url, *, stage='homepage'):
        host = urlsplit(url).hostname
        delay = self.last_host.get(host, float('-inf')) + POLICY['min_host_interval_seconds'] - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        with _lock:
            delay = _last.value + POLICY['min_request_interval_seconds'] - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            _last.value = time.monotonic()
            self.last_host[host] = _last.value
        with pre.deadline(POLICY['request_deadline_seconds']):
            limit = POLICY['max_robots_bytes'] if stage == 'robots' else POLICY['max_decoded_response_bytes']
            return pre.probe.fetch_public(url, max_redirects=0, allow_fake_ip_doh=False, max_response_bytes=limit)


class FullCheck(pre.DomainCheck):
    def get(self, url, stage):
        result = super().get(url, stage)
        self.row['requests'][-1]['saved_decoded_bytes'] = len(result.get('body', b''))
        return result


def initialize(lock, last):
    global _lock, _last
    _lock, _last = lock, last
    pre.POLICY = POLICY
    pre.VERSION = VERSION
    pre.classify_page = classify_page
    pre.probe.TIMEOUT_SECONDS = POLICY['transfer_timeout_seconds']
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def check(row, evidence):
    record = FullCheck(row, SharedTransport(), Path(evidence)).run()
    if record['reason'] == 'rate_limited':
        record.update(stop_batch=False, stopped_origin=True)
    return record


def summary_doc(queue, records, reused, status, started, stop_reason=None):
    all_rows = reused + records
    current_requests = [q for r in records for q in r.get('requests', [])]
    elapsed = max(0, time.time() - started)
    return {'version': VERSION, 'status': status, 'updated_at': pre.probe.iso_time(pre.probe.utc_now()),
            'started_at_epoch': started, 'elapsed_seconds': round(elapsed), 'universe': queue['summary']['universe'],
            'source_window': queue['source']['window'], 'reused': len(reused), 'queued': len(queue['domains']),
            'newly_completed': len(records), 'covered': len(all_rows), 'pending': len(queue['domains']) - len(records),
            'decisions': dict(Counter(r['decision'] for r in all_rows)), 'reasons': dict(Counter(r['reason'] for r in all_rows)),
            'new_decisions': dict(Counter(r['decision'] for r in records)),
            'known_http_attempts': sum(q.get('request_count') or 0 for q in current_requests),
            'requests_with_unknown_count': sum(q.get('request_count') is None for q in current_requests),
            'saved_decoded_bytes': sum(q.get('saved_decoded_bytes', 0) for q in current_requests),
            'stop_reason': stop_reason, 'policy': POLICY,
            'trends': {'status': 'waiting_for_domain_screening', 'confirmed': None,
                       'rule': 'US / web / search term; latest 30 complete days; last7 >= 2 * preceding7; >=5 nonzero days in last7; exclude single spikes and old-term rebounds using six-month background.'},
            'note': 'Technical screening is not keyword qualification. Recheck means insufficient evidence, not a bad website. Domain list date is not a verified launch date.'}


def run(args):
    queue_raw = args.input.read_bytes()
    queue = json.loads(queue_raw)
    rows = queue['domains']
    names = {r['domain'] for r in rows}
    if len(names) != len(rows) or len(rows) > POLICY['maximum_batch_domains']:
        raise ValueError('Invalid queue size or duplicates')
    reuse_path = args.input.parent / 'reused.jsonl'
    if hashlib.sha256(reuse_path.read_bytes()).hexdigest() != queue['reuse_sha256']:
        raise ValueError('Reuse checksum mismatch')
    reused = load_records(reuse_path)
    if names & {r['domain'] for r in reused} or len(reused) + len(rows) != queue['summary']['universe']:
        raise ValueError('Coverage accounting mismatch')
    if not args.execute:
        print(json.dumps({'mode': 'offline_preview', 'queued': len(rows), 'reuse': len(reused), 'network_requests': 0, 'policy': POLICY}))
        return
    network = pre.validate_network(args.network_config)
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / '.lock').open('w') as lockfile:
        fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest = {'queue_sha256': hashlib.sha256(queue_raw).hexdigest(), 'reuse_sha256': queue['reuse_sha256'],
                    'policy': POLICY, 'machine': network['machine'], 'network_label': network['label']}
        manifest_path = args.output / 'run.json'
        if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
            raise ValueError('Manifest mismatch; do not resume changed queues or policies')
        atomic_json(manifest_path, manifest)
        result_path = args.output / 'results.jsonl'
        records = load_records(result_path, names)
        summary_path = args.output / 'summary.json'
        old_summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
        if old_summary.get('status') == 'paused':
            raise ValueError('Paused run requires review; do not auto-resume')
        done = {r['domain'] for r in records}
        remaining = iter(r for r in rows if r['domain'] not in done)
        started = old_summary.get('started_at_epoch', time.time())
        stop_reason, blocked = None, 0
        stopping = [False]
        def handle_stop(signum, frame):
            stopping[0] = True
        signal.signal(signal.SIGTERM, handle_stop)
        signal.signal(signal.SIGINT, handle_stop)
        def publish(status):
            doc = summary_doc(queue, records, reused, status, started, stop_reason)
            atomic_json(summary_path, doc)
            if args.site_status:
                atomic_json(args.site_status, doc)
        publish('screening')
        ctx = mp.get_context('spawn')
        shared_lock, last = ctx.Lock(), ctx.Value('d', 0)
        last_publish = 0
        with result_path.open('a') as out, ProcessPoolExecutor(max_workers=POLICY['concurrency'], mp_context=ctx,
                initializer=initialize, initargs=(shared_lock, last)) as pool:
            active = {}
            def fill():
                while not stopping[0] and len(active) < POLICY['concurrency']:
                    row = next(remaining, None)
                    if row is None:
                        break
                    active[pool.submit(check, row, str(args.output / 'evidence'))] = row
            fill()
            while active:
                completed, _ = wait(active, timeout=5, return_when=FIRST_COMPLETED)
                for future in completed:
                    row = active.pop(future)
                    try:
                        record = future.result()
                    except Exception as exc:
                        stop_reason = 'worker_error: ' + repr(exc)[:300]
                        stopping[0] = True
                        print(stop_reason, flush=True)
                        continue
                    blocked = blocked + 1 if record['reason'] in {'http_blocked', 'challenge', 'rate_limited'} else 0
                    if record.get('stop_batch') or blocked >= POLICY['stop_after_consecutive_blocks']:
                        stop_reason = record['reason'] if record.get('stop_batch') else '50_consecutive_blocks'
                        stopping[0] = True
                    out.write(json.dumps(record, ensure_ascii=False) + '\n')
                    out.flush()
                    os.fsync(out.fileno())
                    records.append(record)
                    if len(records) % 50 == 0:
                        print(f"{len(records)}/{len(rows)} {record['domain']} {record['decision']} {record['reason']}", flush=True)
                fill()
                if time.monotonic() - last_publish >= 15:
                    publish('pausing' if stopping[0] else 'screening')
                    last_publish = time.monotonic()
        complete = len(records) == len(rows)
        publish('domains_complete' if complete else 'paused' if stop_reason else 'interrupted')
        print(json.dumps({'status': 'domains_complete' if complete else 'stopped', 'completed': len(records), 'stop_reason': stop_reason}), flush=True)
        if not complete:
            raise SystemExit(2)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--site-status', type=Path)
    p.add_argument('--network-config', type=Path, default=pre.NETWORK_CONFIG)
    p.add_argument('--execute', action='store_true')
    run(p.parse_args())
