"""Persistent pacing for browser work; this module never sends network requests."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import fcntl
import json
import os
from pathlib import Path

from probe_full import atomic_json

POLICY = {'query_interval_seconds': 60, 'initial_cooldown_seconds': 3600,
          'maximum_cooldown_seconds': 86400, 'healthy_queries_before_reset': 6}


def utcnow():
    return datetime.now(timezone.utc)


def stamp(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timestamp needs an explicit timezone')
    return parsed.astimezone(timezone.utc)


def availability(control, now):
    if not control.get('pacing_enabled') or control.get('status') == 'blocked':
        return {'allowed': False, 'state': 'blocked', 'reason': control.get('reason', 'Explicit resume required')}
    if control.get('inflight'):
        return {'allowed': False, 'state': 'awaiting_capture', 'inflight': control['inflight'],
                'reason': 'Inspect/save the existing browser query; do not submit it again.'}
    due = stamp(control['next_allowed_at'])
    if now < due:
        return {'allowed': False, 'state': 'cooling_down' if control['status'] == 'cooldown' else 'waiting_interval',
                'next_allowed_at': due.isoformat(), 'seconds_remaining': (due - now).total_seconds()}
    return {'allowed': True, 'state': 'ready', 'next_allowed_at': due.isoformat()}


def retry_deadline(value, now):
    if not value:
        return now
    try:
        return now + timedelta(seconds=max(0, int(value)))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (ValueError, TypeError, OverflowError):
            return now  # Still apply the full exponential cooldown.
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(now, parsed.astimezone(timezone.utc))


class Pacer:
    def __init__(self, root, clock=utcnow):
        self.root = Path(root)
        self.clock = clock
        self.path = self.root / 'control.json'

    def read(self):
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    @contextmanager
    def locked(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / '.pacing.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def save(self, control, event, **details):
        atomic_json(self.path, control)
        with (self.root / 'pacing-events.jsonl').open('a') as log:
            log.write(json.dumps({'event': event, 'at': self.clock().isoformat(), **details}, ensure_ascii=False) + '\n')
            log.flush()
            os.fsync(log.fileno())

    def resume(self, not_before, reason):
        with self.locked():
            old = self.read()
            if old.get('inflight'):
                raise ValueError('Resolve existing browser capture before resuming')
            now = self.clock()
            due = max(now, stamp(not_before))
            control = {**old, 'pacing_enabled': True, 'policy': POLICY,
                       'status': 'cooldown' if due > now else 'active',
                       'next_allowed_at': due.isoformat(), 'resume_reason': reason,
                       'resumed_at': now.isoformat(), 'inflight': None,
                       'rate_limit_level': max(1, old.get('rate_limit_level', 0)), 'healthy_queries': 0}
            self.save(control, 'user_authorized_resume', reason=reason, previous_state=old)
            return availability(control, now)

    def claim(self, item):
        with self.locked():
            control, now = self.read(), self.clock()
            decision = availability(control, now)
            if not decision['allowed']:
                return decision
            if item is None:
                return {'allowed': False, 'state': 'queue_complete'}
            claim = {**item, 'claimed_at': now.isoformat()}
            control.update(status='active', inflight=claim,
                           next_allowed_at=(now + timedelta(seconds=POLICY['query_interval_seconds'])).isoformat())
            self.save(control, 'query_slot_reserved', **claim,
                      note='Reservation is not proof a Google request was sent.')
            return {'allowed': True, 'state': 'reserved', **claim,
                    'next_allowed_at': control['next_allowed_at']}

    def require_claim(self, keyword, stage):
        control = self.read()
        if control.get('pacing_enabled'):
            claim = control.get('inflight') or {}
            if claim.get('keyword') != keyword or claim.get('stage') != stage:
                raise ValueError('This import needs its matching reserved query slot')

    def success(self, keyword, stage):
        with self.locked():
            self.require_claim(keyword, stage)
            control = self.read()
            if not control.get('pacing_enabled'):
                return
            healthy = control.get('healthy_queries', 0) + 1
            level = 0 if healthy >= POLICY['healthy_queries_before_reset'] else control.get('rate_limit_level', 0)
            control.update(inflight=None, healthy_queries=healthy, rate_limit_level=level,
                           last_completed_at=self.clock().isoformat())
            # Space from completion too: preparing or downloading a chart must
            # never compress the next submission below the one-minute interval.
            control['next_allowed_at'] = max(stamp(control['next_allowed_at']),
                self.clock() + timedelta(seconds=POLICY['query_interval_seconds'])).isoformat()
            self.save(control, 'capture_imported', keyword=keyword, stage=stage)

    def cooldown(self, reason, retry_after=None):
        with self.locked():
            control, now = self.read(), self.clock()
            level = control.get('rate_limit_level', 0) + 1
            delay = min(POLICY['maximum_cooldown_seconds'],
                        POLICY['initial_cooldown_seconds'] * 2 ** min(level - 1, 10))
            due = max(now + timedelta(seconds=delay), retry_deadline(retry_after, now))
            old_claim = control.get('inflight')
            control.update(status='cooldown', next_allowed_at=due.isoformat(),
                           inflight=None, rate_limit_level=level, healthy_queries=0,
                           last_rate_limit_at=now.isoformat(), last_rate_limit_reason=reason,
                           retry_after=retry_after)
            self.save(control, 'cooldown_started', reason=reason, failed_slot=old_claim,
                      next_allowed_at=due.isoformat(), retry_after=retry_after)
            return availability(control, now)

    def block(self, reason):
        with self.locked():
            control = self.read()
            old_claim = control.get('inflight')
            control.update(status='blocked', reason=reason, at=self.clock().isoformat(), inflight=None)
            self.save(control, 'blocked', reason=reason, failed_slot=old_claim)
