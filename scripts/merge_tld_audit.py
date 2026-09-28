#!/usr/bin/env python3
"""Validate and combine saved content reviews without altering raw probes."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT/'data/runs/2026-09-26-tld'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--require-complete', action='store_true')
    args=parser.parse_args()
    records={}
    lines=(RUN/'probes.jsonl').read_text().splitlines()
    for i,line in enumerate(lines):
        try:
            r=json.loads(line)
        except json.JSONDecodeError:
            if i!=len(lines)-1:raise
            continue
        records[r['domain']]=r
    reviewed=set(); findings=[]; parts=[]
    for path in sorted(RUN.glob('content-audit-part*.json')):
        raw=path.read_bytes(); part=json.loads(raw)
        names=set(part['reviewed_domains'])
        assert not names & reviewed, 'Overlapping review assignments'
        assert all(d in records and records[d]['verdict']=='candidate' for d in names)
        for f in part['findings']:
            assert f['domain'] in names
            assert f['recommended_verdict'] in {'parked','thin','unavailable'}
            value=records[f['domain']].get(f['evidence_field'],'')
            value=' '.join(value) if isinstance(value,list) else value
            assert f['evidence_quote'] and f['evidence_quote'] in value
        reviewed.update(names); findings.extend(part['findings'])
        parts.append({'file':path.name,'sha256':hashlib.sha256(raw).hexdigest(),'reviewed':len(names),'corrections':len(part['findings'])})
    assert len({f['domain'] for f in findings})==len(findings)
    candidates={d for d,r in records.items() if r['verdict']=='candidate'}
    probe_manifest=json.loads((RUN/'probe-manifest.json').read_text())
    complete=probe_manifest['status']=='complete' and reviewed==candidates
    if args.require_complete:
        assert complete, f"Incomplete review: {len(reviewed)}/{len(candidates)} observed candidates; probes {probe_manifest['status']}"
    result={
        'status':'complete' if complete else 'partial',
        'review_type':'AI review of saved homepage metadata and visible-text sample',
        'updated_at':datetime.now(timezone.utc).isoformat(),
        'reviewed_domains':sorted(reviewed), 'findings':sorted(findings,key=lambda f:f['domain']),
        'automatic_candidates_in_snapshot':len(candidates), 'reviewed_count':len(reviewed),
        'correction_count':len(findings), 'remaining_observed_candidates':sorted(candidates-reviewed),
        'parts':parts,
        'scope_note':'逐条查看保存的Title、Description、H1与最多3000字符正文样本；纠正明显待发布、停放、默认模板、访问壳等误收。没有执行JS或验证产品功能、内容真实性、首次上线日期、搜索需求或竞争度；不是人工逐站认证。已有清晰用途的页面不因行业偏好被直接判低价值。'
    }
    path=RUN/'content-audit.json';tmp=path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)
    print(json.dumps({k:result[k] for k in ['status','automatic_candidates_in_snapshot','reviewed_count','correction_count']},ensure_ascii=False))

if __name__=='__main__':main()
