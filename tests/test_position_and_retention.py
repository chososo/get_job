import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from screening import classify,experience_requirement,VERSION,audit_existing
from refresh_jobs import revalidate_cached
from collect import digest
from samsung_finance import parse_posting

def raw(**kw):return {'sourceId':'test','sourceUrl':'https://example.com/1','company':'Test','title':'퀀트 신입','body':'지원자격: 대졸','complete':True,'rolling':True,**kw}

class PositionTests(unittest.TestCase):
    def test_body_position_and_years_override_title_and_ai(self):
        body='□ 모집직위 : 부장 이상\n□ 고용형태 : 계약직\n□ 담당업무 : 채권 프랍\n□ 자격요건 : 관련 업무 10년 이상\n인턴·아르바이트 경력 기재 제외'
        ai={'category':'자산운용·자산배분','decision':'include','level':'신입','reason':'신입','eligibility':'대졸','requiredLocalLanguage':False,'closed':False}
        for judgment in [None,ai]:
            j=classify(raw(body=body),judgment)
            self.assertEqual(j['status'],'excluded');self.assertEqual(j['recruitmentPosition'],'부장 이상');self.assertIn('10년',j['requiredExperience'])
        self.assertEqual(classify(raw(body='모집직위 : 과장\n학력 무관'))['status'],'excluded')
    def test_inline_qualification_after_tasks(self):
        self.assertTrue(experience_requirement('[담당업무]\n퀀트 연구\n□ 자격요건 : 관련 업무 10년 이상'))
    def test_new_grad_training_is_not_prior_experience(self):
        j=classify(raw(title='3급 신입사원 퀀트 채용',body='지원자격: 대졸\n입사자는 입사 후 1년 간 바이오 공정 경험을 통해 비즈니스 이해도를 높입니다.'))
        self.assertEqual(j['status'],'open');self.assertEqual(j['recruitmentPosition'],'3급 신입사원')
        self.assertFalse(experience_requirement('회사 소개\n입사 후 1년간 직무교육 예정'))
        self.assertTrue(experience_requirement('관련 업무 1년 이상 경력 필수'))
    def test_temporary_failure_does_not_remove_verified_recruitment(self):
        job=classify(raw());self.assertEqual(audit_existing(job)['status'],'open')
        self.assertEqual(audit_existing(job)['lastVerifiedAt'],job['lastVerifiedAt'])
    def test_rule_change_rechecks_cached_facts_without_fresh_timestamp(self):
        with tempfile.TemporaryDirectory() as temp:
            cache=Path(temp);r=raw();job={**classify(r),'screeningVersion':'old','status':'excluded'}
            (cache/('raw-'+digest([r['sourceUrl'],''])+'.json')).write_text(json.dumps(r))
            j=revalidate_cached(job,cache)
            self.assertEqual(j['status'],'open');self.assertEqual(j['lastVerifiedAt'],job['lastVerifiedAt']);self.assertEqual(j['screeningVersion'],VERSION)
    def test_employer_roles_are_individually_screened(self):
        head={'seq':1,'title':'2026년 하반기 3급 신입사원 채용','cmpNameKr':'삼성증권','qlfctKr':'2027년 2월 졸업 예정자','startdate':'202609081000','enddate':'202609151700','isOpened':1}
        roles=[{'titleKr':'자산운용','taskKr':'운용 업무','qlfctKr':'전공 무관'}, {'titleKr':'퀀트 리서치','taskKr':'리서치','qlfctKr':'관련 업무 10년 이상'}, {'titleKr':'마케팅','qlfctKr':'신입'}]
        rows=parse_posting({'success':True,'data':{'result':head,'items':roles}},{'id':'samsung-finance'})
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['roles'],'자산운용')
        self.assertEqual(classify(rows[0])['status'],'open')

class EmployerPriorityTests(unittest.TestCase):
    def test_employer_wins_for_existing_stable_id(self):
        from unittest.mock import patch
        import refresh_jobs,ai_screen
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'web/data').mkdir(parents=True);output=root/'web/data/jobs.json'
            output.write_text(json.dumps({'jobs':[],'sources':[],'changes':[]}))
            sources=[{'id':'official','name':'official','url':'https://example.com/official','authoritative':True},{'id':'aggregator','name':'aggregator','url':'https://example.com/summary'}]
            (root/'sources.json').write_text(json.dumps(sources))
            def discover(source,*args):
                row=raw(id='stable',sourceId=source['id'],sourceUrl=source['url'])
                return [row],{'lists':1,'details':1,'failed':0,'truncated':False,'reason':'fixture'}
            with patch.object(refresh_jobs,'ROOT',root),patch.object(refresh_jobs,'OUTPUT',output),patch.object(refresh_jobs,'discover',side_effect=discover),patch.object(ai_screen,'read_config',return_value={'api_key':''}):refresh_jobs.run()
            jobs=json.loads(output.read_text())['jobs']
            self.assertEqual(len(jobs),1);self.assertEqual(jobs[0]['sourceId'],'official')

if __name__=='__main__':unittest.main()
