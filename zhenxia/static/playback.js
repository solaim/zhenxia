'use strict';
// Each resource has its own record so concurrent tabs cannot overwrite other resources.
window.PlaybackProgress = (() => {
  const prefix = 'zhenxia.playback.';
  const fallback = new Map();
  const dirty = new Set();
  const version = item => JSON.stringify([item.size, item.modified]);
  function read(item) {
    const key = prefix + item.id;
    let text = fallback.get(key);
    if (!dirty.has(key)) {
      try { text = localStorage.getItem(key); } catch (_) {}
    }
    try {
      const record = JSON.parse(text);
      if (record?.version !== version(item) || !Number.isFinite(record.position) || record.position <= 0) return 0;
      if (Number.isFinite(record.duration) && record.position >= record.duration - .5) return 0;
      return record.position;
    } catch (_) { return 0; }
  }
  function clear(item) {
    const key = prefix + item.id;
    fallback.set(key,null);
    try { localStorage.removeItem(key); dirty.delete(key); } catch (_) { dirty.add(key); }
  }
  function save(item, position, duration, ended = false) {
    if (!Number.isFinite(position) || position < 0) return;
    if (ended || position === 0 || (Number.isFinite(duration) && position >= duration - .5)) {
      clear(item); return;
    }
    const key = prefix + item.id;
    const text = JSON.stringify({version:version(item), position, duration:Number.isFinite(duration) ? duration : null});
    fallback.set(key,text);
    try { localStorage.setItem(key,text); dirty.delete(key); } catch (_) { dirty.add(key); }
  }
  return {read, save, clear};
})();
