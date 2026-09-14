import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from discovery import discover, links_from
from public_web import extract
from screening import classify, experience_requirement
from collect import canonical


class OfficialRoutesTests(unittest.TestCase):
    def test_global_listing_requires_an_explicit_supported_location(self):
        source={'id':'global','requireLocation':True}
        html='<h1>Quant Research Intern</h1><p>Bachelors degree and Python</p>'
        raw=extract(html,'https://example.com/jobs/intern',source)
        self.assertEqual(raw['country'],'')
        self.assertIsNone(classify(raw))
        html+='''<script type="application/ld+json">{"@type":"JobPosting","title":"Quant Research Intern", "jobLocation":{"address":{"addressCountry":"United Kingdom"}}}</script>'''
        self.assertEqual(extract(html,'https://example.com/jobs/intern',source)['country'],'GB')
        job=classify({'sourceId':'global','sourceUrl':'https://example.com/jobs/intern','company':'Example',
                      'country':'HK','title':'Quant Research Intern','body':'Bachelor degree. Fluent English.',
                      'complete':True,'accepting':True})
        self.assertEqual(job['status'],'review')
        self.assertIn('스폰서십',job['evidence'])

    def test_split_experience_label_and_unrelated_essays(self):
        for years in (3,5,10):
            body=f'지원자격\n경력\n경력\n({years}년이상)\n학력\n학력무관'
            self.assertIn(str(years)+'년',experience_requirement(body))
            raw={'sourceId':'test','sourceUrl':'https://example.com/jobs/1','company':'회사',
                 'country':'KR','title':'금융리스크 분석 신입','body':body,'period':'2030-09-30'}
            self.assertEqual(classify(raw)['status'],'excluded')
        for body in ('근무기간\n10년','경력\n(3년 이상 우대)','경력\n신입·경력 무관'):
            self.assertEqual(experience_requirement(body),'')
        raw=extract('<h1>리스크 분석</h1><p>지원자격</p><p>경력</p><p>(10년이상)</p>'
                    '<p>이 기업의 취업 전략</p><p>신입 합격자소서: 예전 채용 자료</p>',
                    'https://www.jobkorea.co.kr/Recruit/GI_Read/49814985',{'id':'jobkorea'})
        self.assertNotIn('합격자소서',raw['body'])
        self.assertIn('10년',experience_requirement(raw['body']))

    def test_jobkorea_tracking_does_not_create_another_posting(self):
        first='https://www.jobkorea.co.kr/Recruit/GI_Read/49937690?listno=3&stext=quant'
        second='https://www.jobkorea.co.kr/Recruit/GI_Read/49937690?listno=4&stext=intern'
        self.assertEqual(canonical(first),canonical(second))
        self.assertNotEqual(canonical(first),canonical(first.replace('49937690','49937691')))
        listing='https://www.jobkorea.co.kr/Search/?stext=quant'
        self.assertEqual(canonical(listing),listing)

    def test_irrelevant_finance_words_do_not_override_scope(self):
        base={'sourceId':'test','sourceUrl':'https://example.com/jobs/1','company':'회사',
              'country':'KR','complete':True,'period':'2030-09-30',
              'body':'자격요건\n학사 이상, 경력 무관'}
        for title,body in [
            ('법인 경영 리스크 관리 컨설턴트','고용형태\n프리랜서\n경력무관'),
            ('Risk Management Head',base['body']),
            ('자산운용사 CRO',base['body']),
            ('자산운용 지원자에게 추천 3권',base['body']),
            ('자산운용 사무보조 채용',base['body']),
            ('운용지원실 펀드회계팀 인턴 채용',base['body']),
            ('리스크관리 및 가맹점 응대 담당(팀장급)',base['body']),
            ('투자운용본부 신입 인턴','[담당업무]\n국내 부동산 펀드 운용/매각\n[지원자격]\n학사 이상'),
        ]:
            with self.subTest(title=title):
                self.assertEqual(classify({**base,'title':title,'body':body})['status'],'excluded')
        mixed=classify({**base,'title':'대졸 신입 · 재무회계 / RA','body':'화장품 인허가 및 재무회계. 학사 이상', 'section':'corporate'})
        self.assertEqual(mixed['category'],'기업 재무·전략투자')
        risk=classify({**base,'title':'대체투자 리스크관리 인턴','body':'부동산, 인프라, PE 투자 위험 분석\n자격요건\n학사 이상'})
        self.assertEqual(risk['status'],'open')
        mixed=classify({**base,'title':'9월 수시채용 (신입/경력)','roles':'리스크관리 (경력)',
                        'body':'모집분야: 통합구매 (신입) / 리스크관리 (경력) / 영업 (신입)'})
        self.assertEqual(mixed['status'],'excluded')

    def test_official_job_links_are_discovered(self):
        for url,href,label in [
            ('https://qraft.careers.team/job-descriptions', '/job-descriptions/AV8bAdrEvR', 'Quant Developer'),
            ('https://corp.fnguide.com/Career/CareerInfo', '/Career/CareerInfoDetail?no=116', '인덱스개발팀 신입 채용'),
        ]:
            links,_=links_from(f'<a href="{href}">{label}</a>',url,{'id':'test'})
            self.assertEqual(len(links),1)

    def test_fnguide_current_listing_revalidates_existing_job(self):
        base='https://corp.fnguide.com/Career/CareerInfo'
        detail=base+'Detail?no=116'
        html='''<div id="container"><h4>[인덱스개발팀] 신입/경력 채용</h4>
          <div class="career--left"><div class="role1"><p>담당업무</p><p>인덱스 개발 및 유지보수 관리</p>
          <p>자격요건</p><p>학사 이상, 경력 무관, 금융상품 및 자본시장 지식, SQL과 Python 활용 능력</p>
          <p>금융 관련 전공 또는 개발 관련 전공, 다양한 금융 데이터를 분석하고 인덱스 연구 및 유지보수 업무를 수행할 수 있는 분</p>
          <p>문서 작성 및 의사소통 능력을 바탕으로 지수 구성과 검증 결과를 팀원에게 설명할 수 있는 분</p>
          <p>우대사항</p><p>관련 경력 3년 우대</p></div></div>
          <a href="/Career/ConfirmStep?no=116">지원하기</a></div>'''
        class Client:
            def get(self,url):
                content=f'<a href="{detail}">인덱스개발팀 신입 채용 ~2030년 09월 30일</a>' if url==base else html
                return type('Response',(),{'text':content})()
        class Renderer:
            def render(self,url):raise AssertionError('Static fixture needs no renderer')
        rows,info=discover({'id':'fnguide','name':'FnGuide','url':base},Client(),Renderer(),watch=[{'id':'saved-id','sourceUrl':detail}])
        job=classify(rows[0])
        self.assertEqual(job['id'],'saved-id')
        self.assertEqual(job['company'],'에프앤가이드')
        self.assertIn('금융 관련 전공',job['eligibility'])
        self.assertEqual(job['status'],'open')
        self.assertEqual(job['deadlineDate'],'2030-09-30')
        self.assertIsNone(job['deadlineAt'])
        self.assertEqual(info['details'],1)
        job=classify(extract(html.replace('경력 무관','관련 업무 10년 이상'),detail,{'id':'fnguide'}))
        self.assertEqual(job['status'],'excluded')


if __name__=='__main__':unittest.main()
