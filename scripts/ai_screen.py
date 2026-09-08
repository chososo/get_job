"""OpenAI configuration is local-only. Posting text is data, never instructions."""
import json
import os
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / '.local/openai.json'
MODEL = 'gpt-6-astra'

def read_config():
    if CONFIG.is_symlink():
        raise ValueError('로컬 키 파일을 확인하세요.')
    return json.loads(CONFIG.read_text()) if CONFIG.exists() else {'api_key': '', 'model': MODEL}

def save_key(key):
    if not isinstance(key, str) or len(key) > 600 or any(c.isspace() for c in key):
        raise ValueError('API 키 형식을 확인하세요.')
    if key and not key.startswith('sk-'):
        raise ValueError('OpenAI API 키를 입력하세요.')
    if CONFIG.parent.is_symlink() or CONFIG.is_symlink():
        raise ValueError('로컬 키 저장 경로를 확인하세요.')
    CONFIG.parent.mkdir(exist_ok=True, mode=0o700)
    os.chmod(CONFIG.parent,0o700)
    temporary=CONFIG.with_suffix('.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as out:
        json.dump({'api_key': key, 'model': MODEL}, out)
    os.replace(temporary,CONFIG)

def response_text(data):
    if data.get('status') not in ('completed', None):
        raise ValueError('GPT 응답이 완성되지 않았습니다.')
    result = '\n'.join(part['text'] for item in data.get('output', []) if item.get('type') == 'message'
                       for part in item.get('content', []) if part.get('type') == 'output_text')
    if not result:
        raise ValueError('GPT가 결과를 반환하지 않았습니다.')
    return result

def request(payload, config=None):
    config = config or read_config()
    if not config.get('api_key'):
        raise ValueError('수집 현황 · 설정에서 API 키를 저장하세요.')
    body = {'model': MODEL, 'store': False, 'reasoning': {'effort': 'low'}, **payload}
    req = urllib.request.Request('https://api.openai.com/v1/responses', data=json.dumps(body).encode(),
                                 headers={'Authorization': 'Bearer ' + config['api_key'], 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.load(r)
    except urllib.error.HTTPError as exc:
        # Never echo provider responses, keys, or request bodies into logs/public data.
        raise ValueError(f'OpenAI 연결 오류 ({exc.code}). 설정의 키·결제·Astra 사용 권한을 확인하세요.') from None
    except (urllib.error.URLError, TimeoutError):
        raise ValueError('OpenAI 연결 시간이 초과되었습니다.') from None

SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {
        'decision': {'type': 'string', 'enum': ['include', 'exclude', 'review']},
        'category': {'type': 'string', 'enum': ['퀀트 리서치', '자산운용·자산배분', 'ETF·인덱스', '금융리스크', '파생상품평가', '기업·산업 리서치', '기업 재무·전략투자', '무관']},
        'level': {'type': 'string', 'enum': ['인턴', '신입', '아르바이트', '확인 필요', '경력']},
        'eligibleRoles': {'type': 'string'}, 'eligibility': {'type': 'string'},
        'reason': {'type': 'string'}, 'evidenceQuote': {'type': 'string'},
        'requiredLocalLanguage': {'type': 'boolean'},
        'closed': {'type': 'boolean'},
        'deadlineDate': {'type': ['string', 'null']},
        'deadlineQuote': {'type': 'string'},
    },
}
SCHEMA['required'] = list(SCHEMA['properties'])

def screen(raw, config):
    instruction = (ROOT/'docs/SCREENING_POLICY.md').read_text()
    result = request({'instructions': instruction, 'input': json.dumps(raw, ensure_ascii=False),
                      'text': {'format': {'type': 'json_schema', 'name': 'job_screen', 'strict': True, 'schema': SCHEMA}},
                      'max_output_tokens': 4500}, config)
    data = json.loads(response_text(result))
    text = ' '.join((raw.get('title', '') + ' ' + raw.get('body', '')).split())
    quote = ' '.join(data.get('evidenceQuote', '').split())
    if data.get('decision') == 'include' and (not quote or quote not in text):
        data.update(decision='review', reason='AI의 판단 근거를 원문에서 확인하지 못했습니다.')
    deadline_quote = ' '.join(data.get('deadlineQuote', '').split())
    if not deadline_quote or deadline_quote not in text:
        data['deadlineDate'] = None
    return data
