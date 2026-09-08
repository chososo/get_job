import sys
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from collect import parse_period, junior_level, make_job, merge, language_status, category_for, greenhouse
from local_server import response_text

class CollectorTests(unittest.TestCase):
    def test_period(self):
        self.assertEqual(parse_period('20260908~20260930'),('2026-09-08','2026-09-30'))
        self.assertEqual(parse_period('2026.09.08 - 2026.09.30'),('2026-09-08','2026-09-30'))
        self.assertEqual(parse_period('채용시까지'),(None,None))
        self.assertEqual(parse_period('20261340'),(None,None))
    def test_level(self):
        self.assertEqual(junior_level('퀀트 인턴 채용','선임 연구자의 멘토링'), '인턴')
        self.assertEqual(junior_level('Quantitative Researcher','Prior internship experience preferred'), '확인 필요')
        self.assertIsNone(junior_level('AI Research Developer','Research Developer, 과~차장급'))
        self.assertIsNone(junior_level('리스크 경력직 채용','3년 이상 경력'))
        self.assertEqual(junior_level('ETF 운용 신입 및 경력 채용',''), '신입')
    def test_categories(self):
        self.assertEqual(category_for('파생상품평가 신입'), '파생상품평가')
        self.assertEqual(category_for('ETF LP 인턴'), 'ETF·인덱스')
        self.assertEqual(category_for('Model validation graduate'), '금융리스크')
    def test_language(self):
        self.assertEqual(language_status('Fluent in Japanese and English','JP'),'Japanese 필수')
        self.assertIn('우대',language_status('Japanese preferred, fluent in English','JP'))
    def test_unknown_deadline_not_open(self):
        j=make_job({'id':'test','detailUrl':'https://example.com/job'},'1','퀀트 인턴','Acme','마감 안내 없음','KR')
        self.assertEqual(j['status'],'review');self.assertIsNone(j['deadlineDate'])
    def test_merge_ignores_verification_only_and_preserves_failed_source(self):
        j=make_job({'id':'test','detailUrl':'https://example.com/job'},'1','퀀트 인턴','Acme','','KR')
        a,c=merge({},[j],'a');self.assertEqual(len(c),1)
        j['lastVerifiedAt']='later';b,d=merge({'jobs':a,'changes':c},[j],'b');self.assertEqual(len(d),1)
        b,d=merge({'jobs':b,'changes':d},[],'c');self.assertEqual(len(b),1)
        j['title']='퀀트 인턴 변경';b,d=merge({'jobs':b,'changes':d},[j],'d');self.assertEqual(d[-1]['kind'],'updated')
    def test_deadline_expiration_is_explicit(self):
        j=make_job({'id':'test','detailUrl':'https://example.com/job'},'1','퀀트 인턴','Acme','','KR')
        j.update(status='open',deadlineDate=(datetime.now()-timedelta(days=2)).date().isoformat())
        b,c=merge({'jobs':[j]},[],'now');self.assertEqual(b[0]['status'],'closed');self.assertEqual(c[0]['kind'],'closed')
    def test_openai_response_handling(self):
        self.assertEqual(response_text({'status':'completed','output':[{'type':'reasoning'},{'type':'message','content':[{'type':'output_text','text':'Draft'}]}]}),'Draft')
        with self.assertRaises(ValueError):response_text({'status':'incomplete','output':[]})
    def test_api_metadata_null_and_internship_type(self):
        class Response:
            def json(self):
                return {'jobs':[
                  {'id':1,'location':{'name':'London'},'title':'Quantitative Researcher','content':'Research models.','metadata':None,'absolute_url':'https://example.com/1'},
                  {'id':2,'location':{'name':'Hong Kong'},'title':'Quantitative Trader','content':'Fluent in English','metadata':[{'name':'Employment Type','value':'Summer Internship'}],'absolute_url':'https://example.com/2'}]}
        class Client:
            def get(self,*args,**kwargs):return Response()
        jobs,_,_=greenhouse(Client(),{'id':'test','board':'test','company':'Test'},1)
        self.assertEqual(len(jobs),2);self.assertEqual(jobs[1]['level'],'인턴')
    def test_irrelevant_and_archival_jobs_do_not_enter_candidates(self):
        args={'source':{'id':'test','detailUrl':'https://example.com/1'},'source_id':'1','company':'Acme','country':'KR'}
        self.assertIsNone(make_job(**args,title='준법감시인 겸 위험관리책임자',body=''))
        self.assertIsNone(make_job(**args,title='2014 자산운용 신입',body='',posted='2014-01-01'))
        self.assertIsNone(category_for('Infrastructure Automation Specialist','We are a quantitative trading company.'))

if __name__=='__main__':unittest.main()
