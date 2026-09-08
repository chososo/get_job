import test from 'node:test';
import assert from 'node:assert/strict';
import {makeSource,routineExport,recruitmentUrl,duplicateSource} from '../web/modules/sources.js';
test('company-only entries resolve known names and retain unknown search targets',()=>{
  assert.equal(makeSource('나이스평가정보','',[{name:'NICE평가정보',url:'https://nice.career.greetinghr.com/'}]).url,'https://nice.career.greetinghr.com/');
  assert.equal(makeSource('새로운 회사','').url,'');
  assert.equal(makeSource('','careers.example.com').name,'careers.example.com');
  assert.throws(()=>makeSource('',''));
});
test('routine export omits private fields and preserves pause and deletion snapshots',()=>{
  const output=routineExport([{name:'회사',url:'https://example.com',enabled:false,experiences:['secret'],id:'private'}]);
  assert.deepEqual(output.sources,[{name:'회사',url:'https://example.com/',enabled:false}]);
  assert.deepEqual(routineExport([]).sources,[]);
  assert.equal(duplicateSource([{id:'a',name:'NICE평가정보',url:''}],{name:'나이스평가정보',url:''}),true);
});
test('public links reject credentials, executable schemes and local hosts',()=>{
  for(const url of ['javascript:alert(1)','https://user:pass@example.com','http://127.0.0.1','https://test.local','https://example.com?access_token=secret'])assert.throws(()=>recruitmentUrl(url));
});
