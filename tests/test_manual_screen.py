import json, sys, tempfile, unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import manual_screen
import refresh_jobs, ai_screen
from screening import VERSION


class ManualScreenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name)
        self.raw = dict(id='test-1', sourceId='test', sourceUrl='https://example.org/job',
                        title='퀀트 인턴', body='대학교 재학생, Python 필수', complete=True,
                        country='KR', collectedAt='2030-09-01T01:00:00+00:00')
        self.job = dict(id='test-1', sourceId='test', sourceUrl=self.raw['sourceUrl'],
                        status='open', screeningMode='manual', screeningVersion=VERSION,
                        lastVerifiedAt='2030-09-01T02:00:00+00:00', deadlineDate='2030-09-02',
                        deadlineTimezone='Asia/Seoul', evidence='원문 요건 확인')
        (self.cache / ('raw-' + manual_screen.key(self.raw) + '.json')).write_text(json.dumps(self.raw))

    def tearDown(self):
        self.tmp.cleanup()

    def test_identical_original_survives_and_date_only_expires_next_day(self):
        self.assertTrue(manual_screen.remember(self.job, self.cache))
        now = datetime(2030, 9, 2, 14, 59, tzinfo=timezone.utc)
        self.assertEqual(manual_screen.reuse(self.raw, self.cache, now)['status'], 'open')
        self.assertEqual(manual_screen.reuse(self.raw, self.cache, now.replace(hour=15))['status'], 'closed')

    def test_changed_or_incomplete_original_is_rejudged(self):
        manual_screen.remember(self.job, self.cache)
        for changes in [dict(body='관련 경력 10년 필수'), dict(complete=False), dict(country='JP'),
                        dict(deadlineDate='2030-09-01'), dict(roleKey='different'), dict(closed=True),
                        dict(id='another'), dict(sourceUrl='https://example.org/other')]:
            self.assertIsNone(manual_screen.reuse({**self.raw, **changes}, self.cache))

    def test_old_manual_facts_cannot_bind_to_newer_original(self):
        self.assertFalse(manual_screen.remember({**self.job, 'lastVerifiedAt':'2030-08-31T01:00:00Z'}, self.cache))
        self.assertFalse(manual_screen.remember({**self.job, 'screeningVersion':'old'}, self.cache))

    def test_exact_deadline_and_bookkeeping(self):
        manual_screen.remember({**self.job, 'deadlineAt':'2030-09-02T17:00:00+09:00'}, self.cache)
        now = datetime(2030, 9, 2, 8, 0, tzinfo=timezone.utc)
        self.assertEqual(manual_screen.reuse({**self.raw, 'collectedAt':'later', 'label':'D-1', 'greetingHeader':'D-1'}, self.cache, now)['status'], 'closed')

    def test_pipeline_skips_ai_only_for_identical_verified_original(self):
        root = self.cache
        cache = root / '.collection-cache'; cache.mkdir()
        (root / 'web/data').mkdir(parents=True)
        output = root / 'web/data/jobs.json'
        source = dict(id='test', name='Test', url='https://example.org', adapter='public')
        job = {**self.job, 'title':'퀀트 인턴', 'company':'Test', 'country':'KR', 'category':'퀀트 리서치', 'level':'인턴', 'deadlineKind':'date'}
        output.write_text(json.dumps(dict(jobs=[job], sources=[], changes=[])))
        (root / 'sources.json').write_text(json.dumps([source]))
        (cache / ('raw-' + manual_screen.key(self.raw) + '.json')).write_text(json.dumps(self.raw))
        manual_screen.remember(job, cache)
        info = dict(lists=1, details=1, failed=0, truncated=False, reason='test')
        with patch.object(refresh_jobs, 'ROOT', root), patch.object(refresh_jobs, 'OUTPUT', output), \
             patch.object(refresh_jobs, 'discover', return_value=([self.raw], info)), \
             patch.object(refresh_jobs, 'prepare_raw', side_effect=lambda raw,*args:raw), \
             patch.object(ai_screen, 'read_config', return_value={'api_key':'test'}), \
             patch.object(ai_screen, 'screen', side_effect=ValueError('API unavailable')) as screen:
            report = refresh_jobs.run()
            screen.assert_not_called()
        saved = json.loads(output.read_text())['jobs'][0]
        self.assertEqual(saved['status'], 'open')
        self.assertEqual(saved['evidence'], job['evidence'])
        self.assertEqual(report['aiErrors'], 0)


if __name__ == '__main__':
    unittest.main()
