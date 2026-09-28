#!/usr/bin/env python3
"""Resumeable bounded homepage screening, then RDAP on substantive pages only."""
import argparse, concurrent.futures, hashlib, json, re, threading, time, urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit
import probe_domains as probe

ROOT=Path(__file__).resolve().parents[1]
LABELS={'candidate':'近期注册且有内容','redirected':'跳转到其他域名','registration_unknown':'注册时间未核实','old':'注册超过30天','parked':'停放或未正式开放','thin':'页面内容不足','unavailable':'未取得可用页面'}
PARK=re.compile(r'\b(domain (?:is )?for sale|buy this domain|this domain (?:is )?(?:parked|available)|domain parking|website (?:is )?coming soon|under construction|account suspended|website expired|domain (?:has )?expired|default (?:web ?site|page)|welcome to nginx|apache2? .*default page|future home of|index of /)\b|域名出售|网站建设中|即将上线',re.I)
GENERIC=re.compile(r'^(?:home|homepage|welcome|coming soon|just a moment|access denied|error|untitled|index|loading|sign in|log in|404|403|首页|欢迎|登录)[.!…\s]*$',re.I)
SOFT_ERROR=re.compile(r'\bpage (?:was )?not found\b|^(?:not found|404 error|404(?:\s*[-|:—]\s*(?:page|not)|\s+(?:page|not found)|$))',re.I)
CHALLENGE=re.compile(r'^(?:just a moment|access denied|attention required|verify you are human|checking your browser|security verification|please wait)',re.I)
LIMIT_LOCK=threading.Lock();HOST_NEXT={};BOOT={}

def now():return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def atomic(path,obj):
 tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');tmp.replace(path)
def bootstrap(out):
 global BOOT
 path=out/'iana-rdap-bootstrap.json'
 if not path.exists():
  with urllib.request.urlopen('https://data.iana.org/rdap/dns.json',timeout=20) as r:body=r.read(2*1024*1024)
  doc=json.loads(body)
  if 'services' not in doc:raise ValueError('Invalid IANA bootstrap')
  path.write_bytes(body)
 else:doc=json.loads(path.read_text())
 BOOT={tld:next((u for u in urls if u.startswith('https://')),urls[0]) for tlds,urls in doc['services'] for tld in tlds if urls}

def rdap(domain, reference):
 base=BOOT.get(domain.rsplit('.',1)[-1]);url=(base.rstrip('/')+'/domain/'+quote(domain,safe='')) if base else 'https://rdap.org/domain/'+quote(domain,safe='')
 host=urlsplit(url).hostname
 with LIMIT_LOCK:
  at=max(time.monotonic(),HOST_NEXT.get(host,0));HOST_NEXT[host]=at+0.25
 delay=at-time.monotonic()
 if delay>0:time.sleep(delay)
 result=probe.fetch_public(url)
 record={'registration_status':'unknown','registration_date':None,'registration_source':result['final_url'],'registration_checked_at':result['fetched_at'],'registration_http_status':result['http_status'],'registration_error':None,'registration_events':[]}
 if result['status']!='ok':record['registration_error']=result['error'] or result['status'];return record
 try:
  doc=json.loads(result['body'])
  for name in [doc.get('ldhName'),doc.get('unicodeName')]:
   if name and probe.normalize_domain(name)!=domain:raise ValueError('RDAP object does not match requested domain')
  date,status,error=probe.registration_from_events(doc,30,reference)
  record.update(registration_date=date,registration_status=status,registration_error=error)
  record['registration_events']=[{'eventAction':'registration','eventDate':e.get('eventDate')} for e in doc.get('events',[]) if isinstance(e,dict) and e.get('eventAction')=='registration']
 except (ValueError,TypeError,AttributeError) as exc:record['registration_error']='Invalid RDAP JSON: '+str(exc)[:150]
 return record

def phrases(row):
 items=[];seen=set()
 for field,value in [('h1',v) for v in row['h1']]+[('title',row['title']),('description',row['description'])]:
  for fragment in re.split(r'\s+[|–—-]\s+|\s*\|\s*|(?<=[.!?;])\s+' if field == 'description' else r'\s+[|–—-]\s+|\s*\|\s*',value):
   fragment=fragment.strip()
   words=re.findall(r"[A-Za-z][A-Za-z0-9'’_-]*",fragment)
   if not 4<=len(fragment)<=110 or GENERIC.fullmatch(fragment) or PARK.search(fragment) or SOFT_ERROR.search(fragment):continue
   if not (1<=len(words)<=12 or len(re.findall('[\u4e00-\u9fff]',fragment))>=3):continue
   if fragment.casefold() in seen:continue
   if fragment not in value:raise ValueError('phrase is not exact metadata substring')
   seen.add(fragment.casefold());items.append({'phrase':fragment,'field':field,'quote':fragment})
   if len(items)>=6:return items
 return items

def run_one(item, reference):
 domain=probe.normalize_domain(item['domain'])
 r={**item,'domain':domain,'fetched_at':now(),'http_status':None,'final_url':None,'fetch_status':'network_error','fetch_error':None,'title':'','description':'','og_description':'','h1':[],'visible_text':'','registration_status':'not_checked','registration_date':None,'registration_source':None,'registration_error':None,'registration_events':[],'launch_status':'unverified','review_status':'automatic','keyword_candidates':[],'reasons':[],'substantive':False}
 page=probe.fetch_public('https://'+domain+'/')
 r.update(http_status=page['http_status'],final_url=page['final_url'],fetched_at=page['fetched_at'],fetch_status=page['status'],fetch_error=page['error'],content_type=page['content_type'])
 host=(urlsplit(r['final_url'] or '').hostname or '').lower().rstrip('.')
 r['redirected']=host not in {domain,'www.'+domain}
 r['redirected_external']=host!=domain and not host.endswith('.'+domain)
 verdict='unavailable'
 if page['status']=='ok':
  body=page['body'];r['body_sha256']=hashlib.sha256(body).hexdigest()
  ct=(page['content_type'] or '').split(';')[0].lower().strip()
  is_html=ct in {'text/html','application/xhtml+xml'} or (not ct and bool(re.search(br'<(?:!doctype\s+html|html|head|title|body)\b',body[:4096],re.I)))
  if is_html:
   try:
    parser=probe.PageParser();parser.feed(probe.decode_html(body,page['content_type']));parser.close();r.update(parser.extracted())
    head=' '.join([r['title'],*r['h1'],r['description']])
    park=PARK.search(head)
    bare_heading=not r['title'] or r['title'].lower().strip() in {domain,'www.'+domain} or any(h.lower().strip() in {domain,'www.'+domain} for h in r['h1'])
    if not park and bare_heading:park=PARK.search(r['visible_text'][:800])
    if not park and any(re.fullmatch(r'(?:coming soon|under construction|即将上线|网站建设中)[.!…\s]*',t,re.I) for t in [r['title'],*r['h1']]):park=re.search(r'.+',r['title'] or r['h1'][0])
    if park:
     verdict='parked';r['reasons'].append('标题/H1/description 或域名式标题对应的正文开头命中停放/未开放标记：'+park.group())
    elif any(CHALLENGE.search(t) or SOFT_ERROR.search(t) for t in [r['title'],*r['h1']]):
     verdict='unavailable';r['reasons'].append('标题/H1提示验证、访问限制或软404；未绕过')
    elif len(r['visible_text'])<160 or (len(r['description'])<40 and not any(len(h)>=8 and not GENERIC.fullmatch(h) for h in r['h1'])):
     verdict='thin';r['reasons'].append('未同时达到正文160字符且（description≥40字符或非通用H1≥8字符）')
    else:
     r['substantive']=True;r['keyword_candidates']=phrases(r)
     r.update(rdap(domain,reference))
     if r['registration_status']=='verified_old':verdict='old';r['reasons'].append('RDAP registration 早于固定30天窗口')
     elif r['registration_status']!='verified_recent':verdict='registration_unknown';r['reasons'].append('页面有内容，但RDAP未取得有效且位于窗口内的registration事件')
     elif r['redirected_external']:verdict='redirected';r['reasons'].append('来源域名近期注册，但最终页面属于其他域名；目标站上线时间未知')
     else:verdict='candidate';r['reasons'].append('RDAP registration 位于近30天窗口；当前HTTPS页面通过实质内容规则')
   except Exception as e:r['fetch_status']='parse_error';r['fetch_error']=str(e)[:300];r['reasons'].append('解析或核验失败，未认定为新站')
  else:r['fetch_status']='unsupported_content_type';r['reasons'].append('响应不是可解析HTML')
 else:r['reasons'].append('当前未取得可用HTTPS页面：'+page['status'])
 r.update(verdict=verdict,verdict_label=LABELS[verdict])
 return r

def main():
 p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--workers',type=int,default=16);p.add_argument('--timeout',type=int,default=6);p.add_argument('--reference-time',help='Fixed ISO-8601 registration reference; defaults to first run time');a=p.parse_args()
 if not 1<=a.workers<=16 or not 3<=a.timeout<=15:p.error('workers 1..16, timeout 3..15')
 requested_ref=None
 if a.reference_time:
  try:
   requested_ref=datetime.fromisoformat(a.reference_time.replace('Z','+00:00'))
   if requested_ref.tzinfo is None:raise ValueError('Timezone required')
  except ValueError:p.error('reference-time must include a valid date, time and timezone')
 probe.TIMEOUT_SECONDS=a.timeout
 a.output.mkdir(parents=True,exist_ok=True);bootstrap(a.output)
 manifest_path=a.output/'probe-manifest.json'
 if manifest_path.exists():
  manifest=json.loads(manifest_path.read_text());ref=datetime.fromisoformat(manifest['registration_reference_time'].replace('Z','+00:00'))
  if requested_ref is not None and requested_ref!=ref:p.error('reference-time differs from saved run; use a new output directory')
 else:
  ref=requested_ref or datetime.now(timezone.utc)
  manifest={'started_at':now(),'registration_reference_time':ref.isoformat(),'registration_cutoff':(ref-timedelta(days=30)).isoformat(),'workers':a.workers,'timeout_seconds_per_hop':a.timeout,'max_redirects':probe.MAX_REDIRECTS,'input':str(a.input),'method':'先抓HTTPS首页；仅对通过实质内容规则的域名查RDAP。仅registration事件用于注册日期，不推断首次上线。','content_rule':'正文≥160字符且（description≥40字符或非通用H1≥8字符），排除已公开停放/默认页/验证标题规则。','parking_regex':PARK.pattern,'generic_title_regex':GENERIC.pattern,'challenge_regex':CHALLENGE.pattern,'soft_error_regex':SOFT_ERROR.pattern,'keyword_rule':'按H1/title分隔符及description句界切分并保留原文片段；长度4..110，英文1..12词或中文≥3字，最多6条；未做需求或SEO验证。','status':'running'}
  atomic(manifest_path,manifest)
 items=json.loads(a.input.read_text());path=a.output/'probes.jsonl';existing={}
 if path.exists():
  lines=path.read_text().splitlines()
  for index,line in enumerate(lines):
   try:r=json.loads(line);existing[r['domain']]=r
   except (ValueError,KeyError):
    if index!=len(lines)-1:raise
    raise SystemExit('Incomplete final JSONL record; preserve file and repair before resuming')
 todo=[i for i in items if i['domain'] not in existing]
 counts=Counter(r['verdict'] for r in existing.values());start=time.monotonic()
 def progress():
  state={'selected':len(items),'completed':sum(counts.values()),'remaining':len(items)-sum(counts.values()),'verdicts':dict(counts),'updated_at':now(),'elapsed_this_run_seconds':round(time.monotonic()-start,1)}
  atomic(a.output/'progress.json',state);print(json.dumps(state,ensure_ascii=False),flush=True)
 progress()
 with path.open('a',encoding='utf-8') as output,concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
  futures={pool.submit(run_one,item,ref):item for item in todo}
  for f in concurrent.futures.as_completed(futures):
   item=futures[f]
   try:r=f.result()
   except Exception as exc:r={**item,'verdict':'unavailable','verdict_label':LABELS['unavailable'],'fetch_status':'worker_error','fetch_error':str(exc)[:500],'reasons':['请求或处理发生异常，未认定为新站'],'registration_status':'not_checked','fetched_at':now()}
   output.write(json.dumps(r,ensure_ascii=False)+'\n');output.flush();counts[r['verdict']]+=1
   if sum(counts.values())%50==0:progress()
 progress();manifest.update(status='complete',finished_at=now(),selected=len(items),completed=sum(counts.values()),verdicts=dict(counts));atomic(manifest_path,manifest)
if __name__=='__main__':main()
