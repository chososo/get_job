import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build
from import_jobs import validate

class PublicationTests(unittest.TestCase):
    def test_allowlist_excludes_private_files_even_inside_web(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for filename in build.PUBLIC_FILES:
                p=root/'web'/filename;p.parent.mkdir(parents=True,exist_ok=True)
                p.write_text(json.dumps({'jobs':[]}) if filename=='data/jobs.json' else 'public test fixture')
            (root/'web/private.vault.json').write_text('PRIVATE TEST VALUE')
            (root/'.local').mkdir();(root/'.local/openai.json').write_text('SECRET TEST VALUE')
            with patch.object(build,'ROOT',root):build.build()
            files={str(p.relative_to(root/'dist')) for p in (root/'dist').rglob('*') if p.is_file()}
            self.assertEqual(files,set(build.PUBLIC_FILES)|{'.nojekyll'})
            self.assertFalse(any('PRIVATE TEST' in p.read_text() or 'SECRET TEST' in p.read_text() for p in (root/'dist').rglob('*') if p.is_file()))
    def test_public_import_rejects_private_payload_and_executable_url(self):
        job={'id':'test-1','sourceId':'test','sourceUrl':'https://example.com/1','title':'Quant intern','company':'Test','country':'KR','category':'퀀트 리서치','status':'review','lastVerifiedAt':'2026-09-08T00:00:00Z','deadlineKind':'unknown'}
        validate(job)
        with self.assertRaises(ValueError):validate({**job,'experiences':[{'private':True}]})
        with self.assertRaises(ValueError):validate({**job,'sourceUrl':'javascript:alert(1)'})
        with self.assertRaises(ValueError):validate({**job,'status':'open'})

if __name__=='__main__':unittest.main()
