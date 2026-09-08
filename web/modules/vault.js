import {blankState,validState} from './domain.js';
const DB='get-job-private-v1', STORE='vault', ITERATIONS=600000;
const bytes64=b=>btoa(Array.from(new Uint8Array(b),x=>String.fromCharCode(x)).join(''));
const from64=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
async function derive(password,salt,iterations=ITERATIONS) {
  const base=await crypto.subtle.importKey('raw',new TextEncoder().encode(password),'PBKDF2',false,['deriveKey']);
  return crypto.subtle.deriveKey({name:'PBKDF2',salt,iterations,hash:'SHA-256'},base,{name:'AES-GCM',length:256},false,['encrypt','decrypt']);
}
export async function encrypt(state,key,salt) {
  const iv=crypto.getRandomValues(new Uint8Array(12));
  const ciphertext=await crypto.subtle.encrypt({name:'AES-GCM',iv},key,new TextEncoder().encode(JSON.stringify(state)));
  return {format:'quant-career-vault',version:1,iterations:ITERATIONS,salt:bytes64(salt),iv:bytes64(iv),ciphertext:bytes64(ciphertext)};
}
export async function openEnvelope(envelope,password) {
  if(envelope?.format!=='quant-career-vault'||envelope.version!==1||envelope.iterations!==ITERATIONS||typeof envelope.ciphertext!=='string'||envelope.ciphertext.length>14000000) throw Error('지원하지 않는 백업 형식입니다.');
  const salt=from64(envelope.salt), iv=from64(envelope.iv);
  if(salt.length!==16||iv.length!==12) throw Error('손상된 백업입니다.');
  const key=await derive(password,salt,envelope.iterations);
  let decoded; try { decoded=await crypto.subtle.decrypt({name:'AES-GCM',iv},key,from64(envelope.ciphertext)); } catch {throw Error('비밀번호가 다르거나 백업이 손상되었습니다.');}
  const state=JSON.parse(new TextDecoder().decode(decoded));
  if(!validState(state)) throw Error('지원하지 않는 자료 구조입니다.');
  return {state,key,salt};
}
export async function newEnvelope(password) {
  const salt=crypto.getRandomValues(new Uint8Array(16)); const key=await derive(password,salt); const state=blankState();
  return {state,key,salt,envelope:await encrypt(state,key,salt)};
}
let connection;
async function db() { if(connection) return connection; connection=await new Promise((resolve,reject)=>{const r=indexedDB.open(DB,1);r.onupgradeneeded=()=>r.result.createObjectStore(STORE);r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(Error('브라우저 로컬 저장소를 열 수 없습니다.'));}); return connection; }
export async function loadEnvelope() {const d=await db();return new Promise((resolve,reject)=>{const r=d.transaction(STORE).objectStore(STORE).get('main');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});}
export async function storeEnvelope(envelope) {const d=await db();return new Promise((resolve,reject)=>{const tx=d.transaction(STORE,'readwrite');tx.objectStore(STORE).put(envelope,'main');tx.oncomplete=resolve;tx.onerror=()=>reject(Error('저장하지 못했습니다. 저장 공간을 확인하세요.'));tx.onabort=()=>reject(Error('저장이 중단되었습니다.'));});}
