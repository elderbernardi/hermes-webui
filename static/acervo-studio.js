/* MOD-010 Acervo Studio — self-contained full-screen surface. Read-only Phase 0.
   No ES import/export (sourceType:"script"); reuses app globals S/api/esc/showToast/
   renderMd/humanizeFilename. Prefix: acervoStudio* / AXS / .axs-*. */
'use strict';
(function () {
  var AXS = { built: false, open: false, scope: 'micro', slug: '', selectedPath: '' };

  function _sid() { return (typeof S !== 'undefined' && S && S.session) ? S.session.session_id : ''; }
  function _esc(s) { return (typeof esc === 'function') ? esc(s) : String(s == null ? '' : s); }
  function _toast(m, t) { if (typeof showToast === 'function') showToast(m, t); }
  function _root() { return document.getElementById('acervoStudioRoot'); }

  function _build() {
    if (AXS.built) return;
    var root = _root();
    if (!root) return;
    // Reparent to <body>: aside.rightpanel carries a CSS transform that traps
    // position:fixed (the MOD-009 lesson).
    if (root.parentElement !== document.body) document.body.appendChild(root);
    root.className = 'axs-root';
    root.innerHTML =
      '<div class="axs-top">' +
      '  <div class="axs-mode">' +
      '    <button type="button" data-axs="chat">Chat</button>' +
      '    <button type="button" class="on" data-axs="acervo">Acervo</button>' +
      '  </div>' +
      '  <div class="axs-cmd"><input type="search" data-axs="q" ' +
      '     placeholder="Perguntar ou buscar no acervo…" aria-label="Buscar"></div>' +
      '</div>' +
      '<div class="axs-body">' +
      '  <nav class="axs-nav" data-axs="nav" aria-label="Acervo"></nav>' +
      '  <section class="axs-reader" data-axs="reader"></section>' +
      '</div>';
    root.querySelector('[data-axs="chat"]').addEventListener('click', _close);
    var qi = root.querySelector('[data-axs="q"]');
    if (qi) qi.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') acervoStudioSearch(qi.value);
    });
    AXS.built = true;
  }

  function _open() {
    _build();
    var root = _root();
    root.hidden = false;
    AXS.open = true;
    _showLauncher(false);
    if (typeof acervoStudioRenderNav === 'function') acervoStudioRenderNav();
  }
  function _close() {
    var root = _root();
    if (root) root.hidden = true;
    AXS.open = false;
    _showLauncher(true);
  }

  function _ensureLauncher() {
    if (document.getElementById('axsLauncher')) return;
    var b = document.createElement('button');
    b.id = 'axsLauncher';
    b.className = 'axs-launcher';
    b.type = 'button';
    b.title = 'Abrir o Acervo';
    b.innerHTML = '<span>▤</span><span>Acervo</span>';
    b.addEventListener('click', acervoStudioToggle);
    document.body.appendChild(b);
  }
  function _showLauncher(show) {
    var b = document.getElementById('axsLauncher');
    if (b) b.style.display = show ? '' : 'none';
  }

  var SCOPES = [
    { key: 'macro', ico: '🧠', label: 'Soul', tree: true },
    { key: 'global', ico: '🌐', label: 'Global', tree: true },
    { key: 'shared', ico: '🔗', label: 'Shared', tree: true },
    { key: 'micro', ico: '🪐', label: 'Microversos', tree: true },
    { key: 'artifacts', ico: '📦', label: 'Artefatos', tree: true },
    { key: 'inbox', ico: '📥', label: 'Inbox', tree: true }
  ];

  async function _tree(scope, slug) {
    var url = '/api/acervo/x/tree?session_id=' + encodeURIComponent(_sid()) +
      '&scope=' + encodeURIComponent(scope) + '&depth=2' +
      (slug ? '&slug=' + encodeURIComponent(slug) : '');
    return await api(url);
  }

  function _human(rel) {
    return (typeof humanizeFilename === 'function') ? humanizeFilename(rel) : String(rel || '');
  }

  async function acervoStudioRenderNav() {
    var nav = _root() && _root().querySelector('[data-axs="nav"]');
    if (!nav) return;
    if (!_sid()) { nav.innerHTML = '<div class="axs-empty">Sem sessão ativa.</div>'; return; }
    var html = '<div class="axs-sec">Acervo</div>';
    // Inbox count badge (best-effort).
    var inboxCount = 0;
    try { inboxCount = (await _tree('inbox', '')).count || 0; } catch (e) {}
    SCOPES.forEach(function (s) {
      var on = AXS.scope === s.key ? ' on' : '';
      var badge = (s.key === 'inbox' && inboxCount) ?
        '<span class="ct">' + inboxCount + '</span>' : '';
      html += '<div class="axs-ni' + on + '" data-scope="' + s.key + '">' +
        '<span class="ico">' + s.ico + '</span>' + _esc(s.label) + badge + '</div>' +
        '<div class="axs-sub" data-sub="' + s.key + '"></div>';
    });
    nav.innerHTML = html;
    nav.querySelectorAll('.axs-ni').forEach(function (el) {
      el.addEventListener('click', function () {
        acervoStudioSelectScope(el.getAttribute('data-scope'), '');
      });
    });
    if (AXS.scope) acervoStudioSelectScope(AXS.scope, AXS.slug);
  }

  async function acervoStudioSelectScope(scope, slug) {
    AXS.scope = scope; AXS.slug = slug || '';
    var nav = _root().querySelector('[data-axs="nav"]');
    nav.querySelectorAll('.axs-ni').forEach(function (el) {
      el.classList.toggle('on', el.getAttribute('data-scope') === scope);
    });
    var sub = nav.querySelector('[data-sub="' + scope + '"]');
    nav.querySelectorAll('.axs-sub').forEach(function (s) { if (s !== sub) s.innerHTML = ''; });
    if (!sub) return;
    sub.innerHTML = '<div class="axs-empty">Carregando…</div>';
    var data;
    try { data = await _tree(scope, slug); }
    catch (e) { sub.innerHTML = '<div class="axs-empty">Erro ao carregar.</div>'; return; }
    var nodes = data.nodes || [];
    if (!nodes.length) { sub.innerHTML = '<div class="axs-empty">Vazio.</div>'; return; }
    var out = '';
    nodes.forEach(function (n) {
      if (n.type === 'microverse') {
        out += '<div class="axs-pi" data-mv="' + _esc(n.slug) + '">🪐 ' +
          _esc(n.title) + (n.count ? ' (' + n.count + ')' : '') + '</div>';
      } else if (n.type === 'page') {
        var st = n.status === 'ready' ? ' ready' : '';
        out += '<div class="axs-pi" data-path="' + _esc(n.rel_path) + '">' +
          '<span class="st' + st + '"></span>' + _esc(n.title || _human(n.rel_path)) + '</div>';
      } else if (n.type === 'nature') {
        out += '<div class="axs-sec" style="margin-left:18px">' + _esc(n.name) +
          ' (' + (n.count || 0) + ')</div>';
      } else if (n.type === 'intake') {
        out += '<div class="axs-pi"><span class="st"></span>' + _esc(n.title) +
          ' · ' + _esc(n.status) + '</div>';
      } else if (n.type === 'artifact') {
        out += '<div class="axs-pi">📦 ' + _esc(n.title || n.name) + '</div>';
      }
    });
    sub.innerHTML = out;
    sub.querySelectorAll('[data-mv]').forEach(function (el) {
      el.addEventListener('click', function () {
        acervoStudioSelectScope('micro', el.getAttribute('data-mv'));
      });
    });
    sub.querySelectorAll('[data-path]').forEach(function (el) {
      el.addEventListener('click', function () {
        if (typeof acervoStudioOpenPage === 'function')
          acervoStudioOpenPage(el.getAttribute('data-path'));
      });
    });
  }
  window.acervoStudioRenderNav = acervoStudioRenderNav;
  window.acervoStudioSelectScope = acervoStudioSelectScope;

  function _chip(label, cls) { return '<span class="' + (cls || '') + '">' + _esc(label) + '</span>'; }

  // If the body's first non-empty line is a top-level "# Heading" matching the page
  // title, drop that one line (title is already shown separately as .axs-title).
  function _stripDupTitleH1(body, title) {
    if (!body) return body || '';
    var t = String(title || '').trim().toLowerCase();
    if (!t) return body;
    var m = body.match(/^\s*#\s+(.+?)[ \t]*(\r?\n|$)/);
    if (m && m[1].trim().toLowerCase() === t) {
      return body.slice(m[0].length).replace(/^\r?\n/, '');
    }
    return body;
  }

  async function acervoStudioOpenPage(relPath) {
    AXS.selectedPath = relPath;
    var reader = _root().querySelector('[data-axs="reader"]');
    // Mark the active page in the nav — runs for both md and non-md branches.
    var nav = _root() && _root().querySelector('[data-axs="nav"]');
    if (nav) {
      nav.querySelectorAll('.axs-pi').forEach(function (el) {
        el.classList.toggle('on', el.getAttribute('data-path') === relPath);
      });
    }
    reader.innerHTML = '<div class="axs-reader-empty">Carregando…</div>';
    var p;
    try {
      p = await api('/api/acervo/x/page?session_id=' + encodeURIComponent(_sid()) +
        '&path=' + encodeURIComponent(relPath));
    } catch (e) {
      reader.innerHTML = '<div class="axs-reader-empty">Erro ao abrir a página.</div>';
      return;
    }
    var crumb = relPath.split('/').map(function (s, i, a) {
      return i === a.length - 1 ? _esc(s) : '<b>' + _esc(s) + '</b>';
    }).join(' › ');
    if (p && p.editable === false && p.raw_url) {
      var rawUrl = p.raw_url + '&session_id=' + encodeURIComponent(_sid());
      var isImg = (p.mime || '').indexOf('image/') === 0;
      var view = isImg
        ? '<img class="axs-raw" src="' + _esc(rawUrl) + '" alt="' + _esc(relPath) + '">'
        : '<iframe class="axs-raw" src="' + _esc(rawUrl) + '" sandbox></iframe>';
      reader.innerHTML = '<div class="axs-crumb">' + crumb + '</div><div class="axs-doc">' + view + '</div>';
      return;
    }
    var fm = (p && p.frontmatter) || {};
    var chips = '';
    if (fm.nature) chips += _chip(fm.nature);
    if (fm['class']) chips += _chip('🔒 ' + fm['class'],
      String(fm['class']).indexOf('peren') === 0 ? 'perene' : '');
    if (fm.status) chips += _chip('✓ ' + fm.status);
    (Array.isArray(fm.tags) ? fm.tags : []).forEach(function (t) { chips += _chip('#' + t); });
    var title = p.title || relPath;
    var body = _stripDupTitleH1(p.body || '', title);
    var bodyHtml = (typeof renderMd === 'function') ? renderMd(body) : _esc(body);
    reader.innerHTML =
      '<div class="axs-crumb">' + crumb + '</div>' +
      '<div class="axs-doc">' +
      '  <div class="axs-fm">' + chips + '</div>' +
      '  <h1 class="axs-title">' + _esc(title) + '</h1>' +
      '  <div class="axs-md">' + bodyHtml + '</div>' +
      '</div>';
  }
  window.acervoStudioOpenPage = acervoStudioOpenPage;

  async function acervoStudioSearch(q) {
    q = (q || '').trim();
    var reader = _root().querySelector('[data-axs="reader"]');
    if (!q) { reader.innerHTML = '<div class="axs-reader-empty">Digite um termo.</div>'; return; }
    reader.innerHTML = '<div class="axs-reader-empty">Buscando…</div>';
    var d;
    try {
      d = await api('/api/acervo/x/search?session_id=' + encodeURIComponent(_sid()) +
        '&q=' + encodeURIComponent(q));
    } catch (e) { reader.innerHTML = '<div class="axs-reader-empty">Erro na busca.</div>'; return; }
    var res = (d && d.results) || [];
    if (!res.length) { reader.innerHTML = '<div class="axs-reader-empty">Nada encontrado.</div>'; return; }
    var html = '<div class="axs-results">';
    res.forEach(function (r) {
      html += '<button type="button" class="axs-rescard" data-path="' + _esc(r.rel_path) + '">' +
        '<div class="rt">' + _esc(r.title) + '</div>' +
        '<div class="rm">' + _esc(r.nature || '') + (r.status ? ' · ' + _esc(r.status) : '') +
        (r.snippet ? ' — ' + _esc(r.snippet) : '') + '</div></button>';
    });
    html += (d.truncated ? '<div class="axs-empty">Resultados truncados.</div>' : '') + '</div>';
    reader.innerHTML = html;
    reader.querySelectorAll('.axs-rescard').forEach(function (el) {
      el.addEventListener('click', function () { acervoStudioOpenPage(el.getAttribute('data-path')); });
    });
  }
  window.acervoStudioSearch = acervoStudioSearch;

  function acervoStudioToggle() { if (AXS.open) _close(); else _open(); }
  window.acervoStudioToggle = acervoStudioToggle;

  // Expose module internals to later-task render functions in this IIFE.
  window.__AXS = { state: AXS, sid: _sid, esc: _esc, toast: _toast, root: _root };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _ensureLauncher);
  } else {
    _ensureLauncher();
  }
})();
