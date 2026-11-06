const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname,'../zhenxia/static/playback.js'),'utf8');
function create(storage = new Map(), blocked = false) {
  const context = {window:{},localStorage:{
    getItem(key) { if(blocked)throw Error('blocked'); return storage.get(key) ?? null; },
    setItem(key,value) { if(blocked)throw Error('blocked'); storage.set(key,value); },
    removeItem(key) { if(blocked)throw Error('blocked'); storage.delete(key); },
  }};
  vm.runInNewContext(source,context);
  return context.window.PlaybackProgress;
}
const item = {id:'video',size:123,modified:123456};
test('saved progress survives a new page context and stays scoped to each resource', () => {
  const storage = new Map(); const first = create(storage);
  first.save(item,42.5,120); first.save({...item,id:'other'},9,90);
  const next = create(storage);
  assert.equal(next.read(item),42.5);
  assert.equal(next.read({...item,id:'other'}),9);
  assert.equal(next.read({...item,id:'unknown'}),0);
});
test('replaced media and corrupt records never seek to stale positions', () => {
  const storage = new Map();const history=create(storage);history.save(item,12,90);
  assert.equal(history.read({...item,size:124}),0);
  assert.equal(history.read({...item,modified:999}),0);
  for (const value of ['invalid','null','{"position":-1}','{"position":"42"}']) {
    storage.set('zhenxia.playback.video',value);
    assert.equal(create(storage).read(item),0);
  }
});
test('restart and finishing playback remove resume state', () => {
  const history=create();
  history.save(item,42,120);history.clear(item);assert.equal(history.read(item),0);
  history.save(item,42,120);history.save(item,120,120,true);assert.equal(history.read(item),0);
  history.save(item,42,120);history.save(item,0,120);assert.equal(history.read(item),0);
});
test('invalid times are ignored and unknown duration does not break progress', () => {
  const history=create();history.save(item,30,Infinity);assert.equal(history.read(item),30);
  for (const position of [NaN,Infinity,-10])history.save(item,position,120);
  assert.equal(history.read(item),30);
});
test('blocked browser storage still permits progress within the current page', () => {
  const history=create(new Map(),true);
  history.save(item,12,90);assert.equal(history.read(item),12);
  history.clear(item);assert.equal(history.read(item),0);
});

test('another tab can update the same resource without a stale in-memory record', () => {
  const storage = new Map(); const first = create(storage); const second = create(storage);
  first.save(item,12,90); second.save(item,45,90); assert.equal(first.read(item),45);
  second.clear(item); assert.equal(first.read(item),0);
});
