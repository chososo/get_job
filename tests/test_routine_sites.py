import json,sys,tempfile,unittest,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from routine_sites import validate,sync,read

def payload(sources):return {'format':'career-routine-sites','version':1,'sources':sources}
class RoutineSitesTests(unittest.TestCase):
    def test_latest_snapshot_pauses_deletes_and_does_not_read_other_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);dest=root/'.routine-sites.json'
            old=root/'career-routine-sites-1.json';old.write_text(json.dumps(payload([{'name':'A','url':'','enabled':True}])))
            os.utime(old,(1,1));(root/'private.vault.json').write_text('not json')
            new=root/'career-routine-sites-2.json';new.write_text(json.dumps(payload([{'name':'B','url':'https://example.com','enabled':False}])))
            self.assertTrue(sync(root,dest));self.assertEqual(read(dest)['sources'][0]['name'],'B');self.assertFalse(sync(root,dest))
            new.write_text(json.dumps(payload([])));sync(root,dest);self.assertEqual(read(dest)['sources'],[])
            new.write_text('invalid');before=dest.read_text()
            with self.assertRaises(ValueError):sync(root,dest)
            self.assertEqual(dest.read_text(),before)
    def test_private_fields_and_unsafe_links_rejected(self):
        item={'name':'Test','url':'https://example.com','enabled':True}
        validate(payload([item]))
        with self.assertRaises(ValueError):validate(payload([{**item,'CV':'private'}]))
        for url in ['javascript:alert(1)','http://localhost','http://127.0.0.1','https://test.local','https://user:pass@example.com','https://example.com?token=secret']:
            with self.assertRaises(ValueError):validate(payload([{**item,'url':url}]))
if __name__=='__main__':unittest.main()
