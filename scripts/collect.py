"""Public-only collector. Never reads the browser vault, secrets, or personal files."""
from __future__ import annotations
import argparse, hashlib, json, re, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlsplit, parse_qs
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'web/data/jobs.json'
KST = ZoneInfo('Asia/Seoul')
COUNTRIES = {'KR':'Asia/Seoul','GB':'Europe/London','HK':'Asia/Hong_Kong','SG':'Asia/Singapore','PL':'Europe/Warsaw','JP':'Asia/Tokyo'}
CAREER_FIELDS = ['title','company','country','category','level','status','deadlineDate','deadlineAt','deadlineKind','deadlineText','languageStatus','visaStatus','eligibility','evidence','applicationUrl']

def utcnow(): return datetime.now(timezone.utc).isoformat()
def clean(value): return re.sub(r'\s+', ' ', value or '').strip()
def digest(value): return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
def canonical(url):
    u=urlsplit(url)
    if u.scheme not in ('http','https'): return ''
    if 'kofia.or.kr' in u.netloc and 'seq' in parse_qs(u.query):
        return 'https://www.kofia.or.kr/brd/m_96/view.do?seq='+parse_qs(u.query)['seq'][0]
    if (u.hostname or '').endswith('linkedin.com'):
        match=re.search(r'/jobs/view/(?:[^/]*-)?(\d+)',u.path)
        if match:return 'https://www.linkedin.com/jobs/view/'+match[1]
    if u.hostname=='cafe.naver.com':
        match=re.search(r'/f-e/cafes/(\d+)/articles/(\d+)',u.path)
        if match:return 'https://cafe.naver.com/f-e/cafes/'+match[1]+'/articles/'+match[2]
        match=re.match(r'/kkbjob/(\d+)',u.path)
        if match:return 'https://cafe.naver.com/f-e/cafes/15279069/articles/'+match[1]
    return u._replace(fragment='').geturl()

def category_for(title, body=''):
    title=re.sub(r'^\[[^\]]+\]\s*','',title)
    text=title+' '+body[:3500]
    if re.search(r'파생.{0,10}평가|금융상품.{0,10}평가|derivative.{0,30}(pric|valu)',title,re.I): return '파생상품평가'
    if re.search(r'ETF|인덱스|지수개발|index.{0,20}(research|portfolio)',title,re.I): return 'ETF·인덱스'
    if re.search(r'리스크|위험관리|위험분석|성과평가|시장위험|신용위험|risk|model validation',title,re.I): return '금융리스크'
    if re.search(r'퀀트|계량|quant|systematic|트레이딩|트레이더|파생솔루션|trading|research (developer|scientist)|machine learning researcher',title,re.I): return '퀀트 리서치'
    if re.search(r'자산배분|멀티에셋|투자솔루션|주식운용|채권운용|운용역|운용본부|운용부문|운용팀|글로벌매크로|펀드매니저|투자자산운용|portfolio|investment research',title,re.I): return '자산운용·자산배분'
    if re.search(r'파생상품\s*(공정가치\s*)?평가|채권.{0,8}스왑.{0,8}파생상품\s*평가',body,re.I): return '파생상품평가'
    if re.search(r'리서치|연구원|분석|research|analyst',title,re.I) and re.search(r'퀀트|백테스트|금융공학|팩터.{0,15}(모델|분석)',body,re.I): return '퀀트 리서치'
    return None

def junior_level(title,body):
    from screening import experience_requirement
    if experience_requirement(body):return None
    head=clean(title+' '+body[:450])
    junior_title=bool(re.search(r'신입|인턴|intern\b|internship|graduate|new grad|entry.level|junior',title,re.I))
    if not junior_title and re.search(r'과.?차장|과장급|차장급|부장급|팀장|본부장|실장급|책임자|시니어|senior|vice president|director|principal|lead researcher|portfolio manager|engineering manager',head,re.I) and not re.search(r'사원|신입|인턴',head): return None
    if junior_title: return '인턴' if re.search(r'인턴|intern',title,re.I) else '신입'
    if re.search(r'((경력|experience).{0,20}([3-9]|\d{2})\s*(년|years).{0,10}(이상|required|minimum)|(at least|minimum of)\s*[3-9].{0,8}years|[3-9]\+?\s*years.{0,25}experience)',body,re.I): return None
    if re.search(r'경력직|experienced',title,re.I) and not re.search(r'신입|경력.{0,3}무관|new grad',body,re.I): return None
    if re.search(r'(신입.{0,8}(지원|채용|모집|가능)|채용구분.{0,20}신입|경력.{0,4}무관|no (prior )?experience (is )?required)',body,re.I): return '신입'
    if re.search(r'((인턴|internship).{0,10}(모집|채용)|고용형태.{0,8}인턴|모집.{0,15}인턴)',body,re.I): return '인턴'
    return '확인 필요'

def language_status(body,country):
    for local,english in [('일본어','Japanese'),('중국어','Chinese'),('폴란드어','Polish')]:
        phrase=re.search(local+r'[^\n.;]{0,60}',body)
        if phrase:
            text=phrase.group()
            if re.search(r'필수\s*(아님|는\s*아님|가\s*아님)',text):return english+' 우대 또는 선택'
            if re.search(r'필수',text):return english+' 필수'
            if re.search(r'우대',text):return english+' 우대'
            if re.search(r'능통',text):return english+' 필수'
    for language in ['Japanese','Mandarin','Cantonese','Chinese','Polish']:
        if re.search(rf'\b{language}\b.{{0,35}}(preferred|plus|advantage|not required)',body,re.I):
            return language+' 우대'
        if re.search(rf'(fluent|fluency|proficien\w*|native|business.level).{{0,45}}\b{language}\b|\b{language}\b.{{0,45}}(required|mandatory|essential)',body,re.I):
            nearby=re.search(rf'.{{0,60}}\b{language}\b.{{0,80}}',body,re.I)
            if nearby and re.search(r'preferred|plus|advantage|not required',nearby.group(),re.I): return language+' 우대'
            return language+' 필수'
    if country=='KR': return '한국어 · 추가 언어는 원문 확인'
    return '영어 능력 요구 · 추가 현지어 필수 표기 없음' if re.search(r'fluent.{0,15}English|English.{0,30}(fluen|proficien)',body,re.I) else '읽은 원문에 현지어 필수 조건 명시 없음'

def role_excluded(title):
    return bool(re.search(r'재무팀|회계팀|부동산|대체투자|NPL팀|심사역|AI에이전트|운용지원|미들업무|신탁회계|펀드회계|준법감시|마케팅|영업|사업개발|대체운용|business develop|internal controls|non.financial risk|compliance|software engineer|talent network|trading controls|sales and trading|operations engineer',title,re.I))

def parse_period(text):
    dates=[]
    for match in re.finditer(r'(?<!\d)(20\d{2})[.\-/년\s]?(\d{2})[.\-/월\s]?(\d{2})(?!\d)',text or ''):
        try: dates.append(datetime(*map(int,match.groups())).date().isoformat())
        except ValueError: pass
    return (dates[0],dates[-1]) if len(dates)>=2 else (None,dates[0] if dates else None)

def make_job(source,source_id,title,company,body,country,posted='',period='',application_url=''):
    if source.get('_raw'):
        return {'id':source['id']+'-'+str(source_id),'sourceId':source['id'],'sourceUrl':canonical(source.get('detailUrl','')),'title':title,'company':company,'body':body,'country':country,'postedAt':posted,'period':period,'applicationUrl':application_url,'complete':True,'accepting':source.get('adapter')=='greenhouse'}
    title=clean(title); body=clean(body)
    if role_excluded(title): return None
    category=category_for(title,body);level=junior_level(title,body)
    if not category or level is None or country not in COUNTRIES:return None
    language=language_status(body,country)
    if re.search(r'^(Japanese|Mandarin|Cantonese|Chinese|Polish) 필수$',language):return None
    start,end=parse_period(period)
    rolling=bool(re.search(r'채용\s*시\s*(까지|마감)|상시채용|상시 채용|rolling basis|until.{0,15}filled',body,re.I))
    # API presence alone cannot prove that all eligibility conditions are satisfied.
    status='open' if end and level!='확인 필요' and country=='KR' else 'review'
    if end and end<datetime.now(KST).date().isoformat():status='closed'
    if start and start>datetime.now(KST).date().isoformat():status='upcoming'
    if re.search(r'applications (are )?(now )?closed|position has been filled|채용이 종료|접수가 마감|접수마감|채용마감',title+' '+body,re.I):status='closed'
    if not end and posted:
        try:
            if datetime.fromisoformat(posted).date() < (datetime.now(KST)-timedelta(days=120)).date():return None
        except ValueError:pass
    evidence=[]
    if end:evidence.append('접수기간: '+period)
    if level!='확인 필요':evidence.append('인턴·신입 관련 표기 확인. 학위·졸업 시점 및 세부 자격은 원문 확인.')
    else:evidence.append('주니어 지원 여부 미확인.')
    if country!='KR':evidence.append('현지어·학위·졸업 시점·취업허가 확인 필요.')
    if not end:evidence.append('채용 시 마감 표기 확인.' if rolling else '확정 마감일 미확인.')
    return {'id':source['id']+'-'+str(source_id),'sourceId':source['id'],'sourceUrl':canonical(source.get('detailUrl','')),'applicationUrl':canonical(application_url),'title':title,'company':clean(company),'category':category,'country':country,'level':level,'eligibility':'조건별 원문 확인','languageStatus':language,'visaStatus':'국내 채용' if country=='KR' else '스폰서십·현지 취업허가 확인 필요','postedAt':posted,'startDate':start,'deadlineDate':end,'deadlineAt':None,'deadlineTimezone':COUNTRIES[country],'deadlineKind':'date' if end else 'rolling' if rolling else 'unknown','deadlineText':period or ('채용 시 마감' if rolling else '미확인'),'status':status,'evidence':' '.join(evidence),'lastVerifiedAt':utcnow()}

class Client:
    def __init__(self):
        self.session=requests.Session();self.session.headers['User-Agent']='QuantCareerDesk/1.0 (personal public job discovery; low rate)'
    def get(self,url,**kwargs):
        time.sleep(.3)
        r=self.session.get(url,timeout=25,**kwargs);r.raise_for_status();return r

def kofia(client,source,pages):
    found={}; failures=0; inspected=0
    source['_excluded']=set()
    for query in ['퀀트','ETF','인덱스','리스크','위험','파생','자산배분','멀티에셋','투자솔루션','신입','인턴']:
        print('kofia keyword:',query,flush=True)
        for page in range(1,pages+1):
            soup=BeautifulSoup(client.get(source['url'],params={'srchTp':'0','srchWord':query,'page':page}).content,'html.parser')
            rows=soup.select('tbody tr');links=[]
            for row in rows:
                a=row.select_one('a[href*="view.do?seq="]')
                if a:
                    dates=re.findall(r'20\d{2}-\d{2}-\d{2}',row.get_text())
                    if dates and dates[-1] < (datetime.now(KST)-timedelta(days=120)).date().isoformat():continue
                    links.append(urljoin(source['url'],a['href']))
            if not links:break
            old_page=True
            for url in links:
                seq=parse_qs(urlsplit(url).query)['seq'][0]
                if seq in found:continue
                try:
                    detail=BeautifulSoup(client.get(url).content,'html.parser'); info={}
                    for th in detail.select('th'):
                        td=th.find_next_sibling('td')
                        if td: info[clean(th.get_text())]=clean(td.get_text(' ',strip=True))
                    title=info.get('제목','');body=detail.select_one('#write')
                    if not title or body is None:raise ValueError('Detail markup changed')
                    posted=info.get('등록일','')[:10]
                    if posted and posted>=datetime.now(KST).date().replace(day=1).isoformat():old_page=False
                    link=detail.select_one('a[title*="관련 홈페이지"]')
                    item=make_job({**source,'detailUrl':url},seq,title,info.get('회원사명',''),body.get_text('\n',strip=True),'KR',posted,info.get('접수기간',''),link.get('href','') if link else '')
                    if source.get('_raw'):
                        item['images']=[urljoin(url,i['src']) for i in body.select('img[src]')]
                        item['documents']=[urljoin(url,a['href']) for a in detail.select('a[href]') if re.search(r'공고|채용안내|모집요강',a.get_text()) and re.search(r'\.pdf|\.docx',a.get_text()+' '+a['href'],re.I)]
                        item['needsAttachment']=bool(item['images'] or item['documents'])
                        item['complete']=not item['needsAttachment']
                    if item is None:source['_excluded'].add(source['id']+'-'+seq)
                    found[seq]=item;inspected+=1
                except (requests.RequestException,ValueError):failures+=1
            if len(links)<10:break
    result=[j for j in found.values() if j]
    return result, f'{inspected}개 상세 확인, {failures}개 상세 실패. 키워드별 최대 {pages}페이지.', failures

def greenhouse(client,source,pages):
    data=client.get(f'https://boards-api.greenhouse.io/v1/boards/{source["board"]}/jobs',params={'content':'true'}).json()
    if not isinstance(data.get('jobs'),list):raise ValueError('API schema changed')
    result=[];source['_excluded']=set()
    for item in data['jobs']:
        loc=item.get('location',{}).get('name','')
        country=next((c for pattern,c in [(r'Seoul|Korea','KR'),(r'London|United Kingdom','GB'),(r'Hong Kong','HK'),(r'Singapore','SG'),(r'Poland|Warsaw|Krak.w|Wroc.aw','PL'),(r'Tokyo|Japan','JP')] if re.search(pattern,loc,re.I)),None)
        if not country:continue
        raw=BeautifulSoup(item.get('content',''),'html.parser').get_text(' ',strip=True)
        # Greenhouse descriptions can be HTML-escaped twice.
        body=BeautifulSoup(raw,'html.parser').get_text(' ',strip=True)
        title=item.get('title','');metadata={x.get('name'):x.get('value') for x in (item.get('metadata') or [])}
        employment=metadata.get('Employment Type') or ''
        if re.search(r'intern|graduate|new grad',employment,re.I):title+=' · '+employment
        url=item.get('absolute_url','');job=make_job({**source,'detailUrl':url},item['id'],title,source['company'],body,country,application_url=url)
        if job: result.append(job)
        else:source['_excluded'].add(source['id']+'-'+str(item['id']))
    return result,f'공식 공개 채용 API 전체 {len(data["jobs"])}개에서 지정 국가·직무 후보 선별.',0

def merge(previous,incoming,at):
    jobs={j['id']:dict(j) for j in previous.get('jobs',[])};changes=list(previous.get('changes',[]))
    for item in incoming:
        old=jobs.get(item['id']);item=dict(item);item['firstSeenAt']=old.get('firstSeenAt',at) if old else at;item['lastSeenAt']=at
        item['contentHash']=digest({f:item.get(f) for f in CAREER_FIELDS})
        fields=[f for f in CAREER_FIELDS if old and old.get(f)!=item.get(f)]
        if not old or fields:
            kind='new' if not old else 'closed' if item['status']=='closed' and old.get('status')!='closed' else 'updated'
            changes.append({'id':digest([item['id'],kind,item['contentHash'],at])[:24],'jobId':item['id'],'kind':kind,'changedFields':fields,'detectedAt':at})
        jobs[item['id']]=item
    # A failed scan or disappearance does not delete previously seen jobs.
    for job in jobs.values():
        if job.get('deadlineDate') and job['deadlineDate']<datetime.now(ZoneInfo(job.get('deadlineTimezone','Asia/Seoul'))).date().isoformat() and job.get('status') not in ('closed','excluded'):
            job['status']='closed';changes.append({'id':digest([job['id'],'closed',at])[:24],'jobId':job['id'],'kind':'closed','changedFields':['status'],'detectedAt':at})
    return list(jobs.values()),changes[-3000:]

def run(pages=3,resume=False):
    # Retain the old entry point; every invocation fetches sources again.
    from refresh_jobs import run as refresh_all
    return refresh_all(pages=pages)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--pages',type=int,default=3);parser.add_argument('--resume',action='store_true');args=parser.parse_args()
    if not 1<=args.pages<=30:parser.error('--pages must be 1..30')
    from refresh_jobs import run as refresh_all
    refresh_all(pages=args.pages)
