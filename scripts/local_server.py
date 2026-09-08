"""Loopback-only static app + opt-in OpenAI relay. No prompt/response logging."""
import argparse
import getpass
import json
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote
import urllib.request
import urllib.error

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'.local/openai.json'

def configure():
    key=getpass.getpass('OpenAI API 키 (화면에 표시되지 않습니다): ').strip()
    if not key: raise SystemExit('키를 입력하지 않아 취소했습니다.')
    model=input('모델 ID [gpt-5.4-mini]: ').strip() or 'gpt-5.4-mini'
    CONFIG.parent.mkdir(exist_ok=True,mode=0o700)
    fd=os.open(CONFIG,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    os.fchmod(fd,0o600)
    with os.fdopen(fd,'w') as f:json.dump({'api_key':key,'model':model},f)
    print('로컬 설정에만 저장했습니다. GitHub에는 업로드하지 않습니다.')

def read_config():
    cfg=json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    return {'api_key':os.environ.get('OPENAI_API_KEY',cfg.get('api_key','')),'model':os.environ.get('OPENAI_MODEL',cfg.get('model','gpt-5.4-mini'))}

def response_text(data):
    if data.get('status') not in ('completed',None):raise ValueError('GPT 응답이 완성되지 않았습니다. 분량을 줄여 다시 시도하세요.')
    result='\n'.join(part['text'] for item in data.get('output',[]) if item.get('type')=='message' for part in item.get('content',[]) if part.get('type')=='output_text')
    if not result:raise ValueError('GPT가 텍스트를 반환하지 않았습니다. 입력을 확인하세요.')
    return result

class Handler(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass
    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('Cache-Control','no-store');super().end_headers()
    def allowed_host(self):
        return self.headers.get('Host','') in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
    def reply(self,status,data):
        body=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if not self.allowed_host():return self.reply(403,{'error':'허용되지 않은 호스트입니다.'})
        path=unquote(urlsplit(self.path).path)
        if any(segment.startswith('.') for segment in path.split('/') if segment) or '..' in path.split('/'):return self.reply(404,{'error':'Not found'})
        target=(ROOT/'web'/path.lstrip('/')).resolve()
        if not target.is_relative_to((ROOT/'web').resolve()):return self.reply(404,{'error':'Not found'})
        if path=='/api/status':return self.reply(200,{'configured':bool(read_config()['api_key'])})
        return super().do_GET()
    def list_directory(self,path):return self.reply(404,{'error':'Not found'})
    def do_POST(self):
        if not self.allowed_host():return self.reply(403,{'error':'허용되지 않은 호스트입니다.'})
        origins={f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}
        if self.headers.get('Origin') not in origins:return self.reply(403,{'error':'로컬 웹앱에서만 실행할 수 있습니다.'})
        if self.path!='/api/generate':return self.reply(404,{'error':'Not found'})
        if self.headers.get('Content-Type')!='application/json':return self.reply(415,{'error':'JSON만 허용합니다.'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=100000:return self.reply(413,{'error':'입력 분량을 줄여주세요.'})
            payload=json.loads(self.rfile.read(size));prompt=payload.get('prompt')
            if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>40000:return self.reply(400,{'error':'작성 요청을 확인하세요.'})
            cfg=read_config()
            if not cfg['api_key']:return self.reply(503,{'error':'로컬 API 키가 없습니다. README의 GPT 연결 방법으로 설정하세요.'})
            body=json.dumps({'model':cfg['model'],'input':prompt,'store':False,'max_output_tokens':6000}).encode()
            req=urllib.request.Request('https://api.openai.com/v1/responses',data=body,headers={'Authorization':'Bearer '+cfg['api_key'],'Content-Type':'application/json'},method='POST')
            with urllib.request.urlopen(req,timeout=110) as r:data=json.load(r)
            return self.reply(200,{'text':response_text(data)})
        except urllib.error.HTTPError as exc:
            return self.reply(502,{'error':f'OpenAI API 오류 ({exc.code}). 키·결제·모델 사용 권한과 입력 분량을 확인하세요.'})
        except (urllib.error.URLError,TimeoutError):return self.reply(502,{'error':'OpenAI 연결이 지연되거나 실패했습니다. 기존 본문은 유지됩니다.'})
        except (ValueError,KeyError,json.JSONDecodeError) as exc:return self.reply(400,{'error':'입력 또는 응답을 처리하지 못했습니다. 본문은 유지됩니다.'})
        except BrokenPipeError:pass

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--configure',action='store_true');p.add_argument('--port',type=int,default=8765);args=p.parse_args()
    if args.configure:configure()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),partial(Handler,directory=str(ROOT/'web')))
    print(f'로컬 Career Desk: http://127.0.0.1:{args.port}/',flush=True)
    print('GPT API: '+('설정됨' if read_config()['api_key'] else '미설정 · 요청문 복사 기능은 사용 가능'),flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:server.server_close()
