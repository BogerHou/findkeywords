#!/usr/bin/env python3
"""Acquire and audit public WhoisDS daily archives; never infer launch dates."""
import argparse, base64, concurrent.futures, hashlib, io, json, time, urllib.request, zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
 p=argparse.ArgumentParser();p.add_argument('--end',required=True);p.add_argument('--days',type=int,default=30);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 end=date.fromisoformat(a.end);a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=True)
 dates=[(end-timedelta(days=i)).isoformat() for i in range(a.days-1,-1,-1)]
 def fetch(day):
  token=base64.b64encode((day+'.zip').encode()).decode()
  url='https://www.whoisds.com/whois-database/newly-registered-domains/'+token+'/nrd'
  row={'date':day,'url':url,'provider':'WhoisDS','page':'https://www.whoisds.com/newly-registered-domains'}
  try:
   zp=a.output/('whoisds-'+day+'.zip');old=ROOT/'data'/'raw'/zp.name
   body=zp.read_bytes() if zp.exists() else old.read_bytes() if old.exists() else None
   if body is None:
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'FindKeywordsResearch/0.2'}),timeout=35) as r:
     body=r.read(10*1024*1024+1)
    if len(body)>10*1024*1024:raise ValueError('archive exceeds 10 MiB cap')
   with zipfile.ZipFile(io.BytesIO(body)) as z:
    names=z.namelist()
    if names!=['domain-names.txt']:raise ValueError('unexpected archive members')
    member=z.getinfo(names[0])
    if member.file_size>30*1024*1024:raise ValueError('decompressed input exceeds 30 MiB cap')
    if z.testzip():raise ValueError('ZIP CRC failed')
    raw=z.read(names[0]);lines=[s.strip().lower() for s in raw.decode('utf-8-sig').splitlines() if s.strip()]
   if len(lines)<1000:raise ValueError('unexpectedly small batch')
   zp.write_bytes(body);tp=a.output/('whoisds-'+day+'.txt');tp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
   row.update(status='ok',archive=str(zp.relative_to(ROOT)),text=str(tp.relative_to(ROOT)),archive_bytes=len(body),sha256=hashlib.sha256(body).hexdigest(),text_sha256=hashlib.sha256(tp.read_bytes()).hexdigest(),rows=len(lines),unique_domains=len(set(lines)),zip_member_timestamp=list(member.date_time),retrieved_at=datetime.now(timezone.utc).isoformat())
  except Exception as e:row.update(status='error',error=str(e)[:500])
  print(json.dumps({'date':day,'status':row['status'],'rows':row.get('rows'),'error':row.get('error')},ensure_ascii=False),flush=True)
  return row
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:rows=list(ex.map(fetch,dates))
 result={'provider':'WhoisDS free public daily subset','window_start':dates[0],'window_end':dates[-1],'requested_days':a.days,'downloaded_days':sum(r['status']=='ok' for r in rows),'raw_rows':sum(r.get('rows',0) for r in rows),'coverage_note':'供应商免费日名单子集；批次日期不是逐域名核验的注册日期，更不是网站首次上线日期。','batches':rows,'generated_at':datetime.now(timezone.utc).isoformat()}
 (a.output/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 if result['downloaded_days']!=a.days:raise SystemExit('Some requested batches were not acquired; see manifest.json')
 print(json.dumps({k:v for k,v in result.items() if k!='batches'},ensure_ascii=False))
if __name__=='__main__':main()
