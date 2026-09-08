"""Split structured Greeting openings by job, retaining one shared application URL."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from collect import digest, clean
from screening import category, qualification_text


def split_roles(raw):
    if not raw.get('greetingDetail'):return [raw]
    detail=BeautifulSoup(raw['greetingDetail'],'html.parser')
    common=detail.get_text('\n',strip=True).split('채용 직무 안내',1)[0]
    common=common.split('[채용 절차]',1)[0]+'\n동일 공고 내 하나의 직무만 지원 가능 (중복지원 불가).'
    result=[]
    for heading in detail.select('h2'):
        name=clean(heading.get_text(' ',strip=True))
        if not name:continue
        nodes=[]
        for sibling in heading.next_siblings:
            if getattr(sibling,'name',None)=='h2' and clean(sibling.get_text()):break
            nodes.append(str(sibling))
        body=BeautifulSoup(''.join(nodes),'html.parser').get_text('\n',strip=True)
        cat=category(name,body)
        if not cat:continue
        req=qualification_text(body)
        if not re.search(r'지원\s*자격',body):continue
        # Employment metadata is per role; never borrow another role's new-grad label.
        compact=lambda s:re.sub(r'\s+','',s)
        metadata=raw.get('greetingHeader','')
        m=re.search(re.escape(compact(name))+r'.{0,30}?경력(무관|\d+년이상)',compact(metadata))
        employment='신입' if m and m[1]=='무관' else '경력' if m else ''
        key=digest(name)[:12]
        result.append({**raw,'id':raw['sourceId']+'-role-'+digest(raw['sourceUrl'])[:8]+'-'+key,
                       'roleKey':key,'title':name,'roles':'','body':common+'\n'+body,
                       'roleRequirements':common+'\n'+req,'employment':employment,
                       'eligibility':clean(common+' '+req)[:1500],
                       'section':'corporate' if cat=='기업 재무·전략투자' else 'finance',
                       'complete':True,'images':[],'needsAttachment':False})
    return result or [raw]


def extract_greeting(raw, objects, page_text):
    from public_web import walk
    for value in objects:
        for obj in walk(value):
            if not (obj.get('openingId') and obj.get('detail') and obj.get('title')):continue
            title=obj['title'];m=re.match(r'\[([^]]+)\]',title)
            raw.update(title=title,company=m[1] if m else raw.get('company',''),
                       greetingDetail=obj['detail'],greetingHeader=page_text.split('공통사항',1)[0],
                       body=BeautifulSoup(obj['detail'],'html.parser').get_text('\n',strip=True),
                       postingRecognized=True,closed=obj.get('status')!='OPEN',accepting=obj.get('status')=='OPEN')
            if obj.get('dueDate'):
                date=datetime.fromisoformat(obj['dueDate'].replace('Z','+00:00')).astimezone(ZoneInfo('Asia/Seoul'))
                raw.update(deadlineAt=date.isoformat(),deadlineDate=date.date().isoformat(),period=date.strftime('%Y-%m-%d %H:%M KST'))
            return
