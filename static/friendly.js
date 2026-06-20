/* friendly.js — human display-name resolver (MOD-008).
 * Turns raw paths/slugs/timestamps into readable labels for the Sessão and Acervo
 * views. Pure display layer — never renames files on disk. Depends only on the
 * globals S and api(). Priority: manifest friendly_name/title → cached frontmatter
 * title (via /api/acervo/titles) → humanized filename. */

const _friendlyTitleCache = {};   // workspace-relative path -> title | null

function _friendlyKey(p){
  let s = String(p || '').replace(/^~\//, '').replace(/^\.\/+/, '');
  const ws = S && S.session && S.session.workspace;
  if(ws){
    const n = ws.replace(/\/+$/, '') + '/';
    if(s.startsWith(n)) s = s.slice(n.length);
  }
  return s.replace(/^\/+/, '');
}

function humanizeFilename(name){
  const base = String(name || '').replace(/^.*\//, '');
  let s = base.replace(/\.[^.]+$/, '');
  s = s
    .replace(/^(art|draft)[-_]/i, '')                      // strip ID-ish prefixes FIRST
    .replace(/[_-]?\d{8}[_-]\d{6}/g, '')                   // compact 20260606_055603
    .replace(/[_-]?\d{4}-\d{2}-\d{2}([_-]\d{2,6})?/g, '')  // ISO date / date-time
    .replace(/[-_]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if(!s) return base;
  return s.split(' ').map(w => {
    if(!w) return w;
    if(w === w.toUpperCase()) return w;   // ALLCAPS token (EX, MOD)
    if(/\d/.test(w)) return w;            // has digit (ex22, v2, q2)
    return w[0].toUpperCase() + w.slice(1);
  }).join(' ');
}

function friendlyName(item){
  if(item && typeof item === 'object'){
    if(item.friendly_name) return item.friendly_name;
    if(item.title) return item.title;
    const p = item.path || item.rel_path || item.name || '';
    const cached = _friendlyTitleCache[_friendlyKey(p)];
    return cached || humanizeFilename(p);
  }
  const p = String(item || '');
  const cached = _friendlyTitleCache[_friendlyKey(p)];
  return cached || humanizeFilename(p);
}

// Batch-fetch frontmatter titles for the .md paths about to be rendered, then run
// onReady() so the caller can re-render with resolved titles. Only fetches paths
// not already cached; non-.md paths are skipped (fall straight to humanized name).
async function prefetchTitles(paths, onReady){
  if(!S || !S.session){ if(onReady) onReady(); return; }
  const want = [];
  for(const p of (paths || [])){
    const k = _friendlyKey(p);
    if(!k || !k.toLowerCase().endsWith('.md')) continue;
    if(k in _friendlyTitleCache) continue;
    if(want.indexOf(k) === -1) want.push(k);
  }
  if(!want.length){ if(onReady) onReady(); return; }
  try{
    const data = await api('/api/acervo/titles?session_id=' + encodeURIComponent(S.session.session_id) +
      '&paths=' + encodeURIComponent(want.join(',')));
    const titles = (data && data.titles) || {};
    for(const k of want) _friendlyTitleCache[k] = titles[k] || null;
  }catch(e){
    for(const k of want){ if(!(k in _friendlyTitleCache)) _friendlyTitleCache[k] = null; }
  }
  if(onReady) onReady();
}
