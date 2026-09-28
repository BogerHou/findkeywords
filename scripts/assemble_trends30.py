#!/usr/bin/env python3
"""Expand lossless browser DOM transcriptions, validating independent checksums."""
import argparse
from datetime import date, timedelta
from urllib.parse import quote
from build_trends30 import RUN, DATES, START, END, dump, read
from trends30_validation import expand_series, keyword_key, require, validate_backgrounds, validate_captures, validate_series, validate_terms


def load_captures():
    captures = []
    for path in sorted(RUN.glob('packed-*.json')):
        items = read(path)
        require(isinstance(items, list), f'{path.name}: expected a list of records')
        for item in items:
            name = item.get('id', path.name)
            validate_terms(item.get('terms'), name)
            if item.get('status') == 'chart':
                require(isinstance(item.get('data'), list), f'{name}: missing chart data')
                series = [expand_series(s, len(DATES), name) for s in item['data']]
                validate_series(series, item.get('checks'), len(item['terms']), len(DATES), name)
            else:
                require(item.get('status') == 'no_data', f'{name}: unknown capture status')
                require(item.get('data', []) == [] and item.get('checks', []) == [], f'{name}: no-data must have empty data/checks')
                series = []
            averages = item.get('averages', [])
            require(isinstance(averages, list) and len(averages) in (0, len(item['terms'])), f'{name}: averages length mismatch')
            captures.append(dict(id=item['id'], captured_at=item['time'], terms=item['terms'],
                chart_terms=item['terms'] if series else [], averages=averages, status=item['status'], dates=DATES if series else [],
                series=series, checks=item.get('checks', []), message=item.get('message'),
                url='https://trends.google.com/trends/explore?date='+quote(START+' '+END, safe='')+'&geo=US&q='+','.join(quote(t, safe='') for t in item['terms'])+'&hl=en',
                source='Google Trends Classic Explore 可访问图表 DOM；查询 URL 按核对过的参数统一编码；非 CSV 导出。'))
    return validate_captures(captures, DATES, START, END)


def load_background(path=None):
    """Keep the original no-argument loader compatible; new records pass a path."""
    path = path or RUN / 'background-packed.json'
    if not path.exists():
        return None
    b = read(path)
    no_data = b.get('status') == 'no_data'
    if no_data:
        require(b.get('nonzero', {}) == {} and b.get('values', []) == [] and b.get('dates', []) == [] and b.get('checks', []) == [], f'{path.name}: no-data must have empty series')
        dates, values = [], []
    else:
        require(b.get('status', 'chart') == 'chart', f'{path.name}: unsupported background status')
        require(type(b.get('count')) is int and b['count'] > 0, f'{path.name}: invalid background count')
        dates = b.get('dates') or [(date.fromisoformat(b['start']) + timedelta(days=i)).isoformat() for i in range(b['count'])]
        values = expand_series(b.get('values', b.get('nonzero')), b['count'], path.name)
        require(b.get('dates_verified') and len(dates) == b['count'], f'{path.name}: background dates unverified/count mismatch')
        if not b.get('dates'):
            require(dates[-1] == b['end'], f'{path.name}: generated dates do not reach verified end')
        validate_series([values], [b.get('checks')], 1, b['count'], path.name)
    old_reason = '半年背景在4月至7月已显示非零搜索信号，因此不能把本窗口的首次非零称为新词诞生。近30日的周均上升仍只是一条待复核线索；不同窗口各自归一化，不能用两张图的指数直接比较规模。'
    fallback = old_reason if path.name == 'background-packed.json' and keyword_key(b['keyword']) == 'custom embroidered patches' else '背景复查已保存；请结合原始记录判断较早信号。不同窗口独立归一化，不能据此比较搜索规模或确认新词。'
    result = {**{k: b[k] for k in ('keyword', 'start', 'end', 'url', 'captured_at')},
        'checks': b.get('checks', []),
        'dates': dates, 'values': values,
        'source': b.get('source') or (f'Google Trends Classic Explore 图表DOM，{len(dates)}个逐日日期标签已在浏览器核对为连续自然日；日期转为ISO展示。' if not b.get('dates') and not no_data else 'Google Trends Classic Explore 实际页面；保留已核对的日期标签或明确无图提示。'),
        'reason': b.get('reason') or (b.get('message') if no_data else fallback)}
    if no_data:
        result.update(status='no_data', message=b.get('message'))
    return validate_backgrounds([result])[0]


def load_backgrounds():
    paths = [RUN / 'background-packed.json'] + sorted(RUN.glob('background-*-packed.json'))
    return validate_backgrounds([load_background(path) for path in paths if path.exists()])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true', help='Validate without writing any snapshot')
    args = parser.parse_args()
    captures, backgrounds = load_captures(), load_backgrounds()
    if not args.check_only:
        dump(RUN / 'captures.json', captures)
        dump(RUN / 'backgrounds.json', backgrounds)
        legacy_background = load_background()
        if legacy_background:
            dump(RUN / 'background.json', legacy_background)
    print(f'Validated {len(captures)} captures, {sum(len(c["series"]) for c in captures)} actual chart series, {len(backgrounds)} backgrounds; '+('no files written' if args.check_only else 'snapshot saved'))


if __name__ == '__main__':
    main()
