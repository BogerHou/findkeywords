#!/usr/bin/env python3
"""Publish a local month-research snapshot from recorded acquisition and probes."""
import csv, io, json, re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'data/runs/2026-09-26-month'
RAW=ROOT/'data/raw/month-2026-09-26'

def read(path,default=None):return json.loads(path.read_text()) if path.exists() else default

def main():
 acquisition=read(RAW/'manifest.json');screen=read(RUN/'screening/manifest.json');probe_meta=read(RUN/'probe-manifest.json',{})
 selected=read(RUN/'screening/probe_candidates.json',[])
 rows=[]
 if (RUN/'probes.jsonl').exists():
  for line in (RUN/'probes.jsonl').read_text().splitlines():
   try:rows.append(json.loads(line))
   except json.JSONDecodeError:continue # concurrent writer may have an incomplete final line
 assert len({r['domain'] for r in rows})==len(rows),'Duplicate probe records'
 audit=read(RUN/'content-audit.json',{})
 audited=set(audit.get('reviewed_domains',[]));overrides={f['domain']:f for f in audit.get('findings',[])}
 labels={'parked':'停放或未正式开放','thin':'页面内容不足','unavailable':'未取得可用页面'}
 for r in rows:
  r['automatic_verdict']=r['verdict']
  if r['domain'] in audited:r['review_status']='ai_content_reviewed'
  if r['domain'] in overrides:
   f=overrides[r['domain']];raw=r.get(f['evidence_field'],'');raw=' '.join(raw) if isinstance(raw,list) else raw
   assert f['evidence_quote'] in raw,'Review quote not present in raw page evidence'
   assert f['recommended_verdict'] in labels,'Unexpected review verdict'
   r['verdict']=f['recommended_verdict'];r['verdict_label']=labels[r['verdict']]
   r['reasons']=['AI内容复核：'+f['reason']+' 原文：'+f['evidence_quote'],*['自动初判：'+reason for reason in r.get('reasons',[])]]
 names={r['domain'] for r in selected};assert all(r['domain'] in names for r in rows),'Probe outside selection'
 channel_names={c['id']:c['label'] for c in screen['channels']}
 domains=[]
 for r in sorted(rows,key=lambda r:r.get('queue_rank',999999)):
  kw=r.get('keyword_candidates',[])
  for k in kw:
   value=r.get(k['field'],'');value=' '.join(value) if isinstance(value,list) else value
   assert k['quote'] in value and k['phrase']==k['quote'],f"Unbacked keyword: {r['domain']} {k}"
  domains.append({'domain':r['domain'],'sourceDates':[r.get('source_date')],'channel':r.get('channel'),'channelLabel':channel_names.get(r.get('channel'),r.get('channel')),'selectionReason':r.get('selection_reason'),'verdict':r['verdict'],'verdictLabel':r.get('verdict_label'),'reasons':r.get('reasons',[]),'registrationStatus':r.get('registration_status'),'registrationDate':r.get('registration_date'),'registrationSource':r.get('registration_source'),'registrationError':r.get('registration_error'),'httpStatus':r.get('http_status'),'fetchStatus':r.get('fetch_status'),'fetchError':r.get('fetch_error'),'finalUrl':r.get('final_url'),'fetchedAt':r.get('fetched_at'),'title':r.get('title',''),'description':r.get('description',''),'h1':r.get('h1',[]),'visibleText':r.get('visible_text',''),'redirected':r.get('redirected',False),'redirectedExternal':r.get('redirected_external',False),'keywordCandidates':kw,'launchStatus':'unverified','reviewStatus':r.get('review_status','automatic')})
 candidates=[d for d in domains if d['verdict']=='candidate'];prior_domains={r['domain'] for r in read(ROOT/'data/runs/2026-09-26/probes.json',[])};phrases=[k for d in candidates for k in d['keywordCandidates']]
 counts=Counter(r.get('registration_status') for r in rows);verdicts=Counter(r['verdict'] for r in rows)
 summary={'rawRows':acquisition['raw_rows'],'uniqueDomains':screen['counts']['unique_valid_domains'],'downloadedDays':acquisition['downloaded_days'],'requestedDays':acquisition['requested_days'],'probeSelected':len(selected),'probed':len(rows),'remaining':len(selected)-len(rows),'httpsAccessible':sum(r.get('fetch_status')=='ok' for r in rows),'substantivePages':sum(r.get('substantive',False) for r in rows),'verifiedRecent':counts['verified_recent'],'verifiedOld':counts['verified_old'],'registrationUnknown':counts['unknown'],'registrationNotChecked':counts['not_checked'],'candidates':len(candidates),'keywordPhrases':len(phrases),'uniqueKeywordPhrases':len({k['phrase'].casefold() for k in phrases}),'verdicts':dict(verdicts),'newToPriorProbes':sum(d['domain'] not in prior_domains for d in candidates),'priorProbeOverlap':sum(d['domain'] in prior_domains for d in candidates),'automaticCandidates':sum(r.get('automatic_verdict')=='candidate' for r in rows),'contentReviewed':len(audited),'contentCorrections':len(overrides),'duplicateOccurrences':screen['counts']['duplicate_occurrences'],'invalidInputs':screen['counts']['invalid_or_blank_lines']}
 for c in screen['channels']:
  c['results']=dict(Counter(r['verdict'] for r in rows if r.get('channel')==c['id']))
 channel_rules={c['id']:c['condition'] for c in screen['rules']['channel_rules']}
 result={'meta':{'runId':'2026-09-26-month','runDate':'2026-09-26','generatedAt':datetime.now(timezone.utc).isoformat(),'status':'complete' if len(rows)==len(selected) and probe_meta.get('status')=='complete' else 'running','windowStart':acquisition['window_start'],'windowEnd':acquisition['window_end'],'registrationCutoff':probe_meta.get('registration_cutoff'),'registrationReferenceTime':probe_meta.get('registration_reference_time'),'sourceNote':'WhoisDS 每日免费子集，共30个日期批次；不是全球全部域名，也不是已上线网站名单。','launchNote':'新站候选仅表示来源域名近30天注册且当前HTTPS页面通过自动实质内容规则。首次上线时间未核实，不能把域名注册/证书签发/名单日期当上线日期。'},'summary':summary,'screening':{'method':screen['audit_reproduction'],'channels':[{'id':c['id'],'label':c['label'],'eligible':c['all_valid_count'],'selected':c['final_quota'],'quota':str(c['share_percent'])+'%','rule':channel_rules[c['id']],'results':c['results']} for c in screen['channels']],'notes':screen['rules']['limitations']+[screen['rules']['idn_priority_override'],'工作台结果合并已保存的AI内容复核，纠正明显默认页/停放/加载壳等误收；自动初判仍完整保留在probes.jsonl。','未被抽入3000队列的域名保留在全量审计中；未核验不代表无价值。','自动内容规则：正文≥160字符且description≥40或非通用H1≥8，排除已知停放、未开放、验证和错误页。可能误判，保留原文供复核。','关键词短语为H1/title/description原文片段；尚未人工逐词核查，也未查询本轮的Google Trends或竞争度。']},'acquisition':{'sourceName':'WhoisDS 免费日名单','sourceUrl':'https://www.whoisds.com/newly-registered-domains','windowStart':acquisition['window_start'],'windowEnd':acquisition['window_end'],'batches':acquisition['batches'],'coverageNote':acquisition['coverage_note']},'domains':domains,'resources':[
 {'title':'内容复核与误收纠正','description':'覆盖域名、每一条改判理由及对应原文；不覆盖功能或关键词机会验证。','path':'../data/runs/2026-09-26-month/content-audit.json','type':'audit'},
 {'title':'月度完整审计报告','description':'真实数量、来源、规则、队列覆盖与结果边界。','path':'../reports/month-2026-09-26.md','type':'report'},
 {'title':'全部探测结果 CSV','description':'可用表格查看全部实探域名及每条去留理由。','path':'../reports/month-domains-2026-09-26.csv','type':'data'},
 {'title':'候选站原文短语 CSV','description':'仅含近期注册且通过内容规则的候选；不等于已验证关键词。','path':'../reports/month-keywords-2026-09-26.csv','type':'data'},
 {'title':'30天来源与文件校验','description':'逐包日期、数量、来源URL和SHA-256。','path':'../data/raw/month-2026-09-26/manifest.json','type':'data'},
 {'title':'全量筛选独立验收','description':'逐批校验、3000条源行定位、全通道重分类及精确哈希抽样复算。','path':'../data/runs/2026-09-26-month/screening-verification.json','type':'audit'},
 {'title':'完整筛选规则与配额','description':'每通道数量、词表、固定抽样方法和复算方法。','path':'../data/runs/2026-09-26-month/screening/manifest.json','type':'data'},
 {'title':'3000个入选记录','description':'包含输入行号、命中规则、选择原因及哈希排序。','path':'../data/runs/2026-09-26-month/screening/probe_candidates.json','type':'data'},
 {'title':'逐域名探测原始记录','description':'页面标签、正文样本、请求时间、RDAP注册事件和处理理由。','path':'../data/runs/2026-09-26-month/probes.jsonl','type':'evidence'},
 {'title':'注册与内容规则','description':'固定窗口、超时与内容规则正则，以及核验运行状态。','path':'../data/runs/2026-09-26-month/probe-manifest.json','type':'data'}]}
 def cell(v):
  s=str(v or '')
  return "'"+s if s.lstrip()[:1] in {'=','+','-','@'} else s
 with (ROOT/'reports/month-domains-2026-09-26.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.writer(f);w.writerow(['域名','名单日期','通道','自动判定','判定原因','注册日期','注册状态','最终页面','标题','Description','H1','原文短语','首次上线时间'])
  for d in domains:w.writerow(map(cell,[d['domain'],';'.join(filter(None,d['sourceDates'])),d['channelLabel'],d['verdictLabel'],';'.join(d['reasons']),d['registrationDate'],d['registrationStatus'],d['finalUrl'],d['title'],d['description'],';'.join(d['h1']),';'.join(k['phrase'] for k in d['keywordCandidates']),'未核实']))
 with (ROOT/'reports/month-keywords-2026-09-26.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.writer(f);w.writerow(['域名','原文短语','证据字段','原文','页面URL','验证状态'])
  for d in candidates:
   for k in d['keywordCandidates']:w.writerow(map(cell,[d['domain'],k['phrase'],k['field'],k['quote'],d['finalUrl'],'自动提取原文片段；需求、趋势、竞争均未验证']))
 payload=json.dumps(result,ensure_ascii=False,separators=(',',':'))
 for filename,content in [('month-data.json',payload+'\n'),('month-data.js','window.FINDKEYWORDS_MONTH = '+payload+';\n')]:
  path=ROOT/'site'/filename;tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(content,encoding='utf-8');tmp.replace(path)
 lines=['# 近30天域名扩量审计（2026-09-26）','',f"状态：{result['meta']['status']}。下载名单窗口：{acquisition['window_start']} 至 {acquisition['window_end']}。",'',result['meta']['sourceNote'],result['meta']['launchNote'],'','## 真实覆盖','',*[f'- {label}: {summary[key]}' for key,label in [('rawRows','原始名单行数'),('uniqueDomains','IDNA标准化后唯一域名'),('downloadedDays','成功下载日批次'),('probeSelected','抽样队列'),('probed','已完成页面探测'),('remaining','剩余未探测'),('httpsAccessible','取得可解析HTTPS页面'),('substantivePages','通过初步实质内容规则并尝试RDAP'),('verifiedRecent','已核实近30天注册'),('verifiedOld','已核实注册超过30天'),('registrationUnknown','已查但未核实注册日期'),('registrationNotChecked','未查询注册日期'),('automaticCandidates','自动初留候选'),('contentReviewed','AI内容复核覆盖候选'),('contentCorrections','AI内容复核改判'),('candidates','最终保留候选'),('newToPriorProbes','相对前轮52域名新发现的候选'),('priorProbeOverlap','与前轮52域名重合的候选'),('keywordPhrases','候选站原文片段'),('uniqueKeywordPhrases','原文片段忽略大小写去重'),('duplicateOccurrences','标准化重复出现次数'),('invalidInputs','不合规输入')]],'','## 通道与选择规则','','|通道|合规域名数|实探配额|占比|','|---|---:|---:|---|',*[f"|{c['label']}|{c['eligible']:,}|{c['selected']:,}|{c['quota']}|" for c in result['screening']['channels']],'',screen['audit_reproduction'],'',*[f"- {c['label']}：{c['rule']}" for c in result['screening']['channels']],'','## 核验规则与边界','',*[f'- {s}' for s in result['screening']['notes']],f"- 注册核验固定基准时间：{probe_meta.get('registration_reference_time')}；下界：{probe_meta.get('registration_cutoff')}。仅采用 registration 事件；晚于基准日期仍记未知。",'- 只对通过内容规则的页面查询RDAP；其他页面注册状态为not_checked。RDAP失败保留unknown。没有将SSL签发等同上线时间。','- 每个域名仅探测当前HTTPS首页，最多3次跳转、每请求6秒、响应512KiB。不执行页面JavaScript，不绕过验证码或访问拒绝。失败表示本次未取得页面，并不证明网站不存在。','- 3,000 个样本按固定通道配额抽取，不代表当月全体域名的有效率；未入选域名不是被判无价值。','- 名称词根仍有误匹配；无词根探索只按字符条件，不是语义模型。','- 当前自动候选不能直接用来决定建站；还需人工核查网站用途、搜索趋势及竞争。','','## 来源与原始记录','','- [WhoisDS 来源](https://www.whoisds.com/newly-registered-domains)','- [下载清单](../data/raw/month-2026-09-26/manifest.json)','- [筛选清单与规则](../data/runs/2026-09-26-month/screening/manifest.json)','- [逐域名探测 JSONL](../data/runs/2026-09-26-month/probes.jsonl)','- [候选原文短语 CSV](month-keywords-2026-09-26.csv)','']
 (ROOT/'reports/month-2026-09-26.md').write_text('\n'.join(lines),encoding='utf-8')
 print(json.dumps({'status':result['meta']['status'],**summary},ensure_ascii=False))
if __name__=='__main__':main()
