"""Public HTTP + anonymous rendering and source-grounded posting extraction."""
import ipaddress, json, os, re, socket, subprocess, threading, shutil, tempfile, zipfile
from pathlib import Path
from urllib.parse import urlsplit, urljoin, urlencode
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from collect import clean, canonical, COUNTRIES

ROOT=Path(__file__).resolve().parents[1]

def validate_url(url):
    u=urlsplit(url)
    if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or u.port not in (None,80,443):
        raise ValueError('공개 채용 URL만 허용합니다.')
    addresses=socket.getaddrinfo(u.hostname,u.port or (443 if u.scheme=='https' else 80),type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(x[4][0]).is_global for x in addresses):
        raise ValueError('로컬·사설 네트워크 주소는 수집하지 않습니다.')
    return url

class Client:
    def get(self,url,params=None,**kwargs):
        if params:url+=('&' if '?' in url else '?')+urlencode(params)
        for _ in range(6):
            validate_url(url)
            r=requests.get(url,timeout=(8,25),headers={'User-Agent':'Mozilla/5.0 (compatible; CareerDesk/2.0; public recruitment research)'},allow_redirects=False,stream=True)
            if r.is_redirect:
                url=urljoin(url,r.headers['Location']);r.close();continue
            r.raise_for_status();chunks=[];size=0
            for part in r.iter_content(65536):
                size+=len(part)
                if size>8_000_000:r.close();raise ValueError('본문 용량 제한 초과')
                chunks.append(part)
            r._content=b''.join(chunks);r._content_consumed=True
            if not r.encoding or r.encoding=='ISO-8859-1':r.encoding=r.apparent_encoding
            return r
        raise ValueError('리디렉션 횟수 초과')

class Renderer:
    def __init__(self):self.process=None;self.lock=threading.Lock();self.cache={}
    def render(self,url):
        with self.lock:
            if url in self.cache:return self.cache[url]
            if not self.process or self.process.poll() is not None:
                runtime=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node'
                node=shutil.which('node') or str(runtime/'bin/node')
                package=ROOT/'node_modules/playwright/index.mjs'
                if not package.exists():package=runtime/'node_modules/playwright/index.mjs'
                if not package.exists():raise ValueError('동적 페이지 수집 도구 설치 필요')
                env={**os.environ,'CAREER_PLAYWRIGHT':str(package),'PLAYWRIGHT_BROWSERS_PATH':str(ROOT/'.local/browsers')}
                self.process=subprocess.Popen([node,str(ROOT/'scripts/render_public.mjs')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,env=env)
            self.process.stdin.write(json.dumps({'url':validate_url(url)})+'\n');self.process.stdin.flush()
            import select
            if not select.select([self.process.stdout],[],[],50)[0]:self.process.kill();raise ValueError('동적 페이지 응답 시간 초과')
            result=json.loads(self.process.stdout.readline())
            if result.get('error'):raise ValueError(result['error'])
            self.cache[url]=result['html']
            return result['html']
    def close(self):
        if self.process:
            try:self.process.stdin.close();self.process.wait(timeout=8)
            except (OSError,subprocess.TimeoutExpired):self.process.terminate()
            self.process=None

def soup_text(soup):
    clone=BeautifulSoup(str(soup),'html.parser')
    for item in clone(['script','style','nav','footer','header','noscript']):item.decompose()
    return '\n'.join(clean(x) for x in clone.get_text('\n').splitlines() if clean(x))

def json_objects(soup):
    values=[]
    for tag in soup.select('script[type="application/ld+json"],script#__NEXT_DATA__'):
        try:values.append(json.loads(tag.string or tag.get_text()))
        except (ValueError,TypeError):pass
    return values

def walk(value):
    if isinstance(value,dict):
        yield value
        for item in value.values():yield from walk(item)
    elif isinstance(value,list):
        for item in value:yield from walk(item)

def extract(html,url,source):
    soup=BeautifulSoup(html,'html.parser');text=soup_text(soup);objects=json_objects(soup)
    raw={'sourceId':source['id'],'sourceUrl':canonical(url),'body':text,'country':'' if source.get('requireLocation') else source.get('country','KR'),
         'company':source.get('company',''),'title':'','complete':True}
    title=soup.select_one('h1') or soup.select_one('meta[property="og:title"]') or soup.title
    if title:raw['title']=clean(title.get('content') or title.get_text())
    if urlsplit(url).hostname in ('www.jobkorea.co.kr','jobkorea.co.kr'):
        # Interview tips and historical successful essays are unrelated to this opening.
        raw['body']=re.split(r'(?m)^이 기업의 취업 전략\s*$',raw['body'],maxsplit=1)[0]
    for value in objects:
        for obj in walk(value):
            if obj.get('@type')=='JobPosting':
                raw['postingRecognized']=True
                raw['title']=obj.get('title') or raw['title']
                desc=obj.get('description','')
                if isinstance(desc,str) and len(desc)>100:raw['body']=BeautifulSoup(desc,'html.parser').get_text('\n',strip=True)
                org=obj.get('hiringOrganization') or {}
                if isinstance(org,dict):raw['company']=org.get('name') or raw['company']
                locations=obj.get('jobLocation') or []
                if isinstance(locations,dict):locations=[locations]
                codes=[]
                for loc in locations:
                    address=loc.get('address',{}) if isinstance(loc,dict) else {}
                    if not isinstance(address,dict):continue
                    code=address.get('addressCountry','')
                    if isinstance(code,dict):code=code.get('name','')
                    code={'South Korea':'KR','Korea':'KR','대한민국':'KR','한국':'KR','Korea, Republic of':'KR','United Kingdom':'GB','UK':'GB','Hong Kong':'HK','Singapore':'SG','Poland':'PL','Japan':'JP','United States':'US'}.get(code,code)
                    if code:codes.append(code)
                if codes:raw['country']=next((c for c in codes if c in COUNTRIES),codes[0]);raw['locationRecognized']=True
                raw['employment']=str(obj.get('employmentType') or '')
                valid=obj.get('validThrough')
                if isinstance(valid,str) and re.match(r'20\d{2}-\d{2}-\d{2}',valid):
                    raw['deadlineDate']=valid[:10]
                    if re.search(r'(Z|[+-]\d{2}:\d{2})$',valid):raw['deadlineAt']=valid
                raw['postedAt']=str(obj.get('datePosted') or '')[:10]
    if urlsplit(url).hostname=='corp.fnguide.com' and '/Career/CareerInfoDetail' in url:
        heading=soup.select_one('#container h4');role=soup.select_one('.career--left .role1')
        if heading and role:
            from screening import qualification_text, requirements
            body=soup_text(role)
            raw.update(title=re.sub(r'^\[([^]]+)\]',r'\1 ·',clean(heading.get_text())),
                       company='에프앤가이드',body=body,roleRequirements=qualification_text(body),eligibility=requirements(body),
                       postingRecognized=True,complete='자격요건' in body)
            apply=soup.select_one('a[href*="/Career/ConfirmStep?no="]')
            if apply:raw['applicationUrl']=urljoin(url,apply['href'])
    # Wanted's actual status overrides the generic "상시채용" text.
    if 'wanted.co.kr/wd/' in url:
        for value in objects:
            data=value.get('props',{}).get('pageProps',{}).get('initialData') or {}
            if data.get('position'):
                raw['postingRecognized']=True
                raw.update(title=data['position'],company=(data.get('company') or {}).get('company_name',''),
                           closed=data.get('status')=='close' or bool(data.get('hidden')),accepting=data.get('status')=='open')
                raw['body']='\n'.join(str(data.get(k) or '') for k in ['main_tasks','requirements','preferred_points','benefits'])
                raw['roleRequirements']=str(data.get('requirements') or '')
                raw['employment']='신입' if (data.get('career') or {}).get('is_newbie') else '경력'
                raw['rolling']=not data.get('due_time') and data.get('status')=='open'
    if 'jasoseol.com/recruit/' in url:
        for value in objects:
            data=value.get('props',{}).get('pageProps',{}).get('initialEmploymentCompany') or {}
            if not data.get('name'):continue
            raw['postingRecognized']=True
            from screening import category
            role_names=[e.get('field','') for e in data.get('employments',[]) if category(e.get('field',''),data['name'])]
            raw.update(title=data.get('title') or raw['title'],company=data['name'],roles=' / '.join(role_names),
                       applicationUrl=data.get('employment_page_url',''),deadlineAt=data.get('end_time'),
                       deadlineDate=(data.get('end_time') or '')[:10] or None,startDate=(data.get('start_time') or '')[:10] or None)
            raw['body']=raw['title']+'\n모집분야: '+' / '.join(e.get('field','') for e in data.get('employments',[]))+'\n접수기간: '+str(data.get('start_time',''))+' ~ '+str(data.get('end_time',''))+'\n'+BeautifulSoup(data.get('content',''),'html.parser').get_text('\n',strip=True)
            raw['images']=[urljoin(url,img['src']) for img in BeautifulSoup(data.get('content',''),'html.parser').select('img[src]')]
            raw['needsAttachment']=bool(raw['images'])
            raw['complete']=not raw['needsAttachment']
            if (data.get('company_group') or {}).get('business_size')=='big_business' and role_names and all(category(x,'')=='기업 재무·전략투자' for x in role_names):raw['section']='corporate'
    if 'kofia.or.kr' in url:
        info={clean(th.get_text()):clean(th.find_next_sibling('td').get_text(' ',strip=True)) for th in soup.select('th') if th.find_next_sibling('td')}
        if soup.select_one('#write'):
            raw['postingRecognized']=True
            raw.update(title=info.get('제목',''),company=info.get('회원사명',''),period=info.get('접수기간',''),
                       postedAt=info.get('등록일','')[:10],body=soup_text(soup.select_one('#write')))
            raw['images']=[urljoin(url,i['src']) for i in soup.select('#write img[src]')]
            raw['documents']=[urljoin(url,a['href']) for a in soup.select('a[href]') if re.search(r'공고|채용안내|모집요강',a.get_text()) and re.search(r'\.pdf|\.docx',a.get_text()+' '+a['href'],re.I)]
            raw['needsAttachment']=bool(raw['images'] or raw['documents'])
            if raw['needsAttachment']:raw['complete']=False
    if 'cafe.naver.com' in url:
        article=soup.select_one('.article_viewer') or soup.select_one('.ArticleContentBox')
        if article:
            raw['postingRecognized']=True
            raw['body']=soup_text(article)
            h=soup.select_one('.title_text')
            if h:raw['title']=clean(h.get_text())
        else:raw['complete']=False
        for pattern,c in [('홍콩|Hong Kong','HK'),('싱가포르|Singapore','SG'),('런던|London','GB'),('폴란드|Poland','PL'),('도쿄|Tokyo|일본','JP')]:
            if re.search(pattern,raw['title'],re.I):raw['country']=c;break
    if 'careers.mobis.com/jobs-view' in url:
        title=soup.select_one('#viewTit');body=soup.select_one('.view-cont');period=soup.select_one('.date')
        if title and body:
            raw['postingRecognized']=True
            raw.update(title=clean(title.get_text()),company='현대모비스',body=soup_text(body),section='corporate',period=clean(period.get_text()) if period else '')
            top=soup.select_one('.view-info01')
            if top:raw['employment']=clean(top.get_text())
            if period:
                m=re.search(r'(20\d{2}-\d{2}-\d{2})\s+(\d{2}:\d{2})',period.get_text())
                if m:raw.update(deadlineDate=m[1],deadlineAt=m[1]+'T'+m[2]+':00+09:00')
    if 'catch.co.kr/NCS/RecruitInfoDetails/' in url:
        frames=[urljoin(url,f['src']) for f in soup.select('iframe[src]') if '/controls/recruitDetail/' in f['src']]
        raw['attachments']=frames
        raw['needsAttachment']=bool(frames);raw['complete']=not frames
        # The JSON-LD description covers this job; page recommendations are unrelated jobs.
        descriptions=[obj.get('description','') for value in objects for obj in walk(value) if obj.get('@type')=='JobPosting']
        raw['body']=raw['title']+'\n'+'\n'.join(str(x) for x in descriptions)
    if 'linkedin.com' in url:
        body=soup.select_one('.show-more-less-html__markup')
        if body:raw['body']=soup_text(body)
        raw['closed']=bool(re.search(r'no longer accepting applications',text[:5000],re.I))
        if body:raw['postingRecognized']=True
        company=soup.select_one('.topcard__org-name-link')
        if company:raw['company']=clean(company.get_text())
        # LinkedIn's generated validThrough is an ad expiry, not a verified employer deadline.
        raw['deadlineDate']=None;raw['deadlineAt']=None
        raw['accepting']=bool(soup.select_one('a[data-tracking-control-name*="apply"],button[data-tracking-control-name*="apply"]'))
        for pattern,c in [('Singapore','SG'),('Hong Kong','HK'),('London','GB'),('Poland|Warsaw|Krak.w','PL'),('Tokyo|Japan','JP')]:
            if not raw.get('locationRecognized') and re.search(pattern,text[:3000],re.I):raw['country']=c;break
    if 'greetinghr.com' in url:
        from greeting_roles import extract_greeting
        extract_greeting(raw,objects,text)
    images=[]
    for img in soup.select('img'):
        src=urljoin(url,img.get('src',''))
        if re.search(r'recruit|attach|jobpost|postfiles',src,re.I):images.append(src)
    raw['images']=list(dict.fromkeys(raw.get('images',[])+images))[:6]
    if len(raw['body'])<160:raw['complete']=False
    return raw

_ocr_lock=threading.Lock()
def read_images(raw,client):
    """OCR is local and keyless. Missing image text cannot become a verified recommendation."""
    for url in raw.get('documents',[])[:3]:
        try:
            r=client.get(url)
            with tempfile.NamedTemporaryFile() as f:
                f.write(r.content);f.flush();text=''
                if r.content.startswith(b'%PDF'):
                    python=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'
                    command=[str(python) if python.exists() else 'python3','-c','import sys,pypdf; r=pypdf.PdfReader(sys.argv[1]); print("\\n".join(p.extract_text() or "" for p in r.pages[:30]))',f.name]
                    text=subprocess.run(command,capture_output=True,text=True,timeout=30,check=True).stdout
                elif r.content.startswith(b'PK'):
                    with zipfile.ZipFile(f.name) as z:
                        info=z.getinfo('word/document.xml')
                        if info.file_size<2_000_000:text=BeautifulSoup(z.read(info),'xml').get_text(' ',strip=True)
            if len(text)>100:raw['body']+='\n[첨부 본문]\n'+text;raw['complete']=True
        except Exception:raw['complete']=False
    for url in raw.get('attachments',[]):
        try:
            soup=BeautifulSoup(client.get(url).text,'html.parser')
            raw['body']+='\n'+soup_text(soup)
            raw.setdefault('images',[]).extend(urljoin(url,i['src']) for i in soup.select('img[src]'))
        except Exception:raw['complete']=False
    # Decorative recruitment banners do not constitute job eligibility evidence.
    raw['images']=[u for u in raw.get('images',[]) if not re.search(r'sample\d+_|logo|pictogram',u,re.I)]
    if not raw.get('images'):return raw
    binary=ROOT/'.local/ocr-public'
    with _ocr_lock:
        if not binary.exists() and shutil.which('swiftc'):
            binary.parent.mkdir(exist_ok=True,mode=0o700)
            subprocess.run(['swiftc',str(ROOT/'scripts/ocr_public.swift'),'-o',str(binary)],capture_output=True,timeout=90,check=True)
    texts=[]
    for url in raw['images'][:3]:
        try:
            r=client.get(url)
            if not r.headers.get('Content-Type','').startswith('image/'):continue
            with tempfile.NamedTemporaryFile(suffix='.img') as f:
                f.write(r.content);f.flush()
                result=subprocess.run([str(binary),f.name],capture_output=True,text=True,timeout=35,check=True)
            if len(result.stdout.strip())>100:texts.append(result.stdout.strip())
        except Exception:pass
    if texts:
        raw['body']+='\n[채용 이미지에서 읽은 본문]\n'+'\n'.join(texts)
        raw['complete']=True;raw['ocr']=True
    elif raw.get('needsAttachment'):raw['complete']=False
    return raw
