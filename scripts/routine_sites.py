"""Read only the explicitly exported recruitment-site list, never the private vault.

The newest valid export is a complete snapshot; deletions and pauses propagate.
No URL is fetched here. Official-site resolution belongs to the scheduled agent.
"""
import argparse, json, os, re
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl

ROOT=Path(__file__).resolve().parents[1]
FIELDS={'format','version','sources'}
def validate(data):
    if not isinstance(data,dict) or set(data)!=FIELDS or data.get('format')!='career-routine-sites' or data.get('version')!=1:
        raise ValueError('지원하지 않는 루틴 사이트 파일입니다.')
    items=data['sources']
    if not isinstance(items,list) or len(items)>300:raise ValueError('사이트 목록은 300개 이하여야 합니다.')
    for s in items:
        if not isinstance(s,dict) or set(s)!={'name','url','enabled'}:raise ValueError('사이트 파일에는 기업명·주소·활성 여부만 허용합니다.')
        if not isinstance(s['name'],str) or not 0<len(s['name'].strip())<=120 or not isinstance(s['enabled'],bool):raise ValueError('잘못된 기업명 또는 활성 여부입니다.')
        if not isinstance(s['url'],str) or len(s['url'])>2000:raise ValueError('잘못된 주소입니다.')
        if s['url']:
            u=urlsplit(s['url']);host=(u.hostname or '').lower()
            if u.scheme not in ('http','https') or u.username or u.password or '.' not in host or host.endswith(('.local','.localhost')) or re.fullmatch(r'[\d.]+',host) or ':' in host:
                raise ValueError('공개 채용 주소만 허용합니다.')
            if any(re.search(r'token|password|secret|session|authorization|api.?key',k,re.I) for k,_ in parse_qsl(u.query)):
                raise ValueError('로그인 정보가 있는 주소는 허용하지 않습니다.')
    return data

def read(path):
    if path.is_symlink() or path.stat().st_size>1000000:raise ValueError('허용하지 않는 파일입니다.')
    return validate(json.loads(path.read_text()))

def sync(downloads, destination):
    candidates=[p for p in downloads.glob('career-routine-sites*.json') if re.fullmatch(r'career-routine-sites(?:-\d+)?(?: \(\d+\))?\.json',p.name) and not p.is_symlink()]
    if not candidates:return False
    newest=max(candidates,key=lambda p:p.stat().st_mtime_ns)
    if destination.exists() and newest.stat().st_mtime_ns<destination.stat().st_mtime_ns:
        # Removing a newer download must not resurrect a previously deleted site.
        read(destination)
        return False
    # Fail visibly on a malformed latest export; don't silently restore an older list.
    data=read(newest)
    if destination.exists() and read(destination)==data:return False
    if destination.is_symlink():raise ValueError('로컬 목록이 심볼릭 링크입니다.')
    temporary=destination.with_suffix('.tmp')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as out:json.dump(data,out,ensure_ascii=False,indent=2)
    os.replace(temporary,destination)
    return True

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--downloads',type=Path,default=Path.home()/'Downloads');args=parser.parse_args()
    destination=ROOT/'.routine-sites.json'
    changed=sync(args.downloads,destination)
    data=read(destination) if destination.exists() else {'sources':[]}
    print(json.dumps({'changed':changed,'sources':[s for s in data['sources'] if s['enabled']]},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
