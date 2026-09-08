"""Conservative, evidence-backed rules shared by manual and scheduled refresh."""
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from collect import clean, category_for, language_status, COUNTRIES, parse_period, digest, utcnow

VERSION = '2026-09-08.4'
PREFERRED = re.compile(r'우대|preferred|advantage|a plus|not required|무관', re.I)

def experience_requirement(body):
    # Evaluate individual lines to avoid an unrelated later preference cancelling a requirement.
    for line in re.split(r'[\n;•]|(?<=[.!?])\s+', body):
        for match in re.finditer(r'(?:관련\s*(?:업무|분야)|경력|실무|experience).{0,25}?(\d{1,2})\s*(?:년|years?)\s*(?:이상|\+|required|minimum)|(?:at least|minimum(?: of)?)\s*(\d{1,2})\s*years?|(?<!\d)(\d{1,2})\+?\s*years?.{0,30}?experience|(?<!\d)(\d{1,2})\s*년\s*이상.{0,12}(?:경력|업무|경험)', line, re.I):
            near = line[max(0, match.start()-15):match.end()+18]
            if re.search(r'0\s*[-–~]\s*$',line[max(0,match.start()-6):match.start()]):continue
            if not PREFERRED.search(near) and max(int(x) for x in match.groups() if x) >= 1:
                return clean(near)
    return ''

def category(title, body):
    title=re.sub(r'^\[[^\]]+\]\s*','',title)
    found = category_for(title, body)
    if found: return found
    if re.search(r'기업분석|산업분석|equity research|\bRA\b', title, re.I): return '기업·산업 리서치'
    if re.search(r'리서치|research associate',title,re.I) and re.search(r'금융|주식|투자|증권|자산|equity|investment|asset|portfolio',title+' '+body,re.I):return '기업·산업 리서치'
    if re.search(r'투자관리|전략투자|M&A|재무|자금|\bIR\b|investor relations|corporate finance', title, re.I): return '기업 재무·전략투자'
    if re.search(r'운용지원|운용\s*인턴|OCIO|투자.{0,8}인턴', title, re.I): return '자산운용·자산배분'
    if re.search(r'S&T\s*운용|자산운용|\bPI\b',title,re.I):return '자산운용·자산배분'
    if '인게이지먼트' in title and re.search(r'기업가치|저평가|주주환원|SOTP',body):return '기업·산업 리서치'
    if '상품전략' in title and re.search(r'펀드|ETF|투자신탁',body):return '자산운용·자산배분'
    return None

def level_for(title, body):
    if re.search(r'인턴|intern(?:ship)?|summer (?:analyst|associate)', title, re.I): return '인턴'
    if re.search(r'아르바이트|part.time|assistant', title, re.I): return '아르바이트'
    if re.search(r'신입|new grad|graduate|entry.level|junior', title, re.I): return '신입'
    if re.search(r'경력\s*무관|신입\s*(?:채용|지원|가능|및)|no (?:prior )?experience', body, re.I): return '신입'
    if re.search(r'인턴\s*(?:모집|채용)|고용형태.{0,10}인턴', body): return '인턴'
    return '확인 필요'

def requirements(body):
    lines=[clean(x) for x in body.splitlines() if re.search(r'자격|요건|학사|대졸|졸업|재학|학위|필수|경력|우대|Python|SQL|C\+\+|require|degree|graduat|enroll|visa|sponsor|language',x,re.I)]
    return ' · '.join(dict.fromkeys(lines))[:1500] or '본문에서 지원 자격을 확인하지 못했습니다.'

def classify(raw, ai=None):
    title=clean(raw['title']); body=raw.get('body',''); country=raw.get('country','KR')
    if country not in COUNTRIES:return None
    roles=raw.get('roles',''); focus=title+(' · '+roles if roles else '')
    cat=category(focus, body)
    if not cat and not ai:return None
    if cat=='기업 재무·전략투자' and raw.get('section')!='corporate':return None
    level=level_for(title+' '+raw.get('employment',''), body)
    role_requirements=raw.get('roleRequirements')
    mixed_title=bool(re.search(r'경력|experienced',title,re.I) and re.search(r'신입|인턴|intern',title,re.I))
    if mixed_title and not role_requirements:
        block=re.search(r'\[(?:채용전환형\s*)?(?:인턴|신입)[^\]\n]{0,25}\]\s*([^\[]+)',body)
        if block:role_requirements=block[1];level='인턴' if '인턴' in block[0] else '신입'
    exp=experience_requirement(role_requirements or body)
    lang=language_status(role_requirements or body,country)
    # Mixed recruitments need a verified role-specific section; title alone cannot override requirements.
    mixed=bool(exp and mixed_title and not role_requirements)
    reason=''; status='review'
    if ai:
        cat=ai['category'];level=ai['level']
        if cat=='무관':return None
        reason=ai['reason']
        if ai['decision']=='exclude' or ai['requiredLocalLanguage']:status='excluded'
        elif ai['decision']=='include':status='open'
    elif level!='확인 필요' and raw.get('complete',True):status='open'
    if re.search(r'operations engineer|trading desk operations|\bNPL\b|준법감시|부동산',title,re.I):status='excluded';reason='운영·준법·부동산 중심 직무로 현재 희망 분야에서 제외'
    if re.match(r'Sales and Trading',title,re.I):status='review';reason='세일즈·트레이딩 복합 직무 · 희망하는 계량 업무와의 연관성 확인 필요'
    if re.search(r'기자|플랫폼 운영',title):status='review';reason='여러 직무가 섞여 있어 기업분석·리서치 담당 업무와 지원 트랙 확인 필요'
    if re.search(r'if you are currently a student or recent graduate.{0,100}see our Campus postings',body,re.I):status='review';reason='학생·신입은 별도 Campus 공고로 안내하는 공고입니다.'
    if raw.get('excludeReason'):status='excluded';reason=raw['excludeReason']
    if exp and not mixed:status='excluded';reason='필수 경력 불일치: '+exp
    elif mixed:status='review';reason='신입·경력 복수 직무의 자격요건을 분리해서 확인해야 합니다.'
    if re.search(r'^(Japanese|Mandarin|Cantonese|Chinese|Polish) 필수$',lang):status='excluded';reason=lang+' 조건으로 제외'
    if level=='확인 필요' and status!='excluded':status='review';reason=reason or '인턴·신입 지원 가능 여부가 본문에 명확하지 않습니다.'
    if re.search(r'부장\s*이상|과.?차장급|시니어|\bsenior\b|vice president|principal|책임자',title,re.I) and level=='확인 필요':status='excluded';reason='경력·책임자급 직무'
    start,end=parse_period(raw.get('period',''))
    start=raw.get('startDate') or start
    if not end:
        # Only a labelled application period; never infer deadlines from arbitrary dates.
        for line in body.splitlines():
            if re.search(r'지원기간|접수기간|접수기한|마감일|지원마감|application deadline',line,re.I):
                dates=re.findall(r'(20\d{2})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})',line)
                if dates:
                    try:end=datetime(*map(int,dates[-1])).date().isoformat()
                    except ValueError:pass
    end=raw.get('deadlineDate') or end
    deadline_at=raw.get('deadlineAt')
    if ai and not end and ai.get('deadlineDate') and re.fullmatch(r'20\d{2}-\d{2}-\d{2}',ai['deadlineDate']):
        try:datetime.fromisoformat(ai['deadlineDate']);end=ai['deadlineDate']
        except ValueError:pass
    rolling=raw.get('rolling',False) or bool(re.search(r'채용\s*시\s*(?:까지|마감)|상시\s*채용|rolling basis|until.{0,15}filled',body,re.I))
    if not end and not rolling and not raw.get('accepting') and status=='open':status='review';reason=reason or '현재 접수 여부·마감 확인 필요'
    if not raw.get('complete',True) and status=='open':status='review';reason='첨부·동적 본문 등 일부 내용을 읽지 못했습니다.'
    closed=raw.get('closed') or (ai and ai.get('closed')) or re.search(r'no longer accepting applications|applications (?:are )?(?:now )?closed|position has been filled|채용이 종료|접수가 마감',body,re.I)
    today=datetime.now(ZoneInfo(COUNTRIES[country])).date().isoformat()
    if closed or (end and end<today) or (deadline_at and datetime.fromisoformat(deadline_at.replace('Z','+00:00'))<datetime.now(timezone.utc)):status='closed';reason='접수 종료 확인'
    if status=='open' and start and start>today:status='upcoming'
    eligibility=ai.get('eligibility') if ai else raw.get('eligibility') or requirements(role_requirements or body)
    if eligibility=='본문에서 지원 자격을 확인하지 못했습니다.' and status=='open':status='review';reason='지원 자격 본문 확인 필요'
    if raw.get('curationValid'):
        eligibility=raw.get('eligibility') or eligibility
    company=raw.get('company','')
    if not company:
        match=re.match(r'\[([^\]]+)\]',title)
        company=match[1] if match else '회사명 원문 확인'
        if not match and status=='open':status='review';reason='공고의 회사명 확인 필요'
    return {'id':raw.get('id') or raw['sourceId']+'-'+digest(raw['sourceUrl'])[:16],
            'sourceId':raw['sourceId'],'sourceUrl':raw['sourceUrl'],'applicationUrl':raw.get('applicationUrl',''),
            'title':title+(' · '+roles if roles and roles not in title else ''),'company':company,
            'country':country,'category':cat,'section':raw.get('section') or ('corporate' if cat=='기업 재무·전략투자' else 'finance'),
            'level':level,'eligibility':eligibility,'languageStatus':lang,'visaStatus':'국내 채용' if country=='KR' else '취업허가·스폰서십은 개인 조건과 원문 확인 필요',
            'postedAt':raw.get('postedAt',''),'startDate':start,'deadlineDate':end,'deadlineAt':deadline_at,
            'deadlineTimezone':COUNTRIES[country],'deadlineKind':'date' if end else 'rolling' if rolling else 'unknown',
            'deadlineText':raw.get('period') or ('채용 시 마감' if rolling else '마감일 미공개'),
            'status':status,'evidence':reason or ('원문에서 주니어 모집 확인. '+(ai.get('eligibleRoles','') if ai else roles)),
            'lastVerifiedAt':utcnow(),'screeningMode':'astra' if ai else 'rules','screeningVersion':VERSION}
