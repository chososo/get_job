import test from 'node:test';
import assert from 'node:assert/strict';
import {dateInZone,liveStatus,calendarCells,safeUrl,esc,writingPrompt,blankState} from '../web/modules/domain.js';
import {newEnvelope,openEnvelope,encrypt} from '../web/modules/vault.js';
import {registerPublicTools} from '../web/modules/agent-tools.js';

test('KST changes day while UK is still on prior day',()=>{
 const now=new Date('2026-09-08T15:01:00Z');assert.equal(dateInZone(now),'2026-09-09');assert.equal(dateInZone(now,'Europe/London'),'2026-09-08');
});
test('date-only deadline stays open on the stated local day, not the next',()=>{
 const job={status:'open',deadlineDate:'2026-09-08',deadlineTimezone:'Asia/Seoul',lastVerifiedAt:'2026-09-08T01:00:00Z'};
 assert.equal(liveStatus(job,new Date('2026-09-08T14:59:59Z')),'open');assert.equal(liveStatus(job,new Date('2026-09-08T15:00:00Z')),'closed');
});
test('precise deadline and stale verification',()=>{
 assert.equal(liveStatus({status:'open',deadlineAt:'2026-09-08T04:00:00Z'},new Date('2026-09-08T05:00:00Z')),'closed');
 assert.equal(liveStatus({status:'open',lastVerifiedAt:'2026-09-01T00:00:00Z'},new Date('2026-09-08T05:00:00Z')),'review');
});
test('calendar is stable across leap and year boundaries',()=>{
 assert.equal(calendarCells(2028,1).filter(c=>c.current).length,29);assert.equal(calendarCells(2026,0).length,42);assert.equal(calendarCells(2026,0)[0].date,'2025-12-28');
});
test('untrusted strings cannot become executable links or markup',()=>{
 assert.equal(safeUrl('javascript:alert(1)'),'');assert.equal(safeUrl('data:text/html,test'),'');assert.equal(safeUrl('https://example.com/a'),'https://example.com/a');assert.equal(esc('<img onerror="x">'),'&lt;img onerror=&quot;x&quot;&gt;');
});
test('writing prompt includes only explicitly supplied experiences',()=>{
 const prompt=writingPrompt({company:'A',role:'Risk intern',kind:'CV',experiences:[{id:'selected',title:'Known project'}]});assert.match(prompt,/selected/);assert.match(prompt,/지어내지/);assert.doesNotMatch(prompt,/unselected/);
});
test('vault roundtrip, wrong password, tampering, and IV uniqueness',async()=>{
 const a=await newEnvelope('test-password-123');a.state.documents.push({id:'1',content:'Private test content'});
 const one=await encrypt(a.state,a.key,a.salt),two=await encrypt(a.state,a.key,a.salt);assert.notEqual(one.iv,two.iv);assert.doesNotMatch(JSON.stringify(one),/Private test content/);
 const opened=await openEnvelope(one,'test-password-123');assert.equal(opened.state.documents[0].content,'Private test content');
 await assert.rejects(openEnvelope(one,'wrong-password'));const bad={...one,ciphertext:(one.ciphertext[0]==='A'?'B':'A')+one.ciphertext.slice(1)};await assert.rejects(openEnvelope(bad,'test-password-123'));
 await assert.rejects(openEnvelope({...one,iterations:1},'test-password-123'));
});
test('agent tool contracts reject invalid inputs and expose public data only',()=>{
 const tools=[];const data=[{id:'one',company:'Acme',title:'Quant',sourceUrl:'https://example.com',country:'KR',status:'open'}];let opened;
 const lifecycle=registerPublicTools({registerTool:t=>tools.push(t)},()=>data,id=>opened=id);
 assert.equal(tools.length,2);assert.equal(tools[0].annotations.readOnlyHint,true);assert.equal(tools[0].execute({query:'quant'}).length,1);
 assert.throws(()=>tools[0].execute({query:42}));assert.throws(()=>tools[1].execute({id:'missing'}));assert.equal(opened,undefined);assert.deepEqual(tools[1].execute({id:'one'}),{opened:'one'});assert.equal(opened,'one');lifecycle.abort();
});
