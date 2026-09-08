// No API keys or personal documents are stored by this bridge.
export function helperBase(location){return ['127.0.0.1','localhost'].includes(location.hostname)?location.origin:'http://127.0.0.1:8765';}
let token='';
export async function helper(path,payload){
  const base=helperBase(location);
  try{
    if(payload!==undefined&&!token){const status=await helper('/api/status');token=status.token;}
    const response=await fetch(base+path,{method:payload===undefined?'GET':'POST',cache:'no-store',
      headers:payload===undefined?{}:{'Content-Type':'application/json','X-Career-Token':token},
      body:payload===undefined?undefined:JSON.stringify(payload),signal:AbortSignal.timeout(path==='/api/generate'?200000:10000)});
    const data=await response.json();
    if(!response.ok){if(response.status===403)token='';throw Error(data.error||'도우미 요청 실패');}
    if(data.token)token=data.token;
    return data;
  }catch(e){
    if(e.name==='TypeError'||e.name==='TimeoutError')throw Error('이 Mac의 로컬 도우미에 연결할 수 없습니다. 수집 현황 · 설정에서 실행 방법을 확인하세요.');
    throw e;
  }
}
export function apiPanel(){return `<section class="panel"><h2>공고 심사 · GPT 연결</h2>
<p id="api-connection" role="status">로컬 도우미 연결 확인 중…</p>
<p>키 없음: 규칙 기반 심사 · 키 저장됨: <strong>GPT-6 Astra</strong>가 원문을 읽고 직무·필수 자격·마감을 정리합니다.</p>
<form id="api-settings"><label for="api-key">OpenAI API 키</label><input id="api-key" type="password" autocomplete="off" spellcheck="false" maxlength="600" placeholder="sk-… (저장된 키는 표시하지 않습니다)">
<div class="actions"><button id="api-save" class="primary" type="submit">이 Mac에 키 저장</button><button id="api-delete" type="button">키 삭제 · 규칙 방식으로 전환</button><button id="api-check" type="button">도우미 연결 확인</button></div></form>
<p class="muted">한 번 저장하면 새로고침·예약 수집에서 다시 묻지 않습니다. 키는 이 Mac에만 저장하며 GitHub·브라우저 보관함에 넣지 않습니다. 키 저장 후 수집하면 공개 공고 본문이 OpenAI로 전송되고 별도 API 요금이 발생합니다. 경험·자소서는 공고 수집에 사용하지 않습니다.</p>
<details><summary>로컬 도우미 실행 방법</summary><p>이 Mac의 quant-career-desk 폴더에서 <strong>Career Desk 시작.command</strong>를 더블클릭하고 열린 창을 유지하세요. GitHub Pages 화면에서 사용할 수 있습니다. 브라우저가 로컬 네트워크 접근을 물으면 허용하세요.</p><p>GitHub Pages는 화면을 제공하고, 재수집·API 키 보관은 로컬 도우미가 실행합니다. 컴퓨터가 꺼져 있으면 수집할 수 없습니다.</p></details></section>`;}
export function bindApiPanel(notify){
  const $=s=>document.querySelector(s);
  const status=message=>{if($('#api-connection'))$('#api-connection').textContent=message;};
  const check=async()=>{try{const data=await helper('/api/status');status(data.configured?'도우미 연결됨 · 키 저장됨 · Astra 심사 (모델 접근 권한은 실제 호출 시 확인)':'도우미 연결됨 · 키 없음 · 규칙 기반 심사');}catch(e){status(e.message);}};
  $('#api-settings').onsubmit=async e=>{e.preventDefault();const input=$('#api-key');const key=input.value.trim();if(!key)return status('저장할 API 키를 입력하세요.');$('#api-save').disabled=true;try{await helper('/api/settings',{apiKey:key});input.value='';await check();notify('키를 이 Mac에 저장했습니다. 다음 수집부터 Astra를 사용합니다.');}catch(e){status(e.message);}finally{if($('#api-save'))$('#api-save').disabled=false;}};
  $('#api-delete').onclick=async()=>{try{await helper('/api/settings',{apiKey:''});$('#api-key').value='';await check();notify('키를 삭제했습니다. 다음 수집부터 규칙 방식을 사용합니다.');}catch(e){status(e.message);}};
  $('#api-check').onclick=check;check();
}
