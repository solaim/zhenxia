'use strict';
// Dictionaries are plain JSON so new languages can be added without changing views.
window.I18n = (() => {
  const supported = ['zh-CN', 'en'];
  const dictionaries = {};
  let language = 'zh-CN';
  function preferred() {
    let saved;
    try { saved = localStorage.getItem('zhenxia.language'); } catch (_) {}
    if (supported.includes(saved)) return saved;
    for (const candidate of navigator.languages || [navigator.language || 'en']) {
      if (candidate.toLowerCase().startsWith('zh')) return 'zh-CN';
      if (candidate.toLowerCase().startsWith('en')) return 'en';
    }
    return 'en';
  }
  function t(key, values = {}) {
    const message = dictionaries[language]?.[key] ?? dictionaries['zh-CN']?.[key] ?? key;
    return message.replace(/\{(\w+)\}/g, (match, name) => values[name] ?? match);
  }
  function error(message) {
    const text = String(message);
    const key = Object.keys(dictionaries['zh-CN'] || {}).find(key => key.startsWith('error.server.') && (dictionaries['zh-CN'][key] === text || dictionaries.en?.[key] === text));
    if (key) return t(key);
    // Third-party diagnostic text has no stable error code. Preserve it verbatim.
    return language === 'en' && /\p{Script=Han}/u.test(text) ? t('error.source', {message: text}) : text;
  }
  function apply() {
    document.documentElement.lang = language;
    document.title = t('app.title');
    for (const node of document.querySelectorAll('[data-i18n]')) node.textContent = t(node.dataset.i18n);
    for (const name of ['placeholder', 'aria-label']) {
      for (const node of document.querySelectorAll('[data-i18n-' + name + ']')) node.setAttribute(name, t(node.getAttribute('data-i18n-' + name)));
    }
    document.querySelector('#language').value = language;
  }
  async function init() {
    await Promise.all(supported.map(async lang => {
      const response = await fetch('/static/locales/' + lang + '.json', {cache:'no-store'});
      if (!response.ok) throw new Error('Could not load language: ' + lang);
      dictionaries[lang] = await response.json();
    }));
    language = preferred();
    apply();
  }
  function setLanguage(next) {
    if (!supported.includes(next)) return;
    language = next;
    try { localStorage.setItem('zhenxia.language', next); } catch (_) {}
    apply();
    window.dispatchEvent(new Event('languagechange'));
  }
  return {init, t, error, setLanguage, get language() { return language; }};
})();
