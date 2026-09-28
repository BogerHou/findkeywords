#!/usr/bin/env python3
"""Build a reproducible 30-complete-day screening snapshot from saved evidence."""
import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from trends30_validation import capture_time, keyword_key, remaining_coverage, require, validate_backgrounds, validate_captures

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'data/runs/2026-09-26-trends30'
START, END = '2026-08-27', '2026-09-25'
DATES = [(date.fromisoformat(START)+timedelta(days=i)).isoformat() for i in range(30)]
LABELS = {
    'pending': '尚未查询', 'zero': '同图全零，数据不足',
    'no_data': 'Google 未提供图表', 'sparse': '稀疏数据／尖峰',
    'rising': '持续上升候选', 'emerging': '近期连续可见候选',
    'cooling': '近期回落', 'other': '有数据，未达起量规则',
}
RULES = [
    '固定美国、网页搜索、所有类别、搜索字词，2026-08-27 至 2026-09-25 共 30 个完整日。前 16 日为 8/27–9/11，此前 7 日为 9/12–9/18，最近 7 日为 9/19–9/25。',
    '先处理数据不足：30 日全零独立标记；非零少于 5 日，或单日占 30 日指数总和超过 50%，标记稀疏／尖峰。该保守规则可能把早期有大尖峰、近期已经持续的词降级待复核。零值不代表没有搜索；孤峰可能是采样噪声。',
    '持续性初筛：此前 7 日至少 4 个非零日，最近 7 日至少 5 个非零日；最近周的单日峰值不超过该周指数总和的 35%；末 3 日均值不少于此前 4 日均值的 70%。',
    '持续上升候选：通过持续性初筛，最近 7 日均值比此前 7 日及更早 16 日均值均至少高 20%。此前 7 日均值为零时，不计算增长倍数。',
    '近期连续可见候选：达到上述持续上升条件（含最近周比前 16 日均值至少高 20%），且前 16 日最多 2 个非零日。这只是窗口内变得可见，并不证明是新词。仅变得连续但未达升幅的词仍保留原始数据供复核。',
    '连续性不足以入选时，最近周均值比此前周低 20%，或末 3 日均值比此前 4 日低 30%，标记近期回落；其余标记有数据、未达起量规则。',
    '所有阈值均是透明的人工复核优先级，不是显著性检验。5 词同图对比可能让小词取整为零；不同图的 0–100 不能比较搜索量。候选需单词复查及更长历史核查；多词图的全零或无图词仍需单词独立复查，不能据此淘汰或认定没有需求。单次查询不能确认需求或建站机会。',
]

def read(path):
    return json.loads(path.read_text())

def dump(path, obj):
    write_atomic(path, json.dumps(obj, ensure_ascii=False, indent=2)+'\n')

def write_atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, prefix='.'+path.name+'.', delete=False) as tmp:
        name = tmp.name
        tmp.write(text)
    try:
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def remaining_groups():
    groups = []
    for path in sorted(RUN.glob('remaining-*.json')):
        plan = read(path)
        require((plan['start'], plan['end'], plan['geo']) == (START, END, 'US'), f'{path.name}: queue scope mismatch')
        groups.extend(plan['groups'])
    return groups

def capture_disclosures(captures):
    """Descriptive coverage and shape counts only; never changes classifications."""
    multiple, single, rechecked, seen_multiple = set(), set(), set(), set()
    multiple_count = single_count = recheck_count = 0
    latest = {}
    for cap in sorted(captures, key=lambda c: (capture_time(c), c['id'])):
        keys = [keyword_key(word) for word in cap['terms']]
        if len(keys) > 1:
            multiple.update(keys)
            seen_multiple.update(keys)
            multiple_count += 1
        else:
            single.add(keys[0])
            single_count += 1
            if keys[0] in seen_multiple:
                rechecked.add(keys[0])
                recheck_count += 1
        for index, word in enumerate(keys):
            latest[word] = (cap, index)
    nonzero, first_dates, boundary_groups = [], Counter(), set()
    chart_count = no_data_count = early_zero_late = early_zero_all_late = 0
    boundary_examples = []
    for word, (cap, index) in latest.items():
        if cap['status'] == 'no_data':
            no_data_count += 1
            continue
        chart_count += 1
        series = cap['series'][index]
        if not any(series):
            continue
        nonzero.append(word)
        first = next(i for i, value in enumerate(series) if value)
        first_dates[DATES[first]] += 1
        if first == 16:
            boundary_groups.add(cap['id'])
            boundary_examples.append({'keyword': cap['terms'][index], 'captureId': cap['id']})
        if not any(series[:16]):
            early_zero_late += 1
            early_zero_all_late += int(all(value > 0 for value in series[16:]))
    return {'multiTermCoverage': len(multiple), 'multiTermCaptures': multiple_count,
            'singleTermCoverage': len(single), 'singleTermCaptures': single_count,
            'singleTermRecheckCoverage': len(rechecked), 'singleTermRecheckCaptures': recheck_count,
            'comparisonOnlyTerms': len(multiple - single),
            'signalPatternAudit': {
                'basis': '每个词仅用最新主要记录统计；比例分母为有图且至少有一个非零日的词，不重复计入复查。',
                'boundaryDate': DATES[16], 'chartTerms': chart_count, 'noDataTerms': no_data_count,
                'nonzeroChartTerms': len(nonzero), 'allZeroChartTerms': chart_count-len(nonzero),
                'earlyZeroLateNonzeroTerms': early_zero_late,
                'earlyZeroLateAllNonzeroTerms': early_zero_all_late,
                'firstNonzeroOnBoundaryTerms': first_dates[DATES[16]],
                'firstNonzeroOnBoundaryGroups': len(boundary_groups),
                'firstNonzeroDateCounts': dict(sorted(first_dates.items())),
                'boundaryFirstRecords': boundary_examples,
                'note': '多个不同主题的词可能在同一天首次显示非零；这是保存数列的共同形态，原因尚未确认，不能据此认定需求同步诞生。校验和检查的是转录一致性，不能证明 Google 数据代表真实新增需求；同日单查也不等于跨日独立复核。'}}

def mean(values):
    return sum(values)/len(values)

def analyze(s):
    assert len(s)==30 and all(isinstance(v, int) and 0<=v<=100 for v in s)
    early, previous, recent = s[:16], s[16:23], s[23:]
    a,b,c = mean(early),mean(previous),mean(recent)
    total=sum(s)
    nz=lambda x:sum(v>0 for v in x)
    tail, prior = mean(s[-3:]), mean(s[-7:-3])
    m={'earlyMean':a,'previousMean':b,'recentMean':c,'nonzeroDays':nz(s),
       'recentNonzero':nz(recent),'previousNonzero':nz(previous),'earlyNonzero':nz(early),
       'peakShare':max(s)/total if total else None,
       'recentPeakShare':max(recent)/sum(recent) if sum(recent) else None,
       'recentRatio':c/b if b else None,'tailMean':tail,'priorFourMean':prior,
       'recentlyVisible':nz(early)<=2 and nz(previous)>=4 and nz(recent)>=5}
    continuity = (nz(previous)>=4 and nz(recent)>=5 and sum(recent)>0
                  and 20*max(recent)<=7*sum(recent)
                  and 40*sum(s[-3:])>=21*sum(s[-7:-3]))
    if not total:
        status,reason='zero','已取得同图 30 个零值；可能低于报告阈值或被同组大词压低，不能解释为零搜索。'
    elif nz(s)<5 or 2*max(s)>total:
        status,reason='sparse',f'仅 {nz(s)} 个非零日；最大单日占 30 日指数总和 {max(s)/total:.1%}。不能据此认定持续起量。'
    elif continuity and b>0 and 5*sum(recent)>=6*sum(previous) and 40*sum(recent)>=21*sum(early):
        status='emerging' if nz(early)<=2 else 'rising'
        reason='达到本轮持续性和 20% 均值升幅规则；需单词复查与更长历史核验，不代表新词或已确认机会。'
    elif (b>0 and 5*sum(recent)<=4*sum(previous)) or (prior>0 and 40*sum(s[-3:])<21*sum(s[-7:-3])):
        status='cooling'
        reason=(f'最近7日均值 {c:.2f}，比此前7日 {b:.2f} 低 {(1-c/b):.1%}，达到周均回落规则。'
                if b>0 and 5*sum(recent)<=4*sum(previous) else
                f'最后3日均值 {tail:.2f}，比此前4日 {prior:.2f} 低 {(1-tail/prior):.1%}，触发末段回落规则；即使整周均值升高，也暂不认定持续起量。')
    else:
        status,reason='other','有非零记录，但尚未同时满足持续日期、均值升幅和末段保持规则。'
    return status,reason,m

def main():
    rows={}
    terms={}
    skipped=[]
    for part in range(1,4):
        inputs=read(RUN/f'input-{part}.json')
        doc=read(RUN/f'terms-{part}.json')
        assert doc['status']=='complete'
        assert set(doc['reviewed_domains'])=={d['domain'] for d in inputs}
        rows.update({d['domain']:d for d in inputs})
        local_counts=Counter(t['domain'] for t in doc['terms'])
        assert all(v<=2 for v in local_counts.values())
        assert set(local_counts).isdisjoint(s['domain'] for s in doc['skipped'])
        assert set(local_counts)|{s['domain'] for s in doc['skipped']}==set(doc['reviewed_domains'])
        skipped.extend(doc['skipped'])
        for t in doc['terms']+(read(RUN/'query-variants.json') if part==1 else []):
            raw=rows[t['domain']][t['source_field']]
            raw=' '.join(raw) if isinstance(raw,list) else raw
            assert t['evidence_quote'] in raw, t
            key=t['keyword'].strip().casefold()
            if key not in terms:
                terms[key]={'id':hashlib.sha256(key.encode()).hexdigest()[:12],
                            'keyword':t['keyword'],'priority':t['priority'],'theme':t['theme'],
                            'sources':[],'status':'pending','statusLabel':LABELS['pending'],
                            'reason':'已提炼并核对网页原文，尚未取得本轮 30 日趋势。',
                            'captureIds':[],'primaryCaptureId':None,'metrics':None}
            terms[key]['sources'].append({k:v for k,v in t.items() if k not in ('keyword','theme','priority')})
    assert len(rows)==357
    captures=validate_captures(read(RUN/'captures.json'), DATES, START, END)
    groups=remaining_groups()
    coverage=remaining_coverage(groups, captures, terms)
    for cap in captures:
        for i,word in enumerate(cap['terms']):
            key=keyword_key(word)
            assert key in terms, f'Missing source for query: {word}'
            t=terms[key]
            t['captureIds'].append(cap['id'])
            # Validated captures are chronological: the latest real capture is primary.
            t['primaryCaptureId']=cap['id']
            if cap['status']=='chart':
                t['status'],t['reason'],t['metrics']=analyze(cap['series'][i])
            else:
                t['status'],t['reason'],t['metrics']='no_data',cap['message'],None
            t['statusLabel']=LABELS[t['status']]
    background_path=RUN/'background.json'
    backgrounds_path=RUN/'backgrounds.json'
    backgrounds=validate_backgrounds(read(backgrounds_path) if backgrounds_path.exists() else [read(background_path)] if background_path.exists() else [])
    latest_backgrounds={}
    for background in backgrounds:
        key=keyword_key(background['keyword'])
        require(key in terms, f'Background keyword has no webpage source: {background["keyword"]}')
        latest_backgrounds[key]=background
    single_words={keyword_key(c['terms'][0]) for c in captures if len(c['terms'])==1}
    for key, term in terms.items():
        if term['status'] in ('emerging','rising') and key in single_words:
            term['reason']='达到本轮持续性和 20% 均值升幅规则；已保存单词复查记录'+('及更长历史背景' if key in latest_backgrounds else '，仍待更长历史核验')+'，不代表新词或已确认机会。'
    for key, background in latest_backgrounds.items():
        terms[key]['background']=background
        terms[key]['reason']+=' '+background['reason']
    dump(RUN/'public/backgrounds.json',backgrounds)
    if background_path.exists():
        # Keep the original legacy resource, even when another keyword is checked later.
        dump(RUN/'public/background.json',validate_backgrounds([read(background_path)])[0])
    values=list(terms.values())
    counts=Counter(t['status'] for t in values)
    queried=sum(bool(t['captureIds']) for t in values)
    require(queried == len(values)-counts['pending'], 'capture coverage/status mismatch')
    status='complete' if values and queried==len(values) else 'partially_queried' if queried else 'not_queried'
    summary={'reviewedDomains':len(rows),'domainsWithTerms':len({s['domain'] for t in values for s in t['sources']}),
             'skippedDomains':len(skipped),'sourceTermPairs':sum(len(t['sources']) for t in values),
             'terms':len(values),'queried':queried,'pending':len(values)-queried,'status':status,
             'captures':len(captures),'statusCounts':dict(counts),
             'queriedSourceDomains':len({s['domain'] for t in values if t['captureIds'] for s in t['sources']}),
             'backgroundChecks':len(backgrounds),'backgroundKeywords':len(latest_backgrounds),'remainingQueue':coverage,
             **capture_disclosures(captures)}
    initial=[c for c in captures if re.fullmatch(r'g\d{2}', c['id'])]
    initial_words={keyword_key(w) for c in initial for w in c['terms']}
    planned_ids={g['id'] for g in groups}
    queue_words={keyword_key(w) for g in groups for w in g['terms']}
    require(not initial_words.intersection(queue_words), 'initial sample overlaps remaining queue')
    if groups:
        require(initial_words | queue_words == set(terms), 'initial sample plus remaining queue must cover every sourced term')
    history=f'首批 {len(initial_words)} 词由 AI 主观分批选样：优先具体产品、功能和服务需求，兼顾不同主题，保留部分常见词作对照；这段历史不是随机抽样，也不是按已知趋势选赢家。'
    continuation=(f'后续保留原待查队列 {coverage["plannedTerms"]} 词的分组，每组最多 5 词逐组全量核验；出错分组恢复后补查，执行先后见采集时间。当前已保存 {coverage["queriedTerms"]} 词，另有 {coverage["pendingTerms"]} 词待查。'
                  if groups else '待查词仍完整保留；未取得实际记录的词不计为已查询。')
    preparation=[f'{len(rows)} 个域名逐条阅读网页字段，每站最多提炼两个有原文依据的需求词；首组查询另补充 canvas wall art 与 embroidery machines 两个较宽的原文词作对照。AI 提炼含人工判断；保留原文、归一化或翻译说明，不要求命中固定词表，不限定行业。',
                 f'其中 {summary["domainsWithTerms"]} 站提炼出词；{len(skipped)} 站暂不提词，具体理由保存在逐站复核记录。这不等于认定站点违法或没有价值。',
                 history,continuation]
    modes=(f'“已实际查询”按去重词计覆盖，不表示逐个词单独查询。当前多词比较图覆盖 {summary["multiTermCoverage"]} 词（{summary["multiTermCaptures"]} 组），'
           f'单词查询覆盖 {summary["singleTermCoverage"]} 词（{summary["singleTermCaptures"]} 次）；其中在比较图后单词复查覆盖 {summary["singleTermRecheckCoverage"]} 词、{summary["singleTermRecheckCaptures"]} 次。两种覆盖有重叠，不能相加。')
    pattern=summary['signalPatternAudit']
    pattern_rule=(f'形态审计采用每词最新主要记录：{pattern["nonzeroChartTerms"]} 个至少有一个非零日的词中，'
                  f'{pattern["earlyZeroLateNonzeroTerms"]} 个前16日全零，{pattern["firstNonzeroOnBoundaryTerms"]} 个首次非零恰在 {pattern["boundaryDate"]}，'
                  f'{pattern["earlyZeroLateAllNonzeroTerms"]} 个呈现前16日全零、后14日每天非零。'+pattern['note'])
    rules=preparation+[modes]+RULES+['同一词有多条保存记录时，按实际采集时刻采用较新的记录作主要判断，较早记录仍可展开核查。保存的全零图和 Google 明确无图提示均属已实际查询；只有前者有可计算的指数数列。',pattern_rule]
    brief=lambda c:{k:c[k] for k in ('id','terms','captured_at','status')}
    selection={'type':'首批主观选样历史＋原待查队列全量核验','status':status,
               'rationale':history+' '+continuation,
               'initial_sample':{'terms':len(initial_words),'rationale':history,'groups':[brief(c) for c in initial]},
               'remaining_queue':{**coverage,'rationale':continuation,'groups':groups},
               'groups':[brief(c) for c in captures if c['id'] in planned_ids or c in initial],
               'rechecks':[brief(c) for c in captures if c['id'] not in planned_ids and c not in initial],
               'recheck_reason':'保存实际追加的复查记录，具体范围以词和查询时间为准；同日复查并非跨日独立采样。'}
    dump(RUN/'public/selection.json',selection)
    session_path = RUN/'query-session.json'
    collection = read(session_path) if session_path.exists() else {}
    collection.update(queried=queried, pending=summary['pending'],
                      pendingGroups=[g for g in groups if g['id'] in coverage['missingGroupIds']],
                      pendingKeywords=[t['keyword'] for t in values if not t['captureIds']],
                      pendingCandidateRechecks=[t['keyword'] for t in values
                          if t['status'] in ('emerging','rising') and not any(
                              len(c['terms']) == 1 and t['keyword'] in c['terms'] for c in captures)])
    if not summary['pending']:
        collection['status'] = 'queue_complete'
    dump(RUN/'public/query-session.json', collection)
    doc={'meta':{'start':START,'end':END,'geo':'美国','searchType':'网页搜索','status':status,
                 'latestCaptureAt':max(captures,key=capture_time)['captured_at'] if captures else None,
                 'captureMethod':'Google Trends Classic Explore 实际页面的可访问图表表格，DOM 数值抄录；非 CSV 导出。保存查询链接、时间、同图词、日期与两项校验和。'},
         'summary':summary,'rules':rules,'terms':values,'captures':captures,'backgrounds':backgrounds,'collection':collection,
         'resources':[{'title':'30日结果与原文依据','path':'trends30-data.json','description':f'{len(values)} 个词；{queried} 个已查，{summary["pending"]} 个待查；逐日数据与判断规则'},
                      {'title':'选样历史、全量队列与复查记录','path':'../data/runs/2026-09-26-trends30/public/selection.json','description':f'首批 {len(initial_words)} 词选样历史；原待查 {coverage["plannedTerms"]} 词的逐组覆盖和实际复查范围'},
                      {'title':'浏览器数列记录','path':'../data/runs/2026-09-26-trends30/public/captures.json','description':'实际查询参数、时间、30日序列及转录核验摘要'},
                      {'title':'查询状态与剩余名单','path':'../data/runs/2026-09-26-trends30/public/query-session.json','description':f'{summary["pending"]} 个词未取得有效结果；保留分组和待单词复查的候选'},
                      {'title':'浏览器参数与日期核验','path':'../data/runs/2026-09-26-trends30/public/browser-validation.json','description':'保存实际浏览器URL、日期标签与逐组审计覆盖'},
                      {'title':'半年背景复查记录','path':'../data/runs/2026-09-26-trends30/public/backgrounds.json','description':f'{len(backgrounds)} 次保存记录，涉及 {len(latest_backgrounds)} 个词；同词较早背景仍保留'}]}
    dump(ROOT/'site/trends30-data.json',doc)
    write_atomic(ROOT/'site/trends30-data.js','window.FINDKEYWORDS_TRENDS30 = '+json.dumps(doc,ensure_ascii=False)+';\n')
    dump(RUN/'public/captures.json',captures)
    dump(RUN/'public/method.json',{'summary':summary,'rules':rules})
    protocol_path=ROOT/'data/runs/2026-09-26-tld/trend-protocol.json'
    if protocol_path.exists():
        protocol=read(protocol_path)
        protocol.update(status=status,result_run=RUN.name,result_page='http://127.0.0.1:8878/site/#trends30',
                        coverage_note=f'原始网页片段整理为 {len(values)} 个去重搜索词；实际查询 {queried} 词，另有 {summary["pending"]} 词待查。'+history+' '+continuation,
                        coverage=summary,query_selection=selection['rationale'])
        dump(protocol_path,protocol)
        dump(protocol_path.parent/'public/trend-protocol.json',protocol)
    dump(RUN/'private-validation.json',{'reviewed':len(rows),'skipped':skipped,'status':'verified'})
    report=['# 近30天趋势核验 · 2026-09-26','',
        f'本轮逐站阅读{len(rows)}个域名，{summary["domainsWithTerms"]}站提炼出{len(values)}个去重搜索词，{len(skipped)}站暂不提词。实际查询{summary["queried"]}词，{summary["pending"]}词仍待查。',
        f'查询窗口：{START} 至 {END}；美国、网页搜索、全部类别、搜索字词。保存{len(captures)}组30日记录，另有{summary["backgroundChecks"]}次背景复查。','',
        '结果：'+'；'.join(f'{LABELS[k]} {v}词' for k,v in counts.items() if k!='pending')+'。','',
        '词来自实际网页Title、Description、H1或正文；没有限定为软件行业。全部来源与逐日数值见工作台。',
        '工作台：http://127.0.0.1:8878/site/#trends30','',
        *([f'查询受限：{collection["message"]}（{collection["observedAt"]}）。剩余{summary["pending"]}词仍为待查，未把错误记作数据不足。',''] if collection.get('status')=='temporarily_blocked' else []),
        *['- '+r for r in rules],'',
        '| 已查关键词 | 本轮状态 | 前16日 / 前7日 / 末7日均值 | 主要记录 |',
        '|---|---|---|---|']
    for t in values:
        if not t['captureIds']: continue
        m=t['metrics']
        means=' / '.join(f'{m[k]:.2f}' for k in ('earlyMean','previousMean','recentMean')) if m else 'Google无图，未计算'
        report.append(f'| {t["keyword"]} | {t["statusLabel"]} | {means} | {t["primaryCaptureId"]} |')
    for background in backgrounds:
        report+=['',f'背景复查：{background["keyword"]} · {background["start"]} 至 {background["end"]} · {background["captured_at"]}',
                 background['reason'],background['url']]
    write_atomic(ROOT/'reports/trends30-2026-09-26.md','\n'.join(report)+'\n')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':
    main()
