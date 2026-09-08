"""Loopback helper for public collection and explicitly approved writing requests."""
import argparse, getpass, json, os, secrets, threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote
import ai_screen
from ai_screen import response_text, read_config
import routine_sites
from refresh_jobs import atomic

ROOT=Path(__file__).resolve().parents[1]
TOKEN=secrets.token_urlsafe(32)
STATE={'state':'idle','message':'대기 중'}
LOCK=threading.Lock()

def configure():
    ai_screen.save_key(getpass.getpass('OpenAI API 키: ').strip())
    print('이 Mac에만 저장했습니다.')

def collection(payload):
    global STATE
    from refresh_jobs import run
    def update(value):
        global STATE
        with LOCK:STATE=value
    try:run(progress=update,publish_result=True)
    except Exception as exc:update({'state':'error','message':str(exc) if isinstance(exc,ValueError) else '수집 실행 오류. 기존 공고를 유지합니다.'})

class Handler(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass
    def origins(self):return {'https://chososo.github.io',f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}
    def allowed_host(self):return self.headers.get('Host','') in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
    def end_headers(self):
        origin=self.headers.get('Origin')
        if origin in self.origins():
            self.send_header('Access-Control-Allow-Origin',origin)
            self.send_header('Vary','Origin')
            self.send_header('Access-Control-Allow-Private-Network','true')
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('Cache-Control','no-store')
        super().end_headers()
    def reply(self,status,data):
        body=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers()
        try:self.wfile.write(body)
        except BrokenPipeError:pass
    def do_OPTIONS(self):
        if not self.allowed_host() or self.headers.get('Origin') not in self.origins():return self.reply(403,{'error':'허용되지 않은 화면입니다.'})
        self.send_response(204);self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS');self.send_header('Access-Control-Allow-Headers','Content-Type, X-Career-Token');self.end_headers()
    def do_GET(self):
        if not self.allowed_host():return self.reply(403,{'error':'허용되지 않은 호스트입니다.'})
        origin=self.headers.get('Origin')
        if origin and origin not in self.origins():return self.reply(403,{'error':'허용되지 않은 화면입니다.'})
        path=unquote(urlsplit(self.path).path)
        if path=='/api/status':
            with LOCK:state=dict(STATE)
            return self.reply(200,{'configured':bool(read_config().get('api_key')),'model':ai_screen.MODEL,'token':TOKEN,'collection':state})
        if path=='/api/refresh':
            with LOCK:state=dict(STATE)
            return self.reply(200,state)
        if path=='/api/feed':return self.reply(200,json.loads((ROOT/'web/data/jobs.json').read_text()))
        if path.startswith('/api/'):return self.reply(404,{'error':'Not found'})
        if any(s.startswith('.') for s in path.split('/') if s) or '..' in path.split('/'):return self.reply(404,{'error':'Not found'})
        target=(ROOT/'web'/path.lstrip('/')).resolve()
        if not target.is_relative_to((ROOT/'web').resolve()):return self.reply(404,{'error':'Not found'})
        return super().do_GET()
    def list_directory(self,path):return self.reply(404,{'error':'Not found'})
    def do_POST(self):
        global STATE
        if not self.allowed_host() or self.headers.get('Origin') not in self.origins():return self.reply(403,{'error':'허용되지 않은 화면입니다.'})
        if not secrets.compare_digest(self.headers.get('X-Career-Token',''),TOKEN):return self.reply(403,{'error':'도우미 연결을 다시 확인하세요.'})
        if self.headers.get('Content-Type')!='application/json':return self.reply(415,{'error':'JSON만 허용합니다.'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=1000000:return self.reply(413,{'error':'입력 분량 제한 초과'})
            payload=json.loads(self.rfile.read(size))
            if not isinstance(payload,dict):raise ValueError('입력 형식을 확인하세요.')
            if self.path=='/api/settings':
                if set(payload)!={'apiKey'}:raise ValueError('API 키 저장·삭제만 허용합니다.')
                ai_screen.save_key(payload['apiKey'])
                return self.reply(200,{'configured':bool(payload['apiKey']),'model':ai_screen.MODEL})
            if self.path=='/api/sources':
                routine_sites.validate(payload);atomic(ROOT/'.routine-sites.json',payload)
                return self.reply(200,{'saved':len(payload['sources'])})
            if self.path=='/api/refresh':
                with LOCK:
                    if STATE['state']=='running':return self.reply(202,STATE)
                    STATE={'state':'running','message':'전체 사이트 수집 준비 중','completedSources':0}
                    state=dict(STATE)
                threading.Thread(target=collection,args=(payload,),daemon=True).start()
                return self.reply(202,state)
            if self.path=='/api/generate':
                prompt=payload.get('prompt')
                if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>40000:raise ValueError('작성 요청 분량을 확인하세요.')
                return self.reply(200,{'text':response_text(ai_screen.request({'input':prompt,'max_output_tokens':6000}))})
            return self.reply(404,{'error':'Not found'})
        except (ValueError,KeyError,TypeError) as exc:return self.reply(400,{'error':str(exc) if isinstance(exc,ValueError) else '입력 형식을 확인하세요.'})
        except Exception:return self.reply(500,{'error':'로컬 도우미 처리 오류. 기존 자료는 유지됩니다.'})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--configure',action='store_true');p.add_argument('--port',type=int,default=8765);args=p.parse_args()
    if args.configure:configure()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),partial(Handler,directory=str(ROOT/'web')))
    print(f'Career Desk 도우미 실행 중 · http://127.0.0.1:{args.port}/',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:server.server_close()
