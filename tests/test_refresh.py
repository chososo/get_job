import json, os, sys, tempfile, threading, unittest
from pathlib import Path
from functools import partial
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import ai_screen, local_server, refresh_jobs
from public_web import extract, validate_url
from screening import classify, experience_requirement

def raw(**changes):
    return {'id':'test-1','sourceId':'test','sourceUrl':'https://example.com/job','title':'퀀트 인턴',
            'company':'Test','country':'KR','body':'지원자격: 대학교 재학생\nPython 필수\n채용 시 마감','complete':True,**changes}

class EligibilityTests(unittest.TestCase):
    def test_experience_precedes_junior_title(self):
        for text in ['자격요건: 관련 업무 10년 이상','자격요건: 관련 분야 2년 이상','Minimum of 12 years of experience']:
            self.assertEqual(classify(raw(body=text))['status'],'excluded')
        self.assertFalse(experience_requirement('Python 활용 2년 이상 우대'))
        self.assertFalse(experience_requirement('0–2 years of experience'))
    def test_mixed_tracks_require_specific_evidence(self):
        j=classify(raw(title='퀀트 신입 및 경력',body='경력: 관련 업무 10년 이상'))
        self.assertEqual(j['status'],'review')
        j=classify(raw(title='퀀트 신입 및 경력',body='경력: 관련 업무 10년 이상',roleRequirements='신입: 대졸 예정',rolling=True))
        self.assertEqual(j['status'],'open')
        j=classify(raw(title='퀀트 경력직,채용전환형 인턴 동시 모집',body='[경력직 지원 자격]\n경력 2년 이상\n[채용전환형 인턴]\n담당 업무: 퀀트 연구\n지원 자격: 대학 졸업예정\n[근무]\n채용 시 마감'))
        self.assertEqual(j['status'],'open');self.assertNotIn('2년',j['eligibility'])
    def test_language_required_not_preferred(self):
        self.assertEqual(classify(raw(body='중국어 능력 필수\n채용 시 마감'))['status'],'excluded')
        self.assertEqual(classify(raw(body='지원자격: Python 활용\nJapanese preferred\n채용 시 마감'))['status'],'open')
        self.assertEqual(classify(raw(body='중국어 능통자 우대\n채용 시 마감'))['status'],'open')
    def test_unread_attachment_is_not_recommendation(self):
        self.assertEqual(classify(raw(complete=False))['status'],'review')
    def test_wanted_authoritative_close_overrides_rolling(self):
        data={'props':{'pageProps':{'initialData':{'position':'퀀트 신입','company':{'company_name':'Test'},'status':'close','hidden':True,'requirements':'Python','career':{'is_newbie':True}}}}}
        html='<h1>상시채용</h1><script id="__NEXT_DATA__" type="application/json">'+json.dumps(data)+'</script>'
        r=extract(html,'https://www.wanted.co.kr/wd/321015',{'id':'wanted'})
        self.assertEqual(classify(r)['status'],'closed')
    def test_linkedin_expiry_is_not_an_application_deadline(self):
        data={'@type':'JobPosting','title':'Quant Intern','validThrough':'2030-12-01T00:00:00Z','description':'Python required',
              'jobLocation':{'address':{'addressCountry':'SG'}}}
        html='<script type="application/ld+json">'+json.dumps(data)+'</script>'
        result=extract(html,'https://www.linkedin.com/jobs/view/example-123',{'id':'linkedin'})
        self.assertIsNone(result['deadlineDate']);self.assertEqual(result['country'],'SG')
    def test_ai_cannot_override_hard_disqualification(self):
        judgment={'category':'퀀트 리서치','level':'신입','decision':'include','reason':'신입','eligibility':'Python','requiredLocalLanguage':False,'closed':False}
        self.assertEqual(classify(raw(body='관련 업무 10년 이상'),judgment)['status'],'excluded')
    def test_ai_ungrounded_quote_downgrades(self):
        answer={'decision':'include','evidenceQuote':'invented','deadlineDate':'2030-12-01','deadlineQuote':'invented'}
        response={'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(answer)}]}]}
        with patch.object(ai_screen,'request',return_value=response):result=ai_screen.screen(raw(),{'api_key':'test'})
        self.assertEqual(result['decision'],'review');self.assertIsNone(result['deadlineDate'])
    def test_private_destination_rejected(self):
        with self.assertRaises(ValueError):validate_url('http://127.0.0.1')

class HelperTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.config=Path(self.tmp.name)/'.local/openai.json'
        self.patch=patch.object(ai_screen,'CONFIG',self.config);self.patch.start()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),partial(local_server.Handler,directory=self.tmp.name))
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
        self.headers={'Origin':'https://chososo.github.io','Content-Type':'application/json','X-Career-Token':local_server.TOKEN}
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.patch.stop();self.tmp.cleanup()
    def test_local_key_save_no_echo_delete_and_restart(self):
        key='sk-test-no-real-secret'
        r=requests.post(self.url+'/api/settings',headers=self.headers,json={'apiKey':key})
        self.assertEqual(r.status_code,200);self.assertNotIn(key,r.text)
        self.assertEqual(os.stat(self.config).st_mode&0o777,0o600)
        self.assertTrue(ai_screen.read_config()['api_key'])
        r=requests.get(self.url+'/api/status',headers={'Origin':'https://chososo.github.io'})
        self.assertTrue(r.json()['configured']);self.assertNotIn(key,r.text)
        requests.post(self.url+'/api/settings',headers=self.headers,json={'apiKey':''})
        self.assertFalse(ai_screen.read_config()['api_key'])
    def test_origin_and_csrf(self):
        for h in [{**self.headers,'Origin':'https://attacker.example'},{**self.headers,'X-Career-Token':''}]:
            r=requests.post(self.url+'/api/settings',headers=h,json={'apiKey':'sk-test'})
            self.assertEqual(r.status_code,403)
        self.assertFalse(self.config.exists())
        self.assertEqual(requests.options(self.url+'/api/settings',headers={'Origin':'https://chososo.github.io'}).headers['Access-Control-Allow-Origin'],'https://chososo.github.io')
    def test_refresh_starts_once_no_key_prompt(self):
        with patch.object(local_server,'STATE',{'state':'running','message':'Test'}),patch.object(local_server,'collection') as start:
            r=requests.post(self.url+'/api/refresh',headers=self.headers,json={})
            self.assertEqual(r.status_code,202);start.assert_not_called()

class PipelineTests(unittest.TestCase):
    def test_every_registered_source_attempted_and_failures_preserve(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'web/data').mkdir(parents=True)
            output=root/'web/data/jobs.json'
            old=classify(raw());output.write_text(json.dumps({'jobs':[old],'sources':[],'changes':[]}))
            sources=[{'id':x,'name':x,'url':'https://example.com','adapter':'public'} for x in ['naver','jasoseol','wanted']]
            (root/'sources.json').write_text(json.dumps(sources));visited=[]
            def discover(source,*args):visited.append(source['id']);raise ValueError('blocked')
            with patch.object(refresh_jobs,'ROOT',root),patch.object(refresh_jobs,'OUTPUT',output),patch.object(refresh_jobs,'discover',side_effect=discover),patch.object(ai_screen,'read_config',return_value={'api_key':''}):
                report=refresh_jobs.run()
            self.assertCountEqual(visited,['naver','jasoseol','wanted'])
            saved=json.loads(output.read_text());self.assertEqual(saved['jobs'][0]['lastVerifiedAt'],old['lastVerifiedAt'])
            self.assertEqual(report['attemptedSources'],3)
            self.assertTrue(all(s['status']=='error' and s['lastAttemptAt'] for s in saved['sources']))

if __name__=='__main__':unittest.main()
