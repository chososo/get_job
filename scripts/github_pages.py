"""Use the existing Git credential helper for the user's explicitly chosen repository.
No credential is printed, written to disk, or added to a URL.
"""
import argparse,json,subprocess,sys
import requests

REPO='chososo/get_job'
def session():
    r=subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\nusername=chososo\npath='+REPO+'.git\n\n',capture_output=True,text=True)
    if r.returncode:raise RuntimeError('GitHub credential helper에 인증이 없습니다. GitHub 로그인 후 다시 실행하세요.')
    fields=dict(line.split('=',1) for line in r.stdout.splitlines() if '=' in line)
    if not fields.get('password'):raise RuntimeError('GitHub 인증이 없습니다.')
    s=requests.Session();s.headers.update({'Authorization':'Bearer '+fields['password'],'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
    return s
def run(configure=False):
    s=session();base='https://api.github.com/repos/'+REPO
    r=s.get(base+'/pages',timeout=30)
    if configure:
        if r.status_code==404:r=s.post(base+'/pages',json={'build_type':'workflow'},timeout=30)
        elif r.ok and r.json().get('build_type')!='workflow':r=s.put(base+'/pages',json={'build_type':'workflow'},timeout=30)
    print('Pages API:',r.status_code)
    if r.ok:print(json.dumps({k:r.json().get(k) for k in ('html_url','status','build_type')},ensure_ascii=False))
    if not r.ok:raise RuntimeError('Pages 설정을 확인하세요. HTTP '+str(r.status_code))
    runs=s.get(base+'/actions/workflows/pages.yml/runs',params={'per_page':1},timeout=30)
    if runs.ok:
        for item in runs.json().get('workflow_runs',[]):print(json.dumps({k:item.get(k) for k in ('id','status','conclusion','html_url','head_sha')},ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--configure',action='store_true');args=p.parse_args()
    try:run(args.configure)
    except RuntimeError as e:print(str(e));sys.exit(1)
