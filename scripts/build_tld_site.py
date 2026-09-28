#!/usr/bin/env python3
"""Build the independent suffix/name experiment from saved evidence only."""
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'data/runs/2026-09-26-tld'

def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default

def jsonl(path):
    rows = []
    if path.exists():
        lines = path.read_text().splitlines()
        for i, line in enumerate(lines):
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                if i != len(lines)-1:
                    raise
    return rows

def atomic(path, text):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(text, encoding='utf-8')
    tmp.replace(path)

def main():
    acquisition = read(ROOT/'data/raw/month-2026-09-26/manifest.json')
    screen = read(RUN/'screening/manifest.json', {})
    selected = read(RUN/'screening/probe_candidates.json', [])
    probe_meta = read(RUN/'probe-manifest.json', {})
    rows = jsonl(RUN/'probes.jsonl')
    previous = {r['domain'] for r in jsonl(RUN/'prior-probed.jsonl')}
    assert len({r['domain'] for r in rows}) == len(rows), 'Duplicate probe records'
    selected_names = {r['domain'] for r in selected}
    assert not (selected_names & previous), 'Previously probed domain in new queue'
    assert all(r['domain'] in selected_names for r in rows), 'Probe outside selection'
    audit = read(RUN/'content-audit.json', {})
    tag_map = {}
    for path in [RUN/'research-tags-part1.json', RUN/'content-audit-part3.json']:
        doc = read(path, {})
        for tag in doc.get('tags', doc.get('research_tags', [])):
            assert tag['category'] in {'adult', 'gambling'}
            tag_map.setdefault(tag['domain'], set()).add(tag['category'])
    for note in read(RUN/'content-audit-part2.json', {}).get('content_risk_notes', []):
        tag_map.setdefault(note['domain'], set()).add('adult')
    # Unreviewed non-candidates must not publish potentially explicit source
    # material. This is a display precaution, not a website-quality verdict.
    public_guard = re.compile(r'\b(?:porn(?:ography)?|xxx|hentai|jav|bokep|casino|slot gacor)\b|成人视频|成人影片|成人视频|成人内容|色情|偷拍|迷奸|幼女|亂倫|亂倫|乱伦|线上赌场|博彩', re.I)
    guarded = set()
    for r in rows:
        text = ' '.join([r.get('title',''), r.get('description',''), *r.get('h1',[]), r.get('visible_text','')])
        if r['verdict'] != 'candidate' and r['domain'] not in tag_map and public_guard.search(text):
            tag_map[r['domain']] = {'content_review'}
            guarded.add(r['domain'])
    aliases = {d:'隔离记录-'+hashlib.sha256(d.encode()).hexdigest()[:12] for d in tag_map}
    audited = set(audit.get('reviewed_domains', []))
    overrides = {f['domain']: f for f in audit.get('findings', [])}
    assert audited <= {r['domain'] for r in rows}
    assert set(overrides) <= audited
    labels = {'parked':'停放或未正式开放', 'thin':'页面内容不足', 'unavailable':'未取得可用页面'}
    channels = screen.get('channels', [])
    channel_labels = {c['id']: c['label'] for c in channels}
    domains = []
    for r in sorted(rows, key=lambda r:r.get('queue_rank', 999999)):
        r['automatic_verdict'] = r['verdict']
        if r['domain'] in audited:
            r['review_status'] = 'ai_content_reviewed'
        if r['domain'] in overrides:
            f = overrides[r['domain']]
            raw = r.get(f['evidence_field'], '')
            raw = ' '.join(raw) if isinstance(raw, list) else raw
            assert f['evidence_quote'] in raw, 'Content correction quote missing'
            assert f['recommended_verdict'] in labels
            r['verdict'] = f['recommended_verdict']
            r['verdict_label'] = labels[r['verdict']]
            r['reasons'] = ['AI内容复核：'+f['reason']+' 原文：'+f['evidence_quote'],
                            *['自动初判：'+s for s in r.get('reasons', [])]]
        for k in r.get('keyword_candidates', []):
            raw = r.get(k['field'], '')
            raw = ' '.join(raw) if isinstance(raw, list) else raw
            assert k['quote'] in raw and k['phrase'] == k['quote'], 'Unbacked phrase'
        domains.append({
            'domain':r['domain'], 'sourceDates':[r.get('source_date')],
            'channel':r.get('channel'), 'channelLabel':channel_labels.get(r.get('channel'), r.get('channel')),
            'selectionReason':r.get('selection_reason'), 'verdict':r['verdict'], 'verdictLabel':r.get('verdict_label'),
            'reasons':r.get('reasons', []), 'registrationStatus':r.get('registration_status'),
            'registrationDate':r.get('registration_date'), 'registrationSource':r.get('registration_source'),
            'registrationError':r.get('registration_error'), 'httpStatus':r.get('http_status'),
            'fetchStatus':r.get('fetch_status'), 'fetchError':r.get('fetch_error'), 'finalUrl':r.get('final_url'),
            'fetchedAt':r.get('fetched_at'), 'title':r.get('title', ''), 'description':r.get('description', ''),
            'h1':r.get('h1', []), 'visibleText':r.get('visible_text', ''),
            'redirected':r.get('redirected', False), 'redirectedExternal':r.get('redirected_external', False),
            'keywordCandidates':r.get('keyword_candidates', []), 'launchStatus':'unverified',
            'reviewStatus':r.get('review_status', 'automatic'),
            'nameEvidence':r.get('dictionary_segments', []), 'namePath':r.get('name_path'),
            'dictionarySegments':r.get('dictionary_segments', []),
            'legacyMatches':r.get('name_matches', []), 'expandedMatches':r.get('additional_name_matches', [])
        })
        d = domains[-1]
        d.update(researchExcluded=r['domain'] in tag_map, researchCategories=sorted(tag_map.get(r['domain'], set())), sensitiveSuppressed=r['domain'] in tag_map)
        if d['researchExcluded']:
            d.update(domain=aliases[r['domain']], title='已移出本轮研究范围', description='', h1=[], visibleText='', keywordCandidates=[],
                     finalUrl=None, registrationSource=None, selectionReason='名称与原文不在公开工作台展示；抽样位置保留于本地审计。',
                     nameEvidence=[], dictionarySegments=[], legacyMatches=[], expandedMatches=[],
                     reasons=['本轮暂跳过成人与博彩内容；此项不改变页面是否存在的事实判定。'],
                     researchNote='本轮暂跳过成人与博彩内容。风险记录的原文、地址和趋势查询入口已隔离。', fetchError=None, registrationError=None)
            if r['domain'] in guarded:
                d.update(researchNote='未进入候选的原始页面命中敏感内容展示规则，暂不公开原文，待另行复核；不作违法或低价值判断。',
                         reasons=['公开展示暂隔离，原始技术判定保留。'])
    candidates = [d for d in domains if d['verdict'] == 'candidate']
    research_candidates = [d for d in candidates if not d['researchExcluded']]
    phrases = [k for d in candidates for k in d['keywordCandidates']]
    verdicts = Counter(r['verdict'] for r in rows)
    reg = Counter(r.get('registration_status') for r in rows)
    counts = screen.get('counts', {})
    summary = {
        'rawRows':acquisition['raw_rows'], 'uniqueDomains':counts.get('unique_valid_domains', 2096176),
        'downloadedDays':acquisition['downloaded_days'], 'requestedDays':acquisition['requested_days'],
        'probeSelected':len(selected), 'probed':len(rows), 'remaining':len(selected)-len(rows),
        'httpsAccessible':sum(r.get('fetch_status') == 'ok' for r in rows),
        'substantivePages':sum(r.get('substantive', False) for r in rows),
        'verifiedRecent':reg['verified_recent'], 'verifiedOld':reg['verified_old'],
        'registrationUnknown':reg['unknown'], 'registrationNotChecked':reg['not_checked'],
        'candidates':len(candidates), 'keywordPhrases':len(phrases),
        'uniqueKeywordPhrases':len({k['phrase'].casefold() for k in phrases}), 'verdicts':dict(verdicts),
        'automaticCandidates':sum(r['automatic_verdict'] == 'candidate' for r in rows),
        'contentReviewed':len(audited), 'contentCorrections':len(overrides),
        'contentReviewRemaining':sum(r['automatic_verdict'] == 'candidate' for r in rows)-len(audited),
        'researchCandidates':len(research_candidates), 'researchExcluded':len(candidates)-len(research_candidates),
        'publicationSuppressed':len(aliases), 'noncandidateDisplayReview':len(guarded),
        'researchUniqueKeywordPhrases':len({k['phrase'].casefold() for d in research_candidates for k in d['keywordCandidates']}),
        'newToPriorProbes':len(candidates), 'priorProbeOverlap':0,
        'eligibleNames':counts.get('name_eligible_domains'),
        'previousProbeOverlap':counts.get('excluded_previously_probed'),
        'selectedWithoutLegacyTerms':counts.get('selected_without_legacy_terms'),
        'selectedWithoutAnyTerms':counts.get('selected_without_any_terms'),
    }
    rules = screen.get('rules', {})
    channel_rules = {c['id']:c['condition'] for c in rules.get('channel_rules', [])}
    notes = rules.get('limitations', []) + [
        '后缀分组仅用于分配检查名额，不代表权威、注册成本或Google排名优势。其他后缀同样保留探索名额。',
        '词典分词、可读造词和短名称都是粗筛线索，不能判断真实含义、恶意行为或网站商业价值。',
        '与前轮已实探域名去重；两个方法的抽样池和配额不同，候选比例不能作为严格优劣实验结论。',
        '按与月度轮相同的页面和RDAP规则核验；AI内容复核单独保存且保留自动初判。',
        '网页Title、Description和H1原文片段尚未整理成最终搜索词，本轮Google Trends、流量及竞争度均未核验。',
        'Trends以最近30个完整日判断近期是否持续起量，半年仅作辅助背景；较早的0可能是低于展示阈值，不能断言之前无人搜索。',
        '孤立尖峰可能来自统计噪声；第一次非零仅是查询窗口内首次可见，仍需更长历史和多日持续性核对。',
        '后续研究暂跳过明确成人与博彩类别；这是研究范围假设，不是对所有此类网站的质量判定。公开记录用中性编号替代这些域名，不展示其原文、地址或趋势入口。',
    ]
    done = len(rows) == len(selected) and bool(selected) and probe_meta.get('status') == 'complete' and audit.get('status') == 'complete'
    public = RUN/'public'
    public.mkdir(exist_ok=True)
    def neutralize(value):
        if isinstance(value, dict):return {k:neutralize(v) for k,v in value.items()}
        if isinstance(value, list):return [neutralize(v) for v in value]
        if isinstance(value, str):
            for domain, alias in aliases.items():value=value.replace(domain,alias)
        return value
    public_audit = {k:neutralize(v) for k,v in audit.items() if k != 'findings'}
    public_audit['findings'] = [neutralize(f) if f['domain'] not in aliases else {'domain':aliases[f['domain']], 'recommended_verdict':f['recommended_verdict'], 'reason':'研究范围外记录；具体名称及引文已隐藏。', 'evidence_redacted':True} for f in audit.get('findings', [])]
    public_audit['public_note']='公开审计保留数量与非隔离记录原文；研究范围外记录已中性化。完整采集文件仅保留在本地，不由网站提供。'
    public_selection = [r if r['domain'] not in aliases else {'domain':aliases[r['domain']], 'queue_rank':r['queue_rank'], 'channel':r['channel'], 'source_date':r['source_date'], 'sensitiveSuppressed':True} for r in selected]
    for filename, obj in [('screening-manifest.json',neutralize(screen)), ('selection.json',public_selection), ('content-audit.json',public_audit), ('probe-manifest.json',probe_meta), ('trend-protocol.json',read(RUN/'trend-protocol.json',{})), ('screening-verification.json',neutralize(read(RUN/'screening-verification.json',{})))]:
        atomic(public/filename, json.dumps(obj, ensure_ascii=False, indent=2)+'\n')
    atomic(public/'records.json', json.dumps(domains, ensure_ascii=False)+'\n')
    resources = [
        ('新通道审计报告', '筛选数量、规则、两轮关系与实际结果。', 'reports/tld-2026-09-26.md', 'report'),
        ('全部核验结果 CSV', '含失败与排除项、页面字段和每条判定依据。', 'reports/tld-domains-2026-09-26.csv', 'data'),
        ('候选网页原文 CSV', '原文片段与证据字段；不等于已验证的新词。', 'reports/tld-keywords-2026-09-26.csv', 'data'),
        ('完整名称规则与抽样清单', 'TLD分组、词典、形态排除及固定哈希抽样。', 'data/runs/2026-09-26-tld/public/screening-manifest.json', 'data'),
        ('入选记录公开版', '来源、分词与队列次序；范围外域名以中性编号替代。', 'data/runs/2026-09-26-tld/public/selection.json', 'data'),
        ('页面与注册公开记录', '保留可研究页面的字段；隔离记录没有原文或地址。', 'data/runs/2026-09-26-tld/public/records.json', 'evidence'),
        ('页面内容复核公开版', '复核覆盖、改判依据；范围外记录不展示原文。', 'data/runs/2026-09-26-tld/public/content-audit.json', 'audit'),
        ('核验运行及固定窗口', '复用原月度核验时间窗口；实际抓取时间逐项保存。', 'data/runs/2026-09-26-tld/public/probe-manifest.json', 'data'),
        ('独立筛选验收', '源行定位、词表独立性和抽样重算。', 'data/runs/2026-09-26-tld/public/screening-verification.json', 'audit'),
        ('近30天持续起量复核方法', '30天为主要窗口、半年作背景；尚未运行趋势查询。', 'data/runs/2026-09-26-tld/public/trend-protocol.json', 'data'),
    ]
    result = {
        'meta':{'runId':'2026-09-26-tld', 'runDate':'2026-09-26', 'generatedAt':datetime.now(timezone.utc).isoformat(),
                'status':'complete' if done else 'running', 'title':'通过后缀与名称，发现另一批网站。',
                'subtitle':'独立于业务词表的名称探索；后缀决定抽样名额，实际网页决定内容判断。',
                'windowStart':acquisition['window_start'], 'windowEnd':acquisition['window_end'],
                'registrationCutoff':probe_meta.get('registration_cutoff'),
                'registrationReferenceTime':probe_meta.get('registration_reference_time'),
                'sourceNote':'复用同一批30份WhoisDS免费日名单；供应商子集，不是全球全量。',
                'launchNote':'近期注册且当前有内容，不等于确认首次在本月上线。'},
        'summary':summary,
        'screening':{'method':screen.get('audit_reproduction', '筛选尚未完成'),
                     'channels':[{'id':c['id'], 'label':c['label'], 'eligible':c['all_valid_count'],
                                  'selected':c['final_quota'], 'quota':str(c['share_percent'])+'%',
                                  'rule':channel_rules.get(c['id'], ''),
                                  'results':dict(Counter(r['verdict'] for r in rows if r.get('channel') == c['id']))} for c in channels],
                     'notes':notes, 'tldGroups':[{'label':g['label'], 'tlds':g['suffixes'], 'quota':str(g['percent'])+'%', 'fallback':g.get('fallback',False)} for g in rules.get('suffix_groups', [])],
                     'nameRules':[{'label':g['id'], 'rule':g['condition']} for g in screen.get('name_rules', [])],
                     'tldCounts':screen.get('tld_counts', []), 'exclusions':screen.get('rejection_counts', {}),
                     'exclusionLabels':rules.get('ordered_exclusions', {})},
        'acquisition':{'sourceName':'WhoisDS 免费日名单', 'sourceUrl':'https://www.whoisds.com/newly-registered-domains',
                       'windowStart':acquisition['window_start'], 'windowEnd':acquisition['window_end'],
                       'batches':acquisition['batches'], 'coverageNote':acquisition['coverage_note']},
        'domains':domains,
        'resources':[{'title':t, 'description':d, 'path':'../'+p, 'type':k} for t,d,p,k in resources if (ROOT/p).exists() or p.endswith('tld-2026-09-26.md')],
    }
    def cell(v):
        s = '' if v is None else str(v)
        return "'"+s if s.lstrip()[:1] in {'=', '+', '-', '@'} else s
    with (ROOT/'reports/tld-domains-2026-09-26.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f); w.writerow(['域名','名单日期','通道','判定','原因','注册日期','注册状态','页面URL','Title','Description','H1','名称选择依据','首次上线'])
        for d in domains:
            w.writerow(map(cell, [d['domain'],';'.join(filter(None,d['sourceDates'])),d['channelLabel'],d['verdictLabel'],
                                  ';'.join(d['reasons']),d['registrationDate'],d['registrationStatus'],d['finalUrl'],
                                  d['title'],d['description'],';'.join(d['h1']),d['selectionReason'],'未核实']))
    with (ROOT/'reports/tld-keywords-2026-09-26.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f); w.writerow(['域名','网页原文片段','字段','原文','页面URL','Trends状态'])
        for d in research_candidates:
            for k in d['keywordCandidates']:
                w.writerow(map(cell, [d['domain'],k['phrase'],k['field'],k['quote'],d['finalUrl'],'待整理搜索词；未查询Trends']))
    payload = json.dumps(result, ensure_ascii=False, separators=(',', ':'))
    atomic(ROOT/'site/tld-data.json', payload+'\n')
    atomic(ROOT/'site/tld-data.js', 'window.FINDKEYWORDS_TLD = '+payload+';\n')
    lines = ['# 后缀与名称独立通道（2026-09-26）', '',
             '状态：'+result['meta']['status']+'。原始名单窗口：'+acquisition['window_start']+' 至 '+acquisition['window_end']+'。', '',
             '名称粗筛不要求原43词根或补充词表命中；所有后缀都可以通过探索组获得名额。后缀不等于质量。', '',
             '## 已保存数量', '', '|项目|数量|', '|---|---:|']
    for k,label in [('uniqueDomains','名单唯一域名'),('eligibleNames','通过名称启发规则'),('previousProbeOverlap','符合名称规则但此前已探测'),('probeSelected','本轮抽样'),('selectedWithoutLegacyTerms','抽样中不含原43词根'),('selectedWithoutAnyTerms','抽样中两个词表均不命中'),('probed','已完成页面核验'),('remaining','剩余'),('automaticCandidates','自动初留候选'),('contentReviewed','AI内容复核覆盖'),('contentCorrections','复核改判'),('candidates','内容规则保留'),('researchExcluded','暂跳过成人或博彩类别'),('researchCandidates','进入后续研究'),('uniqueKeywordPhrases','研究范围去重原文词句')]:
        lines.append(f"|{label}|{summary.get(k) if summary.get(k) is not None else '未完成'}|")
    lines += ['', '## 筛选方法', '', result['screening']['method'], '', '|分组|符合名称规则|实探名额|目标占比|', '|---|---:|---:|---|']
    for c in result['screening']['channels']:
        lines.append(f"|{c['label']}|{c['eligible']}|{c['selected']}|{c['quota']}|")
    lines += ['', *['- '+n for n in notes], '', '## 注册与页面口径', '',
              f"注册核验固定参照时间：{probe_meta.get('registration_reference_time', '尚未开始')}；下限：{probe_meta.get('registration_cutoff', '尚未开始')}。与原月度轮使用相同窗口；实际网页采集时间见每条记录。", '',
              '抓取当前HTTPS首页；最多3次跳转、单次6秒、响应512KiB，不执行页面JavaScript。仅通过自动内容规则者查RDAP registration事件。失败与日期未知单列，未抽中者没有被判为低价值。', '',
              '## 后续新词复核', '', '以近30个完整日（2026-08-27 至 2026-09-25）判断最近是否持续起量；近半年（2026-03-26 至 2026-09-25）仅作辅助背景。先从网页原文整理实际搜索短语，再查询美国／网页搜索／Search term。当前没有查询这批词的Google Trends。', '',
              '不跨不同窗口直接比较0—100指数；不把此前为0写成零搜索，不用除以0计算增长。新出现候选还需回看12个月，排除周期性和旧事件复起。', '',
              '- [Google：后缀与排名](https://developers.google.com/search/help/site-position-in-search-faq)',
              '- [Google：Trends归一化、低量和尖峰](https://support.google.com/trends/answer/4365533?hl=en)', '',
              '## 复核文件', '', *[f"- [{r['title']}]({r['path']})" for r in result['resources'] if r['type'] != 'report'], '']
    atomic(ROOT/'reports/tld-2026-09-26.md', '\n'.join(lines))
    print(json.dumps({'status':result['meta']['status'], **summary}, ensure_ascii=False))

if __name__ == '__main__':
    main()
