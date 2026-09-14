"""One collection pipeline for the button and the daily routine. Keys never enter feeds."""
import argparse, fcntl, json, os, re, threading, subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collect import merge, utcnow, digest, canonical
from public_web import Client, Renderer, read_images
from discovery import discover
from screening import classify, category, VERSION, audit_existing
import ai_screen
import routine_sites

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'web/data/jobs.json'

def atomic(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as out:json.dump(data,out,ensure_ascii=False,indent=2);out.write('\n')
    tmp.replace(path)

def publish():
    """Only data files are staged; never include other staged work or use force push."""
    def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,stderr=subprocess.DEVNULL,text=True).strip()
    allowed=['web/data/jobs.json','web/data/latest-run.json']
    try:
        if git('branch','--show-current')!='main':return '로컬 저장 완료 · main 브랜치에서만 자동 게시합니다.'
        if git('diff','--cached','--name-only'):return '로컬 저장 완료 · 별도 작업이 준비되어 있어 자동 게시를 보류했습니다.'
        if git('remote','get-url','origin') not in ('git@github.com:chososo/get_job.git','https://github.com/chososo/get_job.git'):return '로컬 저장 완료 · 저장소 설정 확인 필요'
        if not git('diff','--name-only','--',*allowed):return '공개 데이터 변경 없음'
        git('add','--',*allowed);git('commit','-m','Update screened public job feed');git('push','origin','main')
        return 'GitHub 업로드 완료 · Pages 배포 진행 중'
    except subprocess.CalledProcessError:return '로컬 저장 완료 · GitHub 업로드 실패, 인증·원격 상태 확인 필요'

def prepare_raw(raw, cure, cache):
    """Read attachments and apply only unchanged, grounded manual verification."""
    try:raw=read_images(raw,Client())
    except Exception:raw['complete']=False
    verification_text=raw['title']+' '+raw['body']+' '+raw.get('employment','')
    if cure and cure.get('verification') and all(q in re.sub(r'\s+','',verification_text) for q in cure['verification']):
        fingerprint=digest([raw['title'],raw['body'],raw.get('employment',''),raw.get('deadlineAt')]);record=cache/('verified-'+digest([VERSION,cure])+'.json')
        if not record.exists():atomic(record,{'bodyHash':fingerprint})
        if json.loads(record.read_text())['bodyHash']==fingerprint:
            stable_id=raw.get('id')
            raw.update({k:v for k,v in cure.items() if k not in ('verification','sourceId','sourceUrl')})
            if stable_id:raw['id']=stable_id
            raw['curationValid']=True
    if len(raw['body'])>50000:raw['body']=raw['body'][:50000];raw['complete']=False
    return raw

def revalidate_cached(job,cache):
    if job.get('screeningVersion')==VERSION:return audit_existing(job)
    file=cache/('raw-'+digest([job['sourceUrl'],job.get('roleKey','')])+'.json')
    if job.get('screeningMode','rules')=='rules' and file.exists():
        raw=json.loads(file.read_text());new=classify({**raw,'id':job['id']})
        if new:
            new['lastVerifiedAt']=job['lastVerifiedAt']
            return new
    return audit_existing(job)

def run(pages=3, progress=lambda data:None, publish_result=False):
    cache=ROOT/'.collection-cache';cache.mkdir(exist_ok=True)
    with (cache/'refresh.lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('다른 수집 작업이 진행 중입니다. 완료 후 다시 실행하세요.')
        return _run(pages,progress,publish_result,cache)

def _run(pages,progress,publish_result,cache):
    previous=json.loads(OUTPUT.read_text()) if OUTPUT.exists() else {'jobs':[],'sources':[],'changes':[]}
    sources=json.loads((ROOT/'sources.json').read_text());public_ids={s['id'] for s in sources}
    localfile=ROOT/'.routine-sites.json'
    if localfile.exists():
        for s in routine_sites.read(localfile)['sources']:
            if s['enabled']:sources.append({**s,'id':'custom-'+digest([s['name'],s['url']])[:16],'adapter':'public','private':True})
    cfg=ai_screen.read_config();mode='astra' if cfg.get('api_key') else 'rules'
    curation_path=ROOT/'public-watch.json';curations=json.loads(curation_path.read_text()) if curation_path.exists() else []
    old_by_url={}
    for j in previous['jobs']:
        old_by_url.setdefault(canonical(j['sourceUrl']),j)
    cure_by_url={canonical(j['sourceUrl']):j for j in curations}
    incoming=[];statuses=[];started=utcnow();renderer=Renderer();progress_lock=threading.Lock();done=0;ai_errors=[]
    def update(label):
        with progress_lock:progress({'state':'running','mode':mode,'completedSources':done,'totalSources':len(sources),'message':label,'startedAt':started})
    def collect_source(source):
        if not source.get('url'):
            return source,[],{'lists':0,'details':0,'failed':1,'truncated':False,'reason':'기업명만 등록됨 · 채용 사이트 URL 연결 필요'}
        watch=[j for j in previous['jobs'] if j['sourceId']==source['id'] and j.get('status') not in ('closed','excluded')]
        for c in curations:
            if c['sourceId']==source['id']:watch=[w for w in watch if w['sourceUrl']!=c['sourceUrl']]+[c]
        try:
            rows,info=discover(source,Client(),renderer,pages,watch,update)
            return source,rows,info
        except Exception as exc:
            return source,[],{'lists':0,'details':0,'failed':1,'truncated':False,'reason':'접근·본문 수집 실패 ('+type(exc).__name__+')'}
    update('전체 등록 사이트 수집을 시작합니다.')
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures=[pool.submit(collect_source,s) for s in sources]
            for future in as_completed(futures):
                source,rows,info=future.result();kept=excluded=reviewed=0
                for raw in rows:
                    old=old_by_url.get(canonical(raw['sourceUrl']))
                    if old and not raw.get('roleKey'):raw['id']=old['id']
                    cure=cure_by_url.get(canonical(raw['sourceUrl']))
                    possible_ai_candidate=mode=='astra' and re.search(r'인턴|신입|intern|graduate|research|analyst',raw['title'],re.I) and re.search(r'금융|투자|파생|ETF|quant|investment|portfolio|risk',raw['body'],re.I)
                    if not old and not cure and not category(raw['title']+' '+raw.get('roles',''),raw['body']) and not possible_ai_candidate:continue
                    raw=prepare_raw(raw,cure,cache)
                    atomic(cache/('raw-'+digest([raw['sourceUrl'],raw.get('roleKey','')])+'.json'),{**raw,'collectedAt':started})
                    if raw.get('needsAttachment') and not raw.get('complete'):info['failed']+=1
                    judgment=None;api_failed=False
                    if mode=='astra':
                        update(source['name']+' · Astra 자격요건 심사')
                        key=digest([VERSION,ai_screen.MODEL,raw]);file=cache/('ai-'+key+'.json')
                        try:
                            if len(ai_errors)>=3:raise ValueError('반복된 API 오류로 추가 유료 요청을 중단했습니다. 설정을 확인하세요.')
                            if file.exists():judgment=json.loads(file.read_text())
                            else:judgment=ai_screen.screen(raw,cfg);atomic(file,judgment)
                        except Exception as exc:api_failed=True;ai_errors.append(str(exc))
                    job=classify(raw,judgment)
                    if not job:
                        if old and raw.get('complete') and raw.get('postingRecognized',source.get('adapter') in ('kofia','greenhouse')):
                            incoming.append({**old,'status':'excluded','evidence':'원문 재검토: 현재 희망 분야에 해당하는 직무를 확인하지 못했습니다.','lastVerifiedAt':utcnow()})
                            excluded+=1
                        continue
                    if api_failed:
                        if job['status'] in ('open','upcoming'):job['status']='review'
                        job['screeningMode']='astra-error'
                        if job['status'] not in ('excluded','closed'):
                            job['evidence']='Astra 심사 실패 · '+ai_errors[-1]
                    if job['status']=='closed' and not old and not cure:continue
                    if job['status']=='excluded' and not old and not cure:excluded+=1;continue
                    incoming.append(job)
                    if job['status']=='excluded':excluded+=1
                    elif job['status']=='review':reviewed+=1
                    else:kept+=1
                status='error' if not info['lists'] and info['failed'] else 'partial' if info['failed'] or info['truncated'] else 'ok'
                prior=next((s for s in previous.get('sources',[]) if s['id']==source['id']),{})
                result={k:v for k,v in source.items() if not k.startswith('_') and k!='private'}
                result.update(status=status,reason=info['reason'],lastAttemptAt=utcnow(),lastSuccessAt=utcnow() if info['details'] else prior.get('lastSuccessAt'),
                              found=kept,excluded=excluded,review=reviewed,inspected=info['details'],listPages=info['lists'])
                if source['id'] in public_ids:statuses.append(result)
                done+=1;update(source['name']+' 확인 완료')
    finally:renderer.close()
    # Keep stable IDs for company/official-application aliases; don't merge separate roles by company alone.
    merged_incoming={}
    for job in incoming:
        url=canonical(job.get('applicationUrl',''))
        key=url if re.search(r'jobnoticeSn=|recruit_default\.asp|jobs-view\?seq=|/jobs/\d+/',url) else canonical(job['sourceUrl'])
        if job.get('roleKey'):key+='::'+job['roleKey']
        if key in merged_incoming:
            existing=merged_incoming[key]
            if job['id'] in {j['id'] for j in previous['jobs']}:merged_incoming[key]=job
            elif existing['status']=='review' and job['status']=='open':job['id']=existing['id'];merged_incoming[key]=job
        else:merged_incoming[key]=job
    # Prefer direct employer facts when an aggregator shares the same stable ID.
    authoritative={s['id'] for s in sources if s.get('authoritative')}
    by_id={}
    for job in merged_incoming.values():
        if job['id'] not in by_id or job['sourceId'] in authoritative:by_id[job['id']]=job
    merged_incoming=by_id
    refreshed={j['id'] for j in merged_incoming.values()}
    audited=[revalidate_cached(j,cache) for j in previous['jobs'] if j['id'] not in refreshed]
    jobs,changes=merge(previous,list(merged_incoming.values())+audited,started)
    result={'schemaVersion':1,'generatedAt':utcnow(),'screeningMode':mode,'jobs':jobs,'sources':statuses,'changes':changes}
    new_changes=[c for c in changes if c['detectedAt']==started]
    report={'generatedAt':result['generatedAt'],'mode':mode,'jobs':len(jobs),'new':sum(c['kind']=='new' for c in new_changes),
            'updated':sum(c['kind']=='updated' for c in new_changes),'closed':sum(c['kind']=='closed' for c in new_changes),
            'attemptedSources':len(sources),'failedSources':[s['id'] for s in statuses if s['status']!='ok'],
            'aiErrors':len(ai_errors),'aiError':ai_errors[0] if ai_errors else None,'manualSources':[]}
    atomic(OUTPUT,result);atomic(ROOT/'web/data/latest-run.json',report)
    publication=publish() if publish_result else '로컬 공개 데이터 저장 완료'
    progress({'state':'complete','mode':mode,'message':publication,'completedSources':done,'totalSources':len(sources),'report':report,'finishedAt':utcnow()})
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--pages',type=int,default=3);parser.add_argument('--publish',action='store_true');args=parser.parse_args()
    if not 1<=args.pages<=10:parser.error('pages must be 1..10')
    last=[None]
    def log(data):
        value=(data.get('completedSources'),data.get('message'))
        if value!=last[0]:print(json.dumps(data,ensure_ascii=False),flush=True);last[0]=value
    run(args.pages,log,args.publish)
