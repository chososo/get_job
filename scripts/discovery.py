"""Bounded discovery for every registered source; failures are first-class results."""
import re
from urllib.parse import urljoin, urlsplit, quote, parse_qs
from bs4 import BeautifulSoup
from public_web import extract, soup_text
from collect import kofia, greenhouse, canonical, clean

RELEVANT=re.compile(r'퀀트|quant|신입|인턴|graduate|new grad|리스크|risk|ETF|파생|운용|리서치|research|투자|재무|자금|\bIR\b|M&A|채용|recruit',re.I)
DETAIL=re.compile(r'/recruit/\d+|/Recruit/RecruitView\?ID=|/wd/\d+|/post/|/jobs/view/|/jobs/[^/?]{8,}|/o/\d+|/articles/\d+|ArticleRead|jobnotice/view|jobs-view\?seq=|/Recruit/GI_Read/|view\.do\?seq=|artclView|ArticleSeq|bbsSeq|nttId',re.I)

def listing_urls(source,pages):
    sid=source['id']
    if sid=='fcb':return [f'https://www.fcbfi.org/blog/categories/job-postings'+(f'/page/{p}' if p>1 else '') for p in range(1,pages*3+1)]
    if sid=='jasoseol':return [f'https://jasoseol.com/search?division=1&page={p}' for p in range(1,pages+1)]
    if sid=='superookie':return ['https://www.superookie.com/jobs?search='+quote(k) for k in ['퀀트','운용','리스크','신입']]
    if sid=='wanted':return ['https://www.wanted.co.kr/wd/221698','https://www.wanted.co.kr/wdlist/508','https://www.wanted.co.kr/search?query='+quote('퀀트')+'&tab=position']
    if sid=='jobkorea':return ['https://www.jobkorea.co.kr/Search/?stext='+quote(k) for k in ['퀀트','자산운용 인턴','증권 신입','리스크']]
    if sid=='linkedin':return ['https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=quantitative%20intern&location='+quote(place)+'&f_E=1%2C2&start=0' for place in ['United Kingdom','Hong Kong','Singapore','Poland','Japan']]
    if sid=='naver-15279069':return [source['url']]
    if sid=='naver-kkbjob':return [f'https://cafe.naver.com/f-e/cafes/15279069/menus/{board}?viewType=L' for board in [569,604,670,622,610,648,628]]
    return [source['url']]

def links_from(html,url,source):
    soup=BeautifulSoup(html,'html.parser');links={};boards={}
    for a in soup.select('a[href]'):
        href=urljoin(url,a['href']);label=clean(a.get_text(' ',strip=True))
        if urlsplit(href).scheme not in ('http','https'):continue
        if 'cafe.naver.com' in url and re.search(r'menus/\d+',href) and re.search(r'채용|인턴|신입|금융|증권|운용|대기업',label):boards[href]=label
        if DETAIL.search(href):
            if source['id'] in ('jasoseol','catch','wanted','naver-kkbjob','naver-15279069') or RELEVANT.search(label):links[canonical(href)]=label
        elif urlsplit(href).hostname==urlsplit(url).hostname and re.search(r'채용|careers|recruit|채용공고',label,re.I):boards[href]=label
    # LinkedIn public search anchors and KKB's legacy article links can be empty-label anchors.
    return links,boards

def discover(source,client,renderer,pages=3,watch=None,progress=lambda x:None):
    source={**source,'_raw':True};watch=watch or []
    if source['id']=='naver-15279069':
        # This is the same cafe, with a certificate board URL. Visit it, but don't count its
        # sidebar articles as another cafe's recruitment feed.
        html=renderer.render(source['url'])
        return [],{'lists':1,'details':0,'failed':0,'truncated':False,'reason':'지정 게시판 254 열람. kkbjob과 같은 카페의 자격증 게시판입니다. 채용 7개 게시판 결과는 네이버 kkbjob 카페에 통합합니다.'}
    if source.get('adapter') in ('kofia','greenhouse'):
        rows,reason,failed=(kofia if source['adapter']=='kofia' else greenhouse)(client,source,pages)
        return rows,{'reason':reason,'failed':failed,'lists':pages if source['adapter']=='kofia' else 1,'details':len(rows),'truncated':source['adapter']=='kofia'}
    queue=listing_urls(source,pages);visited=set();candidates={};failed=0;lists=0;details=0;rendered=0
    max_lists=max(6,pages*4);max_details=100
    for item in watch:candidates[item['sourceUrl']]=item
    while queue and len(visited)<max_lists:
        url=queue.pop(0)
        if url in visited:continue
        visited.add(url);progress(source['name']+' · 목록 확인')
        try:
            html=client.get(url).text;links,boards=links_from(html,url,source)
            if (not links or 'cafe.naver.com' in url) and rendered<max_lists:
                try:html=renderer.render(url);rendered+=1;links,boards=links_from(html,url,source)
                except Exception:failed+=1
            lists+=1
            if DETAIL.search(url) and not re.search('/RecruitSearch|/jobs-guest/',url):candidates.setdefault(url,{'label':''})
            for href,label in links.items():candidates.setdefault(href,{'label':label})
            for href in boards:
                if href not in visited and href not in queue:queue.append(href)
            if not links and not DETAIL.search(url):failed+=1
        except Exception:failed+=1
    truncated=bool(queue) or len(candidates)>max_details
    result=[]
    # Existing active and verified watch URLs are checked before discovered pages.
    for url,hint in list(candidates.items())[:max_details]:
        progress(source['name']+' · 상세 '+str(details+1)+'/'+str(min(len(candidates),max_details)))
        try:
            html=client.get(url).text;raw=extract(html,url,source)
            if (not raw['complete'] and not raw.get('needsAttachment')) or 'cafe.naver.com' in url:
                try:html=renderer.render(url);raw=extract(html,url,source)
                except Exception:raw['complete']=False
            if not raw['title'] or len(raw['body'])<80:failed+=1;continue
            if hint.get('id'):raw['id']=hint['id']
            raw['label']=hint.get('label','')
            if not raw['company'] and hint.get('company'):raw['company']=hint['company']
            raw['curation']=hint if hint.get('verification') else None
            if hint.get('country'):raw['country']=hint['country']
            if not raw['complete'] and not raw.get('needsAttachment'):failed+=1
            result.append(raw);details+=1
        except Exception:failed+=1
    return result,{'lists':lists,'details':details,'failed':failed,'truncated':truncated,
                  'reason':f'목록 {lists}개 · 상세 {details}개 확인, 접근·본문 확인 실패 {failed}개. 목록 최대 {max_lists}개 / 상세 최대 {max_details}개.'}
