"""Conservative, evidence-backed rules shared by manual and scheduled refresh."""
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from collect import clean, category_for, language_status, COUNTRIES, parse_period, digest, utcnow

VERSION = '2026-09-14.1'
NON_POSTING = re.compile(r'교재|책\s*팝니다|수강|수험|인강\s*공유|강의\s*공유|판매합니다|자격증.*(?:판매|강의)')
PREFERRED = re.compile(r'우대|preferred|advantage|a plus|not required', re.I)

def qualification_text(body):
    """Exclude organization histories and preference sections, not neighbouring requirements."""
    selected=[]; section='unknown'
    for line in body.replace('\u200b','').splitlines():
        heading=re.sub(r'^\s*\d+[.)、]\s*','',clean(line)).strip('[]:： •ㆍ-□■○')
        label,separator,inline=heading.partition(':') if ':' in heading else heading.partition('：')
        if re.fullmatch(r'(?:지원\s*자격|자격\s*요건|필수\s*(?:사항|요건)|requirements|qualifications|필독\s*사항)(?:\s*(?:및|/)\s*우대\s*(?:사항|요건|조건))?(?:\s*[:：])?',label.strip(),re.I):
            section='required'
            if separator:selected.append(inline)
            continue
        if re.fullmatch(r'(?:우대\s*(?:사항|조건|요건)|preferred(?: qualifications)?|조직\s*소개|회사\s*소개|업무\s*내용|담당\s*업무|benefits)',heading,re.I):section='other';continue
        if section!='other':selected.append(line)
    return '\n'.join(selected)

def experience_requirement(body):
    # Job boards render the experience label and its value on separate lines.
    body=re.sub(r'(?m)^\s*경력\s*\n(?:\s*경력\s*\n)?\s*(\(?\d{1,2}\s*(?:[-–~]\s*\d{1,2}\s*)?년[^\n]*)',r'경력 \1',body)
    fallback=''
    for line in re.split(r'[\n;,•ㆍ·]|\s+[/|]\s+|\s+(?=(?:Python|SQL|Excel)\b|학력|전공)|\s+및\s+|\s+and\s+(?=[A-Z][a-zA-Z+#]+\s+(?:preferred|우대))|(?<=[.!?])\s+', qualification_text(body)):
        # Future onboarding/rotations are not prior professional experience.
        if re.search(r'(?:입사|채용|합격)\s*(?:후|이후).{0,90}(?:교육|연수|수습|공정\s*경험|순환|체험|경험을\s*통해)',line) and not re.search(r'필수|보유자|경력자',line):continue
        if PREFERRED.search(line) or re.search(r'신입\s*(?:또는|및)|\d+\s*년\s*이하',line):continue
        if re.search(r'경력(?:자|직)?\s*(?:필수|만\s*(?:지원|가능))|(?:관련|유관|동종).{0,12}경력(?:자|\s*보유자)|경력직\s*(?:채용|모집)',line):fallback=fallback or clean(line)
        for match in re.finditer(r'(?<![\d~–-])(\d{1,2})\s*(?:[-–~]\s*\d{1,2}\s*)?(?:년|years?)\s*\+?',line,re.I):
            if int(match[1])<1:continue
            if re.search(r'경력|경험|실무|관련\s*(?:업무|분야)|experience|at least|minimum',line,re.I):return clean(line)
    return fallback

def position_for(body):
    match=re.search(r'(?:모집\s*직위|모집\s*직급|채용\s*직위|채용\s*직급|직급|seniority level)\s*[:：]?\s*([^\n]{1,70})',body,re.I)
    return clean(match[1]) if match else ''

def senior_position(position):
    return bool(re.search(r'대리|과장|차장|부장|팀장|실장|본부장|수석|책임|시니어|senior|vice president|director|principal|head of',position,re.I))

def career_only(title):
    if re.search(r'\bCRO\b|chief risk officer|risk management head|리스크\s*관리\s*총괄\s*실장',title,re.I):return True
    if re.search(r'신입|인턴|intern|new grad|경력\s*무관|무경력',title,re.I):return False
    return bool(re.search(r'경력(?:직|자)?|experienced|\bsenior\b|시니어|과장|차장|부장|팀장급|실장급|vice president|principal|책임자',title,re.I))

def scope_exclusion(title, body):
    if re.search(r'고용\s*형태\s*[:：]?\s*프리랜서',body):
        return '프리랜서 계약으로 인턴·신입 근로자 채용 범위에서 제외'
    if re.search(r'추천\s*\d+권|FCB\s*어쏘.*모집',title,re.I):
        return '도서 추천·교육 프로그램으로 기업의 인턴·신입 채용 공고가 아님'
    if re.search(r'펀드회계|신탁회계|사무보조|경영지원.*사무직|유튜브.*컴플라이언스',title):
        return '펀드회계·일반 사무·준법 업무로 희망 금융 분석·운용 직무에서 제외'
    duties=re.search(r'담당\s*업무[\]:：\s]*([^\[]+)',body)
    if duties and re.search(r'국내\s*부동산\s*펀드\s*운용',duties[1]):
        return '담당 업무가 부동산 펀드 운용·임대·공사 관리 중심으로 희망 분야에서 제외'
    if re.search(r'리스크제로',title) and re.search(r'산업\s*안전|건설\s*현장|중대\s*재해',body):
        return '산업안전 시스템 직무로 금융리스크 업무에 해당하지 않음'
    return ''

def audit_existing(job):
    """Never certify old summaries as freshly read originals."""
    if job.get('status') in ('closed','excluded'):return job
    reason=''
    if career_only(job['title']):reason='경력 전용 공고: 인턴·신입 지원 근거 없음'
    if NON_POSTING.search(job['title']):reason='채용 공고가 아닌 학습·판매 게시물'
    if re.search(r'\[\s*마감\s*\]',job['title']):return {**job,'status':'closed','evidence':'제목에 접수 마감 명시'}
    if reason:return {**job,'status':'excluded','evidence':reason,'screeningVersion':VERSION}
    if job.get('screeningVersion')!=VERSION:return {**job,'status':'review','evidence':'심사 규칙 변경: 원문 재수집·직무별 자격 재검증 대기'}
    return job

def category(title, body):
    title=re.sub(r'^\[[^\]]+\]\s*','',title)
    found = category_for(title, body)
    if found: return found
    if re.search(r'평가모형|신용평가.*(?:분석|컨설팅)',title): return '금융리스크'
    if '계리' in title: return '금융리스크'
    if '투자자산관리' in title: return '자산운용·자산배분'
    if '데이터 애널리스트' in title and re.search(r'신용|재무|금융',body): return '금융리스크'
    regulatory_ra=bool(re.search(r'화장품|의약품|인허가|regulatory affairs',body,re.I))
    if re.search(r'기업분석|산업분석|equity research',title,re.I) or (re.search(r'\bRA\b',title,re.I) and not regulatory_ra):return '기업·산업 리서치'
    if re.search(r'리서치|research associate',title,re.I) and re.search(r'금융|주식|투자|증권|자산|equity|investment|asset|portfolio',title+' '+body,re.I):return '기업·산업 리서치'
    if re.search(r'투자관리|전략투자|M&A|재무|자금|\bIR\b|investor relations|corporate finance', title, re.I): return '기업 재무·전략투자'
    if re.search(r'운용지원|운용\s*인턴|OCIO|투자.{0,8}인턴', title, re.I): return '자산운용·자산배분'
    if re.search(r'S&T\s*운용|자산운용|\bPI\b',title,re.I):return '자산운용·자산배분'
    if '인게이지먼트' in title and re.search(r'기업가치|저평가|주주환원|SOTP',body):return '기업·산업 리서치'
    if '상품전략' in title and re.search(r'펀드|ETF|투자신탁',body):return '자산운용·자산배분'
    return None

def level_for(title, body):
    if re.search(r'인턴|intern(?:ship)?|summer (?:analyst|associate)', title, re.I): return '인턴'
    if re.search(r'아르바이트|part.time', title, re.I): return '아르바이트'
    if re.search(r'신입|new grad|graduate|entry.level|junior', title, re.I): return '신입'
    if re.search(r'경력\s*무관|신입\s*(?:채용|지원|가능|및)|no (?:prior )?experience', body, re.I): return '신입'
    if re.search(r'인턴\s*(?:모집|채용)|고용형태.{0,10}인턴', body): return '인턴'
    return '확인 필요'

def requirements(body):
    groups={'지원자격':[],'우대사항(필수 아님)':[],'지원자격·우대사항(원문 구분)':[]};current=None
    for line in body.splitlines():
        line=clean(line)
        heading=re.sub(r'^\d+[.)、]\s*','',line).strip('[]:： •ㆍ-')
        if re.match(r'^(?:지원\s*자격|자격\s*(?:요건|및)|필수\s*(?:사항|요건)|requirements|qualifications)',heading,re.I):
            current='지원자격·우대사항(원문 구분)' if '우대' in heading else '지원자격'
            if ':' in heading:groups[current].append(heading.split(':',1)[1])
            continue
        if re.match(r'^(?:우대\s*(?:사항|조건|요건)|preferred qualifications)',heading,re.I):
            current='우대사항(필수 아님)';continue
        if re.match(r'^\d+[.)、]\s*',line) or re.search(r'^(?:담당\s*업무|업무\s*내용|제출|지원\s*방법|전형|개인정보|조직\s*소개)',heading):current=None
        if current and line:groups[current].append(line.strip(' •ㆍ-'))
    parts=[label+': '+' / '.join(dict.fromkeys(lines))[:650] for label,lines in groups.items() if lines]
    if parts:return ' · '.join(parts)[:1500]
    lines=[clean(x) for x in body.splitlines() if re.search(r'자격|요건|학사|대졸|졸업|재학|학위|필수|경력|우대|Python|SQL|C\+\+|require|degree|graduat|enroll|visa|sponsor|language',x,re.I)]
    return ' · '.join(dict.fromkeys(lines))[:1500] or '본문에서 지원 자격을 확인하지 못했습니다.'

def classify(raw, ai=None):
    title=clean(raw['title']); body=raw.get('body',''); country=raw.get('country','KR')
    country={'한국':'KR','대한민국':'KR','Korea, Republic of':'KR'}.get(country,country)
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
        if block and category(block[1],block[1]):role_requirements=block[1];level='인턴' if '인턴' in block[0] else '신입'
    position=raw.get('recruitmentPosition') or position_for(role_requirements or body)
    if not position and re.search(r'3급\s*신입',title):position='3급 신입사원'
    exp=experience_requirement(role_requirements or body)
    lang=language_status(role_requirements or body,country)
    # Mixed recruitments need a verified role-specific section; title alone cannot override requirements.
    mixed=bool(mixed_title and not role_requirements)
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
    # Hard exclusions win over every AI and soft-review branch.
    if career_only(title) or raw.get('employment')=='경력' or (ai and ai.get('level')=='경력'):
        status='excluded';reason='경력 전용 공고: 인턴·신입 지원 근거 없음'
    focused_roles=[r.strip() for r in roles.split(' / ') if r.strip()]
    if focused_roles and all(re.search(r'경력|experienced',r,re.I) and not re.search(r'신입|인턴|intern|무관',r,re.I) for r in focused_roles):
        status='excluded';reason='희망 직무는 경력 전용: '+roles
    if re.search(r'\bsenior\b|시니어|vice president|principal|과장|차장|부장|책임자',title,re.I) and not mixed_title:
        status='excluded';reason='경력·책임자급 직무'
    if ai and (ai.get('decision')=='exclude' or ai.get('requiredLocalLanguage')):
        status='excluded';reason=ai.get('reason') or 'AI 심사에서 필수 조건 불일치 확인'
    if raw.get('excludeReason'):status='excluded';reason=raw['excludeReason']
    if senior_position(position):status='excluded';reason='모집 직위 불일치: '+position+(' · 필수 경력: '+exp if exp else '')
    if NON_POSTING.search(title):status='excluded';reason='채용 공고가 아닌 학습·판매 게시물'
    out_of_scope=scope_exclusion(title,body)
    if out_of_scope:status='excluded';reason=out_of_scope
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
    closed=raw.get('closed') or re.search(r'\[\s*마감\s*\]',title) or (ai and ai.get('closed')) or re.search(r'no longer accepting applications|applications (?:are )?(?:now )?closed|position has been filled|채용이 종료|접수가 마감',body,re.I)
    today=datetime.now(ZoneInfo(COUNTRIES[country])).date().isoformat()
    if closed or (end and end<today) or (deadline_at and datetime.fromisoformat(deadline_at.replace('Z','+00:00'))<datetime.now(timezone.utc)):status='closed';reason='접수 종료 확인'
    if status=='open' and start and start>today:status='upcoming'
    eligibility=ai.get('eligibility') if ai else raw.get('eligibility') or requirements(role_requirements or body)
    if eligibility=='본문에서 지원 자격을 확인하지 못했습니다.' and status=='open':status='review';reason='지원 자격 본문 확인 필요'
    if country!='KR' and status=='open':
        status='review';reason='주니어 모집 요건은 확인했으나 현지 취업허가·스폰서십 조건 확인 필요'
    if raw.get('curationValid'):
        eligibility=raw.get('eligibility') or eligibility
    company=raw.get('company','')
    if not company:
        match=re.match(r'\[([^\]]+)\]',title)
        company=match[1] if match else '회사명 원문 확인'
        if not match and status=='open':status='review';reason='공고의 회사명 확인 필요'
    return {'id':raw.get('id') or raw['sourceId']+'-'+digest(raw['sourceUrl'])[:16],
            'roleKey':raw.get('roleKey',''),'sourceId':raw['sourceId'],'sourceUrl':raw['sourceUrl'],'applicationUrl':raw.get('applicationUrl',''),
            'title':title+(' · '+roles if roles and roles not in title else ''),'company':company,
            'country':country,'category':cat,'section':raw.get('section') or ('corporate' if cat=='기업 재무·전략투자' else 'finance'),
            'recruitmentPosition':position,'requiredExperience':exp,'level':level,'eligibility':eligibility,'languageStatus':lang,'visaStatus':'국내 채용' if country=='KR' else '취업허가·스폰서십은 개인 조건과 원문 확인 필요',
            'postedAt':raw.get('postedAt',''),'startDate':start,'deadlineDate':end,'deadlineAt':deadline_at,
            'deadlineTimezone':COUNTRIES[country],'deadlineKind':'date' if end else 'rolling' if rolling else 'unknown',
            'deadlineText':raw.get('period') or ('채용 시 마감' if rolling else '마감일 미공개'),
            'status':status,'evidence':reason or ('원문에서 주니어 모집 확인. '+(ai.get('eligibleRoles','') if ai else roles)),
            'lastVerifiedAt':utcnow(),'screeningMode':'astra' if ai else 'rules','screeningVersion':VERSION}
