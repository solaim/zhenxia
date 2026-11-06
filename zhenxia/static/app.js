'use strict';
const t = (key, values) => I18n.t(key, values);
const $ = selector => document.querySelector(selector);
const state = {kind: 'all', query: '', offset: 0, items: [], view: 'library', busy: false};
let toastTimer;
function toast(message) { $('#toast').textContent = message; $('#toast').classList.remove('hidden'); clearTimeout(toastTimer); toastTimer = setTimeout(() => $('#toast').classList.add('hidden'), 5000); }
async function api(path, options = {}) {
  const response = await fetch('/api/v1/' + path, {headers: {'Content-Type': 'application/json'}, ...options});
  if (!response.ok) { let message = t('error.request'); try { const data = await response.json(); message = typeof data.detail === 'string' ? data.detail : t('error.input'); } catch (_) {} throw new Error(I18n.error(message)); }
  return response.json();
}
function element(tag, cls, text) { const node = document.createElement(tag); if (cls) node.className = cls; if (text !== undefined) node.textContent = text; return node; }
function size(bytes) { if (!bytes) return '0 B'; const units = ['B','KB','MB','GB','TB']; const n = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), 4); return (bytes / 1024 ** n).toFixed(n ? 1 : 0) + ' ' + units[n]; }
function date(timestamp) { return new Date(timestamp * 1000).toLocaleDateString(I18n.language); }
function view(name) { state.view = name; for (const node of document.querySelectorAll('.view')) node.classList.toggle('hidden', node.id !== name + '-view'); for (const button of document.querySelectorAll('.nav')) button.classList.toggle('active', button.dataset.view === name); $('#page-label').textContent = t('nav.' + name); }
for (const button of document.querySelectorAll('.nav')) button.addEventListener('click', () => { view(button.dataset.view); refresh().catch(error => toast(error.message)); });
function preview(item) {
  const kind = item.type.split('/')[0];
  const media = element(kind === 'image' ? 'img' : kind);
  media.src = '/api/v1/resources/' + item.id + '/file';
  if (kind !== 'image') { media.controls = true; media.autoplay = true; }
  else media.alt = item.name;
  $('#preview-title').textContent = item.name;
  $('#preview-content').replaceChildren(media);
  $('#preview').showModal();
}
$('#close-preview').addEventListener('click', () => $('#preview').close());
$('#preview').addEventListener('close', () => $('#preview-content').replaceChildren());
$('#preview').addEventListener('click', event => { if (event.target === $('#preview')) { const rect = event.target.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) event.target.close(); } });
function card(item) {
  const node = element('article', 'card');
  const thumb = element('button', 'thumbnail'); thumb.setAttribute('aria-label', t('preview.label', {name: item.name}));
  const kind = item.type.split('/')[0];
  if (kind === 'audio') thumb.append(element('div', 'audio-cover', '♫'));
  else { const media = element(kind === 'image' ? 'img' : 'video'); media.src = '/api/v1/resources/' + item.id + '/file' + (kind === 'video' ? '#t=0.1' : ''); if (kind === 'video') { media.preload = 'metadata'; media.muted = true; media.playsInline = true; } else { media.loading = 'lazy'; media.alt = item.name; } thumb.append(media); }
  thumb.append(element('span', 'play', kind === 'video' ? '▷' : kind === 'audio' ? '♫' : '⤢'));
  thumb.append(element('span','media-label', t('media.' + (['video','image','audio'].includes(kind) ? kind : 'other'))));
  thumb.addEventListener('click', () => preview(item));
  const body = element('div','card-body'); const title = element('h3','card-title',item.title || item.name); title.title = item.path;
  const info = element('div','card-info'); info.append(element('span','',date(item.modified)),element('span','',size(item.size)));
  const actions = element('div','card-actions'); const download = element('a','',t('file.save')); download.href = '/api/v1/resources/' + item.id + '/file?download=true'; download.download = item.name;
  const remove = element('button','',t('file.remove')); remove.addEventListener('click', async () => { if (!confirm(t('file.confirm', {name: item.name}))) return; remove.disabled = true; try { await api('resources/' + item.id, {method:'DELETE'}); await refresh(); toast(t('file.trashed')); } catch (error) { toast(error.message); } finally { remove.disabled = false; } });
  actions.append(download,remove); body.append(title,info,actions); node.append(thumb,body); return node;
}
let resourceRequest = 0;
function reconcileResources(items) {
  const grid = $('#resources');
  const existing = new Map([...grid.children].map(node => [node.dataset.resourceId, node]));
  const keep = new Set(items.map(item => item.id));
  for (const node of [...grid.children]) if (!keep.has(node.dataset.resourceId)) node.remove();
  items.forEach((item, index) => {
    const signature = JSON.stringify(item);
    let node = existing.get(item.id);
    if (!node || node.resourceSignature !== signature) {
      const replacement = card(item);
      replacement.dataset.resourceId = item.id;
      replacement.resourceSignature = signature;
      if (node?.isConnected) node.replaceWith(replacement);
      node = replacement;
    }
    if (grid.children[index] !== node) grid.insertBefore(node, grid.children[index] || null);
  });
}
async function loadResources(append = false, preserve = false) {
  const requestId = ++resourceRequest;
  const offset = append ? state.items.length : 0;
  const wanted = preserve ? Math.max(60,state.items.length) : 60;
  const params = new URLSearchParams({q:state.query,kind:state.kind,offset,limit:Math.min(200,wanted)});
  const data = await api('resources?' + params);
  if (preserve && wanted > 200 && data.total > 200) {
    const pages = [];
    for (let offset = 200; offset < Math.min(wanted,data.total); offset += 200) {
      pages.push(api('resources?' + new URLSearchParams({q:state.query,kind:state.kind,offset,limit:Math.min(200,wanted-offset)})));
    }
    for (const page of await Promise.all(pages)) data.items.push(...page.items);
  }
  if (requestId !== resourceRequest) return;
  state.resourceSummary = data;
  state.items = append ? state.items.concat(data.items) : data.items;
  reconcileResources(state.items);
  $('#empty').classList.toggle('hidden',data.total > 0);
  $('#resource-summary').textContent = t(data.total === 1 ? 'resources.count.one' : 'resources.count', {count: new Intl.NumberFormat(I18n.language).format(data.total), size: size(data.bytes)});
  $('#load-more').classList.toggle('hidden',state.items.length >= data.total);
}
function renderStats(data) { if (!data) return; $('#nav-count').textContent = data.total; $('#stat-count').replaceChildren(document.createTextNode(data.total + ' '),element('em','',t('unit.resources'))); $('#stat-size').textContent = size(data.bytes); }
async function loadStats() { state.stats = await api('resources?limit=1'); renderStats(state.stats); }
async function loadJobs() {
  state.jobs = await api('jobs'); return renderJobs(state.jobs);
}
function renderJobs(data) {
  if (!data) return 0;
  const jobs = data.jobs;
  const active = jobs.filter(j => ['pending','running'].includes(j.status)).length;
  $('#active-count').textContent = active; $('#stat-active').replaceChildren(document.createTextNode(active + ' '),element('em','',t('unit.jobs')));
  $('#jobs').replaceChildren(...jobs.map(job => {
    const row = element('article','job'); const text = element('div','job-text'); text.append(element('div','job-url',job.url));
    let detail = new Date(job.created_at).toLocaleString(I18n.language) + ' · ' + t('jobs.detail', job);
    if (job.error) detail += '\n' + I18n.error(job.error);
    if (job.status === 'running') {
      const p = job.progress || {};
      const elapsed = Math.max(0, Math.floor((Date.now() - Date.parse(job.started_at || job.created_at)) / 1000));
      const box = element('div','download-progress');
      const label = element('div','progress-label',t('progress.' + (p.phase || 'extracting')));
      const metrics = [t('progress.elapsed', {seconds:elapsed})];
      if ((p.phase || 'extracting') === 'extracting' && elapsed >= 20) box.append(element('div','progress-item',t('progress.waiting')));
      if (p.phase === 'downloading') {
        if (p.percent != null) metrics.push(Number(p.percent).toFixed(1) + '%');
        if (p.downloaded != null) metrics.push(size(p.downloaded) + (p.total ? ' / ' + size(p.total) : ''));
        if (p.speed) metrics.push(size(p.speed) + '/s');
        if (p.eta != null) metrics.push(t('progress.eta',{seconds:Math.ceil(p.eta)}));
      }
      if (metrics.length) label.append(document.createTextNode(' · ' + metrics.join(' · ')));
      box.append(label);
      if (p.item) box.append(element('div','progress-item',p.item + (p.format ? ' · ' + p.format : '')));
      const bar = element('progress'); bar.max = 100;
      if (p.phase === 'downloading' && p.percent != null) bar.value = Math.min(100,Math.max(0,p.percent));
      bar.setAttribute('aria-label',t('progress.' + (p.phase || 'extracting'))); box.append(bar);text.append(box);
    }
    text.append(element('div','job-detail',detail)); row.append(text,element('span','status ' + job.status,t(job.status === 'running' ? 'progress.' + (job.progress?.phase || 'extracting') : 'status.' + job.status)));
    if (job.status === 'failed') { const retry = element('button','subtle',t('jobs.retry')); retry.addEventListener('click',async () => { retry.disabled = true; try { await api('jobs/' + job.job_id + '/retry',{method:'POST'}); toast(t('jobs.requeued')); await loadJobs(); } catch (error) { toast(error.message); } finally { retry.disabled = false; } }); row.append(retry); }
    return row;
  }));
  $('#jobs-empty').classList.toggle('hidden',jobs.length > 0);
  return active;
}
function renderSettings(data) {
  if (!data) return;
  renderTranscript(data.transcript);
  if (document.activeElement !== $('#limits-gb')) $('#limits-gb').value = data.download_limits.max_gb;
  $('#tiktok-login-status').textContent = t(data.platforms.find(p => p.id === 'tiktok')?.cookie_configured ? 'login.configured' : 'login.empty');
  $('#cookie-status').textContent = t(data.cookie_configured ? 'cookie.configured' : 'cookie.empty');
  const selected = data.platforms.find(p => p.id === $('#cookie-platform').value);
  $('#platform-cookie-status').textContent = t(selected?.cookie_configured ? 'cookie.configured' : 'cookie.empty');
}
async function loadSettings() { state.settings = await api('settings'); renderSettings(state.settings); }
async function refresh() { await Promise.all([loadResources(),loadStats(),loadJobs(),loadSettings()]); }
$('#download-form').addEventListener('submit',async event => { event.preventDefault(); $('#submit-download').disabled = true; try { await api('download',{method:'POST',body:JSON.stringify({url:$('#url').value})}); $('#url').value = ''; toast(t('jobs.queued')); view('jobs'); await loadJobs(); } catch (error) { toast(error.message); } finally { $('#submit-download').disabled = false; } });
$('#cookie-form').addEventListener('submit',async event => { event.preventDefault(); if (!$('#cookie').value.trim() && !confirm(t('cookie.confirm'))) return; const button = event.target.querySelector('button'); button.disabled = true; try { await api('settings/cookie',{method:'PUT',body:JSON.stringify({cookie:$('#cookie').value})}); $('#cookie').value = ''; await loadSettings(); toast(t('cookie.saved')); } catch (error) { toast(error.message); } finally { button.disabled = false; } });
for (const button of document.querySelectorAll('.tab')) button.addEventListener('click',async () => { state.kind = button.dataset.kind; for (const tab of document.querySelectorAll('.tab')) tab.classList.toggle('active',tab === button); try { await loadResources(); } catch (error) { toast(error.message); } });
let searchTimer;
$('#search').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(async () => { state.query = $('#search').value; try { await loadResources(); } catch (error) { toast(error.message); } },250); });
$('#refresh').addEventListener('click', async () => { try { await api('resources/scan', {method:'POST'}); await refresh(); toast(t('resources.synced')); } catch (error) { toast(error.message); } });
$('#load-more').addEventListener('click', () => loadResources(true).catch(error => toast(error.message)));
I18n.init().then(() => { view(state.view); return refresh(); }).catch(error => toast(t('error.connection', {message: error.message})));
$('#language').addEventListener('change', event => I18n.setLanguage(event.target.value));
window.addEventListener('languagechange', () => {
  $('#toast').classList.add('hidden');
  view(state.view);
  renderStats(state.stats);
  renderJobs(state.jobs);
  renderSettings(state.settings);
  const summary = state.resourceSummary;
  if (summary) $('#resource-summary').textContent = t(summary.total === 1 ? 'resources.count.one' : 'resources.count', {count: new Intl.NumberFormat(I18n.language).format(summary.total), size: size(summary.bytes)});
  // Translate existing cards in place: keep media elements, pagination and scroll position.
  for (const [index, node] of [...$('#resources').children].entries()) {
    const item = state.items[index];
    if (!item) continue;
    const kind = item.type.split('/')[0];
    node.querySelector('.thumbnail').setAttribute('aria-label', t('preview.label', {name:item.name}));
    node.querySelector('.media-label').textContent = t('media.' + (['video','image','audio'].includes(kind) ? kind : 'other'));
    node.querySelector('.card-info span').textContent = date(item.modified);
    node.querySelector('.card-actions a').textContent = t('file.save');
    node.querySelector('.card-actions button').textContent = t('file.remove');
  }
});
let wasActive = false;
setInterval(async () => { if (document.hidden || state.busy) return; state.busy = true; try { const active = await loadJobs(); if (active || wasActive) { await loadStats(); if (state.view === 'library') await loadResources(false,true); } wasActive = active > 0; } catch (_) {} finally { state.busy = false; } },1000);

$('#cookie-platform').addEventListener('change', () => { $('#platform-cookie').value = ''; renderSettings(state.settings); });
$('#platform-cookie-form').addEventListener('submit', async event => {
  event.preventDefault();
  const field = $('#platform-cookie');
  if (!field.value.trim() && !confirm(t('cookie.confirm'))) return;
  const button = event.target.querySelector('button'); button.disabled = true;
  try {
    await api('settings/cookies/' + $('#cookie-platform').value, {method:'PUT', body:JSON.stringify({cookie:field.value})});
    field.value = ''; await loadSettings(); toast(t('cookie.saved'));
  } catch (error) { toast(error.message); } finally { button.disabled = false; }
});

let transcriptLoaded = false;
function renderTranscript(value) {
  if (!value) return;
  if (!transcriptLoaded) {
    $('#transcript-enabled').checked = value.enabled;
    $('#transcript-url').value = value.api_url;
    $('#transcript-model').value = value.model;
    $('#transcript-env').value = value.api_key_env;
    transcriptLoaded = true;
  }
  $('#transcript-key-status').textContent = t('transcript.key-' + value.key_source);
}
$('#transcript-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.target.querySelector('button');button.disabled = true;
  try {
    await api('settings/transcript',{method:'PUT',body:JSON.stringify({
      enabled:$('#transcript-enabled').checked,api_url:$('#transcript-url').value,
      model:$('#transcript-model').value,api_key_env:$('#transcript-env').value,
      api_key:$('#transcript-key').value,clear_key:$('#transcript-clear').checked
    })});
    $('#transcript-key').value = '';$('#transcript-clear').checked = false;
    await loadSettings();toast(t('transcript.saved'));
  } catch(error) { toast(error.message); } finally { button.disabled = false; }
});

let loginTimer, loginBusy = false, loginActionBusy = false, loginFrameURL, loginSerial = 0;
async function loginAction(values) {
  if (loginActionBusy) return;
  loginActionBusy = true;
  try { await api('login/action',{method:'POST',body:JSON.stringify(values)}); }
  catch(error) { toast(error.message); }
  finally { loginActionBusy = false; }
}
async function pollLogin(serial) {
  if (loginBusy || serial !== loginSerial || !$('#login-dialog').open) return;
  loginBusy = true;
  try {
    const status = await api('login/status');
    if (serial !== loginSerial) return;
    $('#login-state').textContent = t('login.state.' + status.state) + ' · ' + status.seconds_left + 's';
    if (status.state === 'waiting') {
      const response = await fetch('/api/v1/login/frame',{cache:'no-store'});
      if (response.status === 200) {
        const blob = await response.blob();
        if (serial !== loginSerial) return;
        const old = loginFrameURL; loginFrameURL = URL.createObjectURL(blob);
        $('#login-image').src = loginFrameURL;
        if (old) URL.revokeObjectURL(old);
      }
    }
    if (['saved','failed','expired','cancelled','region_blocked'].includes(status.state)) {
      clearInterval(loginTimer);
      if (loginFrameURL) { URL.revokeObjectURL(loginFrameURL);loginFrameURL=null; }
      $('#login-image').removeAttribute('src');
      await loadSettings();
      if (status.state === 'saved') toast(t('login.state.saved'));
    }
  } catch(error) { clearInterval(loginTimer); $('#login-state').textContent = error.message; }
  finally { loginBusy = false; }
}
$('#start-tiktok-login').addEventListener('click',async () => {
  const button=$('#start-tiktok-login');button.disabled=true;
  try {
    await api('login/tiktok',{method:'POST'});
    $('#login-dialog').showModal();
    const serial=++loginSerial;
    $('#login-state').textContent=t('login.state.starting');
    clearInterval(loginTimer);loginTimer=setInterval(()=>pollLogin(serial),1200);await pollLogin(serial);
  } catch(error) { toast(error.message); } finally { button.disabled=false; }
});
$('#close-login').addEventListener('click',()=>$('#login-dialog').close());
$('#login-dialog').addEventListener('close',async()=>{
  ++loginSerial;clearInterval(loginTimer);$('#login-text').value='';
  $('#login-image').removeAttribute('src');
  if(loginFrameURL){URL.revokeObjectURL(loginFrameURL);loginFrameURL=null;}
  try{await api('login/session',{method:'DELETE'});}catch(_){}
});
let loginPointer;
function loginPoint(event) {
  const rect=$('#login-image').getBoundingClientRect();
  return {x:Math.max(0,Math.min(1100,(event.clientX-rect.left)/rect.width*1100)),y:Math.max(0,Math.min(760,(event.clientY-rect.top)/rect.height*760))};
}
$('#login-image').addEventListener('pointerdown',event=>{
  event.preventDefault();loginPointer=loginPoint(event);event.target.setPointerCapture(event.pointerId);
});
$('#login-image').addEventListener('pointerup',event=>{
  if(!loginPointer)return;
  const end=loginPoint(event),start=loginPointer;loginPointer=null;
  if(Math.hypot(end.x-start.x,end.y-start.y)>8) loginAction({kind:'drag',...start,end_x:end.x,end_y:end.y});
  else loginAction({kind:'click',...start});
  $('#login-screen').focus();
});
$('#login-image').addEventListener('pointercancel',()=>{loginPointer=null;});
$('#login-screen').addEventListener('keydown',event=>{
  if(['Tab','Enter','Backspace','Escape','ArrowDown','ArrowUp'].includes(event.key)){
    event.preventDefault();loginAction({kind:'key',key:event.key});
  }
});
$('#login-screen').addEventListener('wheel',event=>{event.preventDefault();loginAction({kind:'scroll',y:event.deltaY});},{passive:false});
$('#login-text-form').addEventListener('submit',async event=>{
  event.preventDefault();const input=$('#login-text');
  await loginAction({kind:'text',text:input.value});input.value='';
});
$('#login-enter').addEventListener('click',()=>loginAction({kind:'key',key:'Enter'}));
$('#login-backspace').addEventListener('click',()=>loginAction({kind:'key',key:'Backspace'}));
$('#clear-tiktok-login').addEventListener('click',async()=>{
  if(!confirm(t('login.confirm-clear')))return;
  try{await api('login/tiktok/credentials',{method:'DELETE'});await loadSettings();toast(t('login.cleared'));}
  catch(error){toast(error.message);}
});

$('#limits-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.target.querySelector('button'); button.disabled = true;
  try { await api('settings/download-limits', {method:'PUT', body:JSON.stringify({max_gb:Number($('#limits-gb').value)})}); await loadSettings(); toast(t('limits.save')); }
  catch(error) { toast(error.message); } finally { button.disabled = false; }
});
