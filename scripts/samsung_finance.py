"""Read Samsung's public company cards and structured job-specific requirements."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from collect import clean
from screening import category, classify


def parse_posting(data,source):
    if not data.get('success'):raise ValueError('Samsung detail unavailable')
    d=data['data'];head=d['result'];rows=[]
    for role in d.get('items',[]):
        name=role.get('titleKr','');task=role.get('taskKr') or ''
        if re.search(r'세일즈|영업|마케팅',name):continue
        cat=category(name,head.get('cmpNameKr','')+' '+task)
        if not cat:continue
        req=(head.get('qlfctKr') or '')+'\n'+(role.get('qlfctKr') or '')
        body='[지원 자격]\n'+req+'\n[담당 업무]\n'+task+'\n[우대 사항]\n'+(role.get('favorKr') or '')
        raw={'sourceId':source['id'],'sourceUrl':'https://www.samsungcareers.com/hr/?no='+str(head['seq']),
             'title':head['title']+' · '+name,'company':head['cmpNameKr'],'body':body,
             'roleRequirements':req,'complete':bool(req.strip()) and not bool(role.get('files')),'country':'KR',
             'section':'corporate' if cat=='기업 재무·전략투자' else 'finance',
             'accepting':bool(head.get('isOpened')),'closed':not bool(head.get('isOpened'))}
        verdict=classify(raw)
        if verdict and verdict['status'] not in ('excluded',):rows.append((raw,name,req,task))
    if not rows:return []
    # All retained roles have independently passed the position/experience gate.
    raw=dict(rows[0][0]);raw['title']=head['title'];raw['roles']=' / '.join(x[1] for x in rows)
    raw['complete']=all(x[0]['complete'] for x in rows)
    raw['body']='\n\n'.join(x[0]['body'] for x in rows)
    raw['roleRequirements']='\n'.join(x[2] for x in rows)
    raw['eligibility']=clean(head.get('qlfctKr') or '')+' · '+' · '.join(x[1]+': '+clean(x[2].replace(head.get('qlfctKr') or '', '')) for x in rows)
    raw['eligibility']=raw['eligibility'][:1500]
    raw['id']=source['id']+'-'+str(head['seq']);raw['applicationUrl']=raw['sourceUrl'];raw['postingRecognized']=True
    for field,key in [('startdate','startDate'),('enddate','deadlineDate')]:
        date=datetime.strptime(head[field],'%Y%m%d%H%M').replace(tzinfo=ZoneInfo('Asia/Seoul'))
        raw[key]=date.date().isoformat()
        if key=='deadlineDate':raw['deadlineAt']=date.isoformat();raw['period']=date.strftime('%Y-%m-%d %H:%M KST')
    return [raw]


def discover_samsung(source,client,renderer,watch,progress):
    result=[];failed=lists=details=0;empty=[];seen=set();ids={w['sourceUrl']:w.get('id') for w in watch}
    for company,url in source['companyPages'].items():
        progress(company+' · 공식 채용 목록 확인')
        try:
            html=renderer.render(url);soup=BeautifulSoup(html,'html.parser')
            if company not in soup.get_text():raise ValueError('Company page unavailable')
            cards=soup.select('a[name="btnRecruit"][data-value]');lists+=1
            if not cards:empty.append(company)
            for card in cards:
                seq=card['data-value'].replace(',','')
                if not seq.isdigit() or seq in seen:continue
                seen.add(seq)
                try:
                    data=client.get('https://www.samsungcareers.com/recruit/detail.data',params={'seqno':seq,'strCode':''}).json()
                    rows=parse_posting(data,source);details+=1
                    for raw in rows:
                        if ids.get(raw['sourceUrl']):raw['id']=ids[raw['sourceUrl']]
                        result.append(raw)
                except Exception:failed+=1
        except Exception:failed+=1
    return result,{'lists':lists,'details':details,'failed':failed,'truncated':False,
                   'reason':f'삼성 계열 {lists}개 공식 목록 · 상세 {details}개 확인. 현재 목록에 공고 없음: '+(', '.join(empty) or '없음')}
