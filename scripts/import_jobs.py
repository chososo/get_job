"""Import already verified public job facts, never personal application data."""
import argparse,json,re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from collect import ROOT,OUTPUT,COUNTRIES,merge,utcnow

FIELDS={'id','sourceId','sourceUrl','applicationUrl','title','company','category','country','level','eligibility','languageStatus','visaStatus','postedAt','startDate','deadlineDate','deadlineAt','deadlineTimezone','deadlineKind','deadlineText','status','evidence','lastVerifiedAt','section','screeningMode','screeningVersion'}
CATEGORIES={'퀀트 리서치','자산운용·자산배분','ETF·인덱스','금융리스크','파생상품평가','기업·산업 리서치','기업 재무·전략투자'}
def validate(job):
    if not isinstance(job,dict) or set(job)-FIELDS:raise ValueError('Only public job fields are allowed')
    if not all(isinstance(job.get(k),str) and job[k].strip() for k in ('id','sourceId','sourceUrl','title','company','lastVerifiedAt')):raise ValueError('Missing required public fields')
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,160}',job['id']):raise ValueError('Invalid stable ID')
    if job.get('country') not in COUNTRIES or job.get('category') not in CATEGORIES:raise ValueError('Out of scope')
    if job.get('status') not in ('open','review','closed','upcoming','excluded'):raise ValueError('Invalid status')
    if any(isinstance(v,str) and len(v)>1800 for v in job.values()):raise ValueError('Only concise public facts, not full descriptions, are allowed')
    for key in ('sourceUrl','applicationUrl'):
        if job.get(key) and (urlsplit(job[key]).scheme not in ('http','https') or not urlsplit(job[key]).netloc or urlsplit(job[key]).username):raise ValueError('Invalid public URL')
    for key in ('deadlineDate','startDate'):
        if job.get(key):datetime.strptime(job[key],'%Y-%m-%d')
    datetime.fromisoformat(job['lastVerifiedAt'].replace('Z','+00:00'))
    if job.get('status')=='open' and (job.get('level') not in ('인턴','신입','아르바이트') or not job.get('evidence')):raise ValueError('Open jobs require junior and verification evidence')
    if job.get('deadlineKind') not in ('date','rolling','unknown'):raise ValueError('Invalid deadline kind')
    return job

def import_file(path):
    incoming=json.loads(Path(path).read_text())
    if not isinstance(incoming,list):raise ValueError('Expected a list of public jobs')
    incoming=[validate(j) for j in incoming]
    data=json.loads(OUTPUT.read_text());at=utcnow();jobs,changes=merge(data,incoming,at)
    data.update(jobs=jobs,changes=changes,generatedAt=at)
    temp=OUTPUT.with_suffix('.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');temp.replace(OUTPUT)
    print(f'Imported {len(incoming)} verified public records.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('path');a=p.parse_args();import_file(a.path)
