"""Shared, read-only validation for saved Trends transcriptions and coverage."""
from datetime import date, datetime
from urllib.parse import parse_qs, urlparse


def require(condition, message):
    if not condition:
        raise ValueError(message)


def keyword_key(word):
    return word.strip().casefold()


def capture_time(capture):
    stamp = capture.get('captured_at', capture.get('time'))
    require(isinstance(stamp, str), f'{capture.get("id")}: missing capture time')
    value = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
    require(value.tzinfo is not None, f'{capture.get("id")}: capture time needs timezone')
    return value


def validate_terms(terms, context):
    require(isinstance(terms, list) and 1 <= len(terms) <= 5, f'{context}: expected 1–5 terms')
    require(all(isinstance(t, str) and t.strip() for t in terms), f'{context}: empty query term')
    require(len({keyword_key(t) for t in terms}) == len(terms), f'{context}: duplicate query term')


def validate_series(series, checks, term_count, day_count, context):
    require(isinstance(series, list) and isinstance(checks, list), f'{context}: series/checks must be lists')
    require(len(series) == len(checks) == term_count, f'{context}: terms/series/checks length mismatch')
    for index in range(term_count):
        values, check = series[index], checks[index]
        require(isinstance(values, list) and len(values) == day_count, f'{context}[{index}]: wrong day count')
        require(all(type(v) is int and 0 <= v <= 100 for v in values), f'{context}[{index}]: invalid index value')
        require(isinstance(check, list) and len(check) == 2 and all(type(v) is int for v in check), f'{context}[{index}]: invalid checksum')
        expected = [sum(values), sum((i + 1) * v for i, v in enumerate(values))]
        require(expected == check, f'{context}[{index}]: checksum mismatch')


def expand_series(value, day_count, context):
    if isinstance(value, list):
        return value
    require(isinstance(value, dict), f'{context}: expected full list or lossless sparse index map')
    require(all(isinstance(k, str) and k.isdecimal() and str(int(k)) == k and 0 <= int(k) < day_count for k in value), f'{context}: invalid sparse index')
    # In chart records only, omitted positions in the saved sparse map encode observed zeros.
    return [value.get(str(i), 0) for i in range(day_count)]


def validate_captures(captures, dates, start, end):
    require(isinstance(captures, list), 'captures must be a list')
    ids = [c.get('id') for c in captures]
    require(all(isinstance(i, str) and i for i in ids), 'missing capture id')
    require(len(ids) == len(set(ids)), 'duplicate capture id')
    for cap in captures:
        name = cap['id']
        capture_time(cap)
        validate_terms(cap.get('terms'), name)
        q = parse_qs(urlparse(cap.get('url', '')).query)
        require(q.get('geo') == ['US'] and q.get('date') == [start + ' ' + end], f'{name}: query scope mismatch')
        require(q.get('gprop', ['']) == [''] and q.get('cat', ['0']) == ['0'], f'{name}: property/category mismatch')
        require([keyword_key(x) for x in q.get('q', [''])[0].split(',')] == [keyword_key(x) for x in cap['terms']], f'{name}: URL terms mismatch')
        if cap.get('status') == 'chart':
            require(cap.get('chart_terms') == cap['terms'] and cap.get('dates') == dates, f'{name}: chart terms/dates mismatch')
            validate_series(cap.get('series'), cap.get('checks'), len(cap['terms']), len(dates), name)
        else:
            require(cap.get('status') == 'no_data' and isinstance(cap.get('message'), str) and cap['message'].strip(), f'{name}: no-data record needs Google message')
            require(all(cap.get(field) == [] for field in ('series', 'checks', 'dates', 'chart_terms')), f'{name}: no-data must not contain synthetic series')
    return sorted(captures, key=lambda c: (capture_time(c), c['id']))


def remaining_coverage(groups, captures, known_terms=None):
    """Compare the immutable remaining queue with exact saved capture groups."""
    group_ids = [g['id'] for g in groups]
    require(len(group_ids) == len(set(group_ids)), 'duplicate remaining group id')
    words = [keyword_key(t) for g in groups for t in g['terms']]
    require(len(words) == len(set(words)), 'duplicate term in remaining queue')
    if known_terms is not None:
        require(set(words) <= set(known_terms), 'remaining queue contains terms without webpage evidence')
    actual = {c['id']: c for c in captures}
    complete, pending = [], []
    for group in groups:
        validate_terms(group['terms'], group['id'])
        cap = actual.get(group['id'])
        if cap is None:
            pending.append(group['id'])
            continue
        require(cap['terms'] == group['terms'], f'{group["id"]}: captured terms/order differ from remaining queue')
        complete.append(group['id'])
    queried = sum(len(g['terms']) for g in groups if g['id'] in complete)
    return {'plannedTerms': len(words), 'queriedTerms': queried, 'pendingTerms': len(words) - queried,
            'plannedGroups': len(groups), 'capturedGroups': len(complete), 'missingGroupIds': pending,
            'duplicatePlannedTerms': 0}


def validate_backgrounds(backgrounds):
    require(isinstance(backgrounds, list), 'backgrounds must be a list')
    identities = set()
    for background in backgrounds:
        word = background.get('keyword')
        require(isinstance(word, str) and word.strip(), 'background needs a keyword')
        context = 'background: ' + word
        stamp = capture_time(background)
        start, end = date.fromisoformat(background['start']), date.fromisoformat(background['end'])
        require(start <= end, f'{context}: invalid date window')
        identity = (keyword_key(word), stamp, start, end)
        require(identity not in identities, f'{context}: duplicate keyword/time/window record')
        identities.add(identity)
        query = parse_qs(urlparse(background['url']).query)
        require(query.get('geo') == ['US'] and query.get('date') == [background['start']+' '+background['end']], f'{context}: URL scope mismatch')
        require(query.get('gprop', ['']) == [''] and query.get('cat', ['0']) == ['0'], f'{context}: property/category mismatch')
        require(len(query.get('q', [])) == 1 and keyword_key(query['q'][0]) == keyword_key(word), f'{context}: URL keyword mismatch')
        require(isinstance(background.get('reason'), str) and background['reason'].strip(), f'{context}: missing interpretation/boundary note')
        dates, values = background.get('dates'), background.get('values')
        require(isinstance(dates, list) and isinstance(values, list) and len(dates) == len(values), f'{context}: dates/values length mismatch')
        if values:
            require(background.get('status', 'chart') == 'chart', f'{context}: chart status mismatch')
            parsed = [date.fromisoformat(label) for label in dates]
            require(parsed == sorted(set(parsed)) and parsed[0] >= start and parsed[-1] <= end, f'{context}: invalid dates/order')
            validate_series([values], [background.get('checks')], 1, len(dates), context)
        else:
            require(background.get('status') == 'no_data' and background.get('message'), f'{context}: empty series needs explicit no-data message')
            require(background.get('checks') == [], f'{context}: no-data must have empty checks')
    return sorted(backgrounds, key=lambda b: (capture_time(b), keyword_key(b['keyword'])))
