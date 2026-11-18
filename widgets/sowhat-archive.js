(() => {
  'use strict';
  const root = document.getElementById('sowhat-archive');
  if (!root || root.dataset.ready) return;
  const dataNode = root.querySelector('[data-swa-seed]');
  const grid = root.querySelector('[data-swa-grid]');
  const search = root.querySelector('[data-swa-search]');
  const month = root.querySelector('[data-swa-month]');
  const more = root.querySelector('[data-swa-more]');
  const count = root.querySelector('[data-swa-count]');
  const empty = root.querySelector('[data-swa-empty]');
  const months = root.querySelector('[data-swa-months]');
  const structured = root.querySelector('[data-swa-structured]');
  const imageHosts = new Set(['img.stibee.com', 'img2.stibee.com', 'cdn.stibee.com', 'resource.stibee.com', 'cdn.imweb.me']);
  let limit = 9;
  let currentSignature = '';
  let refreshing = false;
  let lastRefresh = 0;

  function normalize(raw) {
    if (!Array.isArray(raw)) return [];
    const seen = new Set();
    return raw.filter(x => x && typeof x.id === 'string' && typeof x.title === 'string' && x.title.trim() && /^\d{4}-\d{2}-\d{2}$/.test(x.date) && /^https:\/\/stib\.ee\/[A-Za-z0-9_-]+$/.test(x.url)).map(x => {
      let image = '';
      try { const u = new URL(x.image); if (u.protocol === 'https:' && imageHosts.has(u.hostname)) image = u.href; } catch (_) {}
      return {id: x.id, title: x.title, date: x.date, url: x.url, image, volume: Number.isInteger(x.volume) && x.volume > 0 ? x.volume : null};
    }).filter(x => { if (seen.has(x.id)) return false; seen.add(x.id); return true; }).sort((a, b) => b.date.localeCompare(a.date));
  }
  let dataset;
  try { dataset = normalize(JSON.parse(dataNode.textContent)); } catch (_) { return; }
  if (!dataset.length) return;
  root.dataset.ready = 'true';
  root.querySelector('[data-swa-tools]').removeAttribute('aria-hidden');
  root.querySelector('[data-swa-tools]').removeAttribute('inert');
  root.querySelector('[data-swa-bottom]').hidden = false;

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }
  function rebuildMonths() {
    const selected = month.value;
    const counts = new Map();
    dataset.forEach(x => counts.set(x.date.slice(0, 7), (counts.get(x.date.slice(0, 7)) || 0) + 1));
    month.replaceChildren(new Option('전체 발행월', ''));
    counts.forEach((value, key) => month.add(new Option(key.slice(0, 4) + '년 ' + Number(key.slice(5)) + '월', key)));
    month.value = counts.has(selected) ? selected : '';
    months.replaceChildren();
    [['', dataset.length], ...Array.from(counts.entries()).slice(0, 3)].forEach(([key, value]) => {
      const button = element('button', 'swa-month-link');
      button.type = 'button';
      button.dataset.month = key;
      button.append(document.createTextNode(key ? key.slice(0, 4) + '년 ' + Number(key.slice(5)) + '월' : '전체 뉴스레터'), element('span', '', String(value)));
      button.addEventListener('click', () => { month.value = key; limit = 9; render(); });
      months.append(button);
    });
    if (structured) structured.textContent = JSON.stringify({'@context':'https://schema.org','@type':'CollectionPage',name:'쏘왓레터 모아보기',url:'https://bestexit.co.kr/sowhat-archives',mainEntity:{'@type':'ItemList',numberOfItems:dataset.length,itemListElement:dataset.map((x,i)=>({'@type':'ListItem',position:i+1,name:x.title,url:x.url}))}});
  }
  function card(x, index) {
    const article = element('article', 'swa-card');
    const anchor = element('a');
    anchor.href = x.url;
    anchor.target = '_blank';
    anchor.rel = 'noopener';
    anchor.setAttribute('aria-label', x.title + ' — 스티비 원문 새 창');
    const cover = element('div', 'swa-cover');
    cover.append(element('span', 'swa-cover-fallback', 'SO WHAT?'));
    if (x.image) {
      const image = element('img');
      image.src = x.image;
      image.alt = x.title;
      image.width = 630;
      image.height = 360;
      image.loading = index < 3 ? 'eager' : 'lazy';
      image.decoding = 'async';
      image.addEventListener('error', () => { image.remove(); cover.classList.add('swa-no-image'); }, {once:true});
      cover.append(image);
    } else cover.classList.add('swa-no-image');
    if (x.id === dataset[0].id) cover.append(element('span', 'swa-latest', 'LATEST'));
    const meta = element('p', 'swa-meta');
    const date = element('time', '', x.date.replace(/-/g, '.'));
    date.dateTime = x.date;
    meta.append(element('span', 'swa-volume', x.volume ? 'Vol. ' + String(x.volume).padStart(3, '0') : 'SO WHAT LETTER'), element('i', '', '·'), date);
    anchor.append(cover, meta, element('h2', '', x.title));
    article.append(anchor);
    return article;
  }
  function render() {
    const query = search.value.trim().toLocaleLowerCase();
    const items = dataset.filter(x => (!query || (x.title + ' ' + (x.volume || '')).toLocaleLowerCase().includes(query)) && (!month.value || x.date.startsWith(month.value)));
    const fragment = document.createDocumentFragment();
    items.slice(0, limit).forEach((x, i) => fragment.append(card(x, i)));
    grid.replaceChildren(fragment);
    count.textContent = items.length + '개';
    more.hidden = items.length <= limit;
    empty.hidden = items.length !== 0;
    root.querySelector('[data-swa-shown]').textContent = (query || month.value ? '검색 결과 ' + items.length : '전체 ' + dataset.length) + '개 중 ' + Math.min(limit, items.length) + '개';
    months.querySelectorAll('button').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.month === month.value)));
  }
  search.addEventListener('input', () => { limit = 9; render(); });
  month.addEventListener('change', () => { limit = 9; render(); });
  more.addEventListener('click', () => { limit += 9; render(); });
  rebuildMonths();
  render();
  currentSignature = JSON.stringify(dataset);

  async function refresh() {
    if (refreshing || Date.now() - lastRefresh < 5 * 60 * 1000) return;
    refreshing = true;
    const bucket = Math.floor(Date.now() / 300000);
    const endpoints = ['https://junggiteam.github.io/naver-news/data/sowhat_archive.json', 'https://raw.githubusercontent.com/junggiteam/naver-news/main/data/sowhat_archive.json'];
    try {
      for (const endpoint of endpoints) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 12000);
        try {
          const response = await fetch(endpoint + '?v=' + bucket, {signal:controller.signal, credentials:'omit'});
          if (!response.ok) throw new Error('Archive unavailable');
          const payload = await response.json();
          const updated = payload.schemaVersion === 1 && payload.source === 'https://page.stibee.com/archives/479387' ? normalize(payload.items) : [];
          if (!updated.length || updated.length < dataset.length * .75) throw new Error('Invalid archive response');
          const signature = JSON.stringify(updated);
          if (signature !== currentSignature) {
            dataset = updated;
            currentSignature = signature;
            rebuildMonths();
            render();
          }
          root.dataset.feedUpdatedAt = payload.updatedAt;
          root.dataset.feedSource = endpoint;
          lastRefresh = Date.now();
          return;
        } catch (_) { /* Keep the server-delivered archive and try the next source. */ }
        finally { clearTimeout(timer); }
      }
    } finally { refreshing = false; }
  }
  refresh();
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  const poll = setInterval(() => { if (!root.isConnected) clearInterval(poll); else if (!document.hidden) refresh(); }, 5 * 60 * 1000);
})();
