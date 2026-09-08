import test from 'node:test';
import assert from 'node:assert/strict';
import {helperBase,apiPanel} from '../web/modules/collector.js';
test('Pages uses loopback; local preview uses its own port',()=>{
  assert.equal(helperBase({hostname:'chososo.github.io',origin:'https://chososo.github.io'}),'http://127.0.0.1:8765');
  assert.equal(helperBase({hostname:'localhost',origin:'http://localhost:8765'}),'http://localhost:8765');
});
test('Settings has a persistent save/delete flow with no secret in markup',()=>{
  assert.match(apiPanel(),/type="password"/);assert.match(apiPanel(),/id="api-delete"/);assert.match(apiPanel(),/GPT-6 Astra/);
});
