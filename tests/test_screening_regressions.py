import sys, unittest, json, tempfile
from unittest.mock import patch
import importlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from screening import classify, experience_requirement, audit_existing, VERSION, requirements
from public_web import extract
from greeting_roles import split_roles

def raw(**kw):
    return dict(sourceId='test',sourceUrl='https://example.com/job',title='퀀트 인턴',company='Test',body='지원자격: 대졸\n채용 시 마감',complete=True,**kw) if not kw else {**raw(),**kw}

class RegressionTests(unittest.TestCase):
    def test_required_years_and_preferences(self):
        for body in ['경력 3~5년','경력 3년 이상 학력 무관','경력 3년 이상 / Python 우대','경력 3년 이상 Python 우대','금융자산 시뮬레이션 3년 이상 경험한 분','필수요건: 실무 경력 3년','경력 2년 이상, Python 우대','관련 업무 10년 이상','관련 분야 경력자 필수','필수요건: 관련 경력 3년 이상 및 Python 우대','[담당 업무]\n퀀트 운용\n3. 지원 자격\n관련 업무 3년 이상','[담당 업무]\n퀀트 운용\n지원자격 및 우대사항\n관련 업무 3년 이상']:
            self.assertEqual(classify(raw(body=body))['status'],'excluded',body)
        for body in ['0–2 years of experience','[우대 사항]\n경력 3년 이상','[조직 소개]\n10~20년 이상 경력의 컨설턴트\n[지원 자격]\n대졸','신입 또는 관련 경력 3년 이하 보유자']:
            self.assertFalse(experience_requirement(body),body)
    def test_preferred_experience_is_labelled_as_optional(self):
        text='[자격 요건]\n- 학력 무관\n[우대 사항]\n- 관련 업무 경력자\n2. 지원 방법\n채용 사이트 접수'
        self.assertEqual(classify(raw(body=text,rolling=True))['status'],'open')
        summary=requirements(text)
        self.assertIn('지원자격: 학력 무관',summary)
        self.assertIn('우대사항(필수 아님): 관련 업무 경력자',summary)
        self.assertNotIn('사이트 접수',summary)
    def test_career_and_senior_cannot_be_junior(self):
        for title in ['ETF 운용 경력직 채용','퀀트 경력사원 채용','Senior Quant Assistant']:
            self.assertEqual(classify(raw(title=title))['status'],'excluded')
    def test_mixed_role_must_be_relevant(self):
        j=classify(raw(title='퀀트 신입 및 경력',body='[인턴]\n마케팅\n[경력직]\n퀀트 연구 경력 3년 이상'))
        self.assertEqual(j['status'],'review')
    def test_ai_exclusion_is_terminal(self):
        ai=dict(category='퀀트 리서치',level='신입',decision='exclude',reason='불일치',requiredLocalLanguage=False,closed=False,eligibility='대졸')
        for title in ['Sales and Trading Intern','퀀트 신입 및 경력']:
            self.assertEqual(classify(raw(title=title),ai)['status'],'excluded')
        self.assertEqual(classify(raw(),{**ai,'level':'경력','decision':'include'})['status'],'excluded')
    def test_course_and_book_posts_are_not_recruitment(self):
        for title in ['투자자산운용사 한권완성 판매합니다.','CFA Lv3 Portfolio 인강공유 하실 분?']:
            old={**classify(raw()),'title':title}
            self.assertEqual(audit_existing(old)['status'],'excluded')

    def test_korean_country_label_does_not_drop_original_link(self):
        job=classify(raw(country='한국',closed=True))
        self.assertEqual(job['country'],'KR');self.assertEqual(job['status'],'closed')
    def test_old_records_preserved_but_not_recertified(self):
        old={**classify(raw()),'screeningVersion':'old'}
        audited=audit_existing(old)
        self.assertEqual(audited['status'],'review');self.assertEqual(audited['lastVerifiedAt'],old['lastVerifiedAt'])
        self.assertEqual(audit_existing({**old,'title':'ETF 경력직 채용'})['status'],'excluded')
        self.assertEqual(classify(raw(title='[마감] 퀀트 인턴'))['status'],'closed')
    def test_greeting_roles_are_separate_and_deadline_is_korean(self):
        detail='<h1>공통사항</h1><p>졸업예정자 가능</p><h1>채용 직무 안내</h1>'
        for name,req in [('평가모형컨설팅','대졸'),('금융리스크 관리','경력 3년 이상')]:
            detail+=f'<h2>{name}</h2><h3>[조직 소개]</h3><p>10~20년 이상 경력의 컨설턴트로 구성</p><h3>[지원 자격]</h3><p>{req}</p><h3>[우대 사항]</h3><p>경력 5년 이상</p>'
        data={'openingId':1,'title':'[NICE평가정보] 신입/경력 채용','detail':detail,'status':'OPEN','dueDate':'2030-09-21T14:59:59Z'}
        html='<h1>'+data['title']+'</h1><p>평가모형컨설팅 NICE 경력 무관</p><p>금융리스크 관리 NICE 경력 3년 이상</p><h2>공통사항</h2><script id="__NEXT_DATA__">'+json.dumps(data)+'</script>'
        jobs=[classify(r) for r in split_roles(extract(html,'https://nice.career.greetinghr.com/ko/o/1',{'id':'niceinfo'}))]
        self.assertEqual(len(jobs),2);self.assertNotEqual(jobs[0]['id'],jobs[1]['id'])
        self.assertEqual([j['status'] for j in jobs],['open','excluded'])
        self.assertEqual(jobs[0]['deadlineAt'],'2030-09-21T23:59:59+09:00')
        self.assertNotIn('20년',jobs[0]['eligibility'])

class PersistenceTests(unittest.TestCase):
    def test_shared_url_roles_and_watched_closed_records_survive(self):
        import refresh_jobs, ai_screen
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'web/data').mkdir(parents=True)
            output=root/'web/data/jobs.json'
            output.write_text(json.dumps({'jobs':[],'sources':[],'changes':[]}))
            source={'id':'test','name':'test','url':'https://example.com/job'}
            (root/'sources.json').write_text(json.dumps([source]))
            (root/'public-watch.json').write_text(json.dumps([{'sourceId':'test','sourceUrl':source['url']}]))
            rows=[raw(id='role-a',roleKey='a',title='퀀트 인턴'),raw(id='role-b',roleKey='b',title='ETF 신입',closed=True)]
            info={'lists':1,'details':1,'failed':0,'truncated':False,'reason':'fixture'}
            with patch.object(refresh_jobs,'ROOT',root),patch.object(refresh_jobs,'OUTPUT',output),patch.object(refresh_jobs,'discover',return_value=(rows,info)),patch.object(ai_screen,'read_config',return_value={'api_key':''}):
                refresh_jobs.run();first=json.loads(output.read_text())['jobs']
                refresh_jobs.run();second=json.loads(output.read_text())['jobs']
            self.assertEqual({j['id'] for j in first},{'role-a','role-b'})
            self.assertEqual({j['id'] for j in second},{'role-a','role-b'})
            self.assertEqual({j['status'] for j in second},{'open','closed'})

class FreshWorkerTests(unittest.TestCase):
    def test_refresh_uses_changed_code_without_helper_restart(self):
        import local_server
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'scripts').mkdir();script=root/'scripts/refresh_jobs.py'
            with patch.object(local_server,'ROOT',root),patch.object(local_server,'STATE',{'state':'running'}):
                for revision in ['first','second']:
                    script.write_text('print('+repr(json.dumps({'state':'complete','revision':revision}))+')')
                    local_server.collection({})
                    self.assertEqual(local_server.STATE.get('revision'),revision)
                script.write_text('raise SystemExit(1)')
                local_server.collection({})
                self.assertEqual(local_server.STATE['state'],'error')

if __name__=='__main__':unittest.main()
