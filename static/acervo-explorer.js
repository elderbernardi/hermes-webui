/* Acervo Explorer — MOD-009 (EXCRTX fork). Premium semantic file-explorer for the
 * Exocórtex acervo: a right-side docked, resizable panel that browses macro / global /
 * micro / shared / artefatos, previews + edits pages (body + frontmatter), moves/renames,
 * sets status/tags, stages a page into the chat composer, and searches by facet.
 *
 * Self-contained / rebase-safe: lives entirely in this NEW file (+ acervo-explorer.css).
 * IIFE-scoped, sourceType:"script" — NO ES import/export. Reuses verified globals only:
 *   renderMd (ui.js), renderKatexBlocks (ui.js, optional), S / api / $ / esc / showToast /
 *   showConfirmDialog (workspace.js + ui.js), humanizeFilename (friendly.js),
 *   renderStagedContextChips (ui.js, optional).
 *
 * Backend contract: GET/POST /api/acervo/x/{tree,page,search,save,move,status,tags,stage}
 * (SPEC §3) plus the existing GET /api/acervo/{microverses,knowledge} for the micro scope.
 */
(function () {
  'use strict';

  var LS_KEY = 'hermes-webui-acervo-explorer';
  var DEFAULT_WIDTH = 380;
  var MIN_WIDTH = 300;

  // ----------------------------- state (SPEC §7) -----------------------------
  var AX = {
    open: false,
    width: DEFAULT_WIDTH,
    widthClass: 'ax-mid',
    built: false,
    scope: 'global',          // global | shared | macro | micro | artifacts
    slug: '',                 // microverso slug (micro scope) or macro slug
    nature: '',               // selected nature inside the tree
    treeNodes: [],            // current tree response nodes
    treeExpanded: {},         // key -> bool, expanded nature nodes
    cards: [],                // pages under the selected nature/scope
    selectedPath: '',
    page: null,               // {rel_path, frontmatter, body, ...}
    editing: false,
    dirty: false,
    loadingTree: false,
    loadingCards: false,
    loadingPage: false,
    search: { q: '', nature: '', status: '', microverso: '', tag: '', results: null, truncated: false, active: false },
    microverses: null,        // cached [{slug,name,description,natures}]
    ro: null,
  };

  // Bilingual labels — mirror acervo.js _acL (pt default, en fallback).
  function _axL(pt, en) {
    var lang = (document.documentElement.lang || 'pt').slice(0, 2);
    return lang === 'en' ? en : pt;
  }

  var SCOPES = [
    { key: 'macro', label: function () { return _axL('Macro', 'Macro'); }, tree: true },
    { key: 'global', label: function () { return _axL('Global', 'Global'); }, tree: true },
    { key: 'micro', label: function () { return _axL('Microversos', 'Microverses'); }, tree: false },
    { key: 'shared', label: function () { return _axL('Compartilhado', 'Shared'); }, tree: true },
    { key: 'artifacts', label: function () { return _axL('Artefatos', 'Artifacts'); }, tree: true },
  ];

  var NATURE_LABELS = {
    context: function () { return _axL('Contexto', 'Context'); },
    knowledge: function () { return _axL('Conhecimento', 'Knowledge'); },
    contracts: function () { return _axL('Contratos', 'Contracts'); },
    workflows: function () { return 'Workflows'; },
    decisions: function () { return _axL('Decisões', 'Decisions'); },
    templates: function () { return 'Templates'; },
    tools: function () { return _axL('Ferramentas', 'Tools'); },
    skills: function () { return 'Skills'; },
    persona: function () { return 'Persona'; },
    prompts: function () { return 'Prompts'; },
    reflections: function () { return _axL('Reflexões', 'Reflections'); },
  };
  var ALL_NATURES = ['context', 'knowledge', 'contracts', 'workflows', 'decisions',
    'templates', 'tools', 'skills', 'persona', 'prompts', 'reflections'];

  function _natureLabel(n) {
    var f = NATURE_LABELS[n];
    if (f) return f();
    return n ? n[0].toUpperCase() + n.slice(1) : n;
  }

  // status -> {label,color}. UI-writable set is draft/ready/archived; others read-only.
  var STATUS_META = {
    draft: { color: '#6c6770', label: function () { return _axL('Rascunho', 'Draft'); } },
    ready: { color: '#1376ed', label: function () { return _axL('Pronto', 'Ready'); } },
    archived: { color: '#78747e', label: function () { return _axL('Arquivado', 'Archived'); } },
    approved: { color: '#0ea5e9', label: function () { return _axL('Aprovado', 'Approved'); } },
    published: { color: '#22c55e', label: function () { return _axL('Publicado', 'Published'); } },
    pending: { color: '#f59e0b', label: function () { return _axL('Pendente', 'Pending'); } },
  };
  var UI_STATUSES = ['draft', 'ready', 'archived'];
  function _statusMeta(s) { return STATUS_META[s] || { color: '#6c6770', label: function () { return s || '—'; } }; }

  // ----------------------------- helpers -----------------------------
  function _sid() { return (typeof S !== 'undefined' && S && S.session) ? S.session.session_id : ''; }
  function _hasSession() { return !!_sid(); }
  function _esc(s) { return (typeof esc === 'function') ? esc(s) : String(s == null ? '' : s); }
  function _toast(msg, ms, type) { if (typeof showToast === 'function') showToast(msg, ms, type); }
  function _human(rel) { return (typeof humanizeFilename === 'function') ? humanizeFilename(rel) : String(rel || ''); }
  function _label(node) { return (node && node.title) || _human(node && (node.rel_path || node.name) || ''); }

  function _persist() {
    try { localStorage.setItem(LS_KEY, JSON.stringify({ open: AX.open, width: AX.width })); } catch (_) { /* ignore */ }
  }
  function _restore() {
    try {
      var raw = localStorage.getItem(LS_KEY);
      if (!raw) return;
      var d = JSON.parse(raw);
      if (d && typeof d.width === 'number') AX.width = Math.max(MIN_WIDTH, Math.min(d.width, _maxWidth()));
    } catch (_) { /* ignore */ }
  }
  function _maxWidth() { return Math.round(window.innerWidth * 0.7); }

  function _q(sel) { return AX.root ? AX.root.querySelector(sel) : null; }

  // ----------------------------- panel shell (T8) -----------------------------
  function _build() {
    var mount = (typeof $ === 'function') ? $('acervoExplorerRoot') : document.getElementById('acervoExplorerRoot');
    if (!mount) return null;
    AX.root = mount;
    mount.classList.add('ax-root');
    mount.setAttribute('role', 'dialog');
    mount.setAttribute('aria-modal', 'false');
    mount.setAttribute('aria-label', _axL('Explorador do Acervo', 'Acervo Explorer'));
    mount.hidden = false; // CSS controls visibility via .open; keep in DOM flow
    mount.style.width = AX.width + 'px';

    mount.innerHTML =
      '<div class="ax-resizer" role="separator" aria-orientation="vertical" aria-label="' + _esc(_axL('Redimensionar', 'Resize')) + '" tabindex="0"></div>' +
      '<div class="ax-shell">' +
      '  <header class="ax-header">' +
      '    <div class="ax-title">' + _esc(_axL('Acervo', 'Acervo')) + '</div>' +
      '    <div class="ax-header-actions">' +
      '      <button type="button" class="ax-icon-btn" data-ax="refresh" title="' + _esc(_axL('Atualizar', 'Refresh')) + '" aria-label="' + _esc(_axL('Atualizar', 'Refresh')) + '">⟳</button>' +
      '      <button type="button" class="ax-icon-btn" data-ax="expand" title="' + _esc(_axL('Expandir', 'Expand')) + '" aria-label="' + _esc(_axL('Expandir', 'Expand')) + '">⤢</button>' +
      '      <button type="button" class="ax-icon-btn" data-ax="close" title="' + _esc(_axL('Fechar', 'Close')) + '" aria-label="' + _esc(_axL('Fechar', 'Close')) + '">✕</button>' +
      '    </div>' +
      '  </header>' +
      '  <div class="ax-searchbar">' +
      '    <input type="search" class="ax-search-input" data-ax="q" placeholder="' + _esc(_axL('Buscar no acervo…', 'Search the acervo…')) + '" aria-label="' + _esc(_axL('Buscar', 'Search')) + '">' +
      '    <button type="button" class="ax-icon-btn" data-ax="facets-toggle" title="' + _esc(_axL('Filtros', 'Facets')) + '" aria-label="' + _esc(_axL('Filtros', 'Facets')) + '">⚙</button>' +
      '  </div>' +
      '  <div class="ax-facets" data-ax="facets" hidden></div>' +
      '  <nav class="ax-scopes" role="tablist" aria-label="' + _esc(_axL('Escopos', 'Scopes')) + '"></nav>' +
      '  <div class="ax-breadcrumb" data-ax="crumb" aria-live="polite"></div>' +
      '  <div class="ax-body">' +
      '    <div class="ax-pane ax-pane-tree" data-ax="tree" role="tree" aria-label="' + _esc(_axL('Árvore', 'Tree')) + '"></div>' +
      '    <div class="ax-pane ax-pane-cards" data-ax="cards" aria-label="' + _esc(_axL('Páginas', 'Pages')) + '"></div>' +
      '    <div class="ax-pane ax-pane-preview" data-ax="preview" aria-label="' + _esc(_axL('Pré-visualização', 'Preview')) + '"></div>' +
      '  </div>' +
      '</div>';

    _renderScopes();
    _renderFacets();
    _wireShell();
    _wireResizer();
    _observe();
    AX.built = true;
    return mount;
  }

  function _renderScopes() {
    var nav = _q('.ax-scopes');
    if (!nav) return;
    nav.innerHTML = SCOPES.map(function (s) {
      var on = AX.scope === s.key;
      return '<button type="button" role="tab" class="ax-scope' + (on ? ' active' : '') + '"' +
        ' aria-selected="' + (on ? 'true' : 'false') + '" data-scope="' + _esc(s.key) + '">' +
        _esc(s.label()) + '</button>';
    }).join('');
  }

  function _renderFacets() {
    var host = _q('[data-ax="facets"]');
    if (!host) return;
    function opts(list, sel, anyLabel) {
      var o = '<option value="">' + _esc(anyLabel) + '</option>';
      o += list.map(function (v) {
        var lbl = (typeof v === 'object') ? v.label : v;
        var val = (typeof v === 'object') ? v.value : v;
        return '<option value="' + _esc(val) + '"' + (sel === val ? ' selected' : '') + '>' + _esc(lbl) + '</option>';
      }).join('');
      return o;
    }
    var natOpts = ALL_NATURES.map(function (n) { return { value: n, label: _natureLabel(n) }; });
    var statOpts = UI_STATUSES.map(function (s) { return { value: s, label: _statusMeta(s).label() }; });
    var mvOpts = (AX.microverses || []).map(function (m) { return { value: m.slug, label: m.name || m.slug }; });
    host.innerHTML =
      '<label class="ax-facet"><span>' + _esc(_axL('Natureza', 'Nature')) + '</span>' +
      '<select data-ax="f-nature">' + opts(natOpts, AX.search.nature, _axL('Todas', 'All')) + '</select></label>' +
      '<label class="ax-facet"><span>' + _esc(_axL('Status', 'Status')) + '</span>' +
      '<select data-ax="f-status">' + opts(statOpts, AX.search.status, _axL('Todos', 'All')) + '</select></label>' +
      '<label class="ax-facet"><span>' + _esc(_axL('Microverso', 'Microverse')) + '</span>' +
      '<select data-ax="f-micro">' + opts(mvOpts, AX.search.microverso, _axL('Todos', 'All')) + '</select></label>' +
      '<label class="ax-facet"><span>' + _esc(_axL('Tag', 'Tag')) + '</span>' +
      '<input type="text" data-ax="f-tag" value="' + _esc(AX.search.tag) + '" placeholder="tag"></label>';
  }

  function _wireShell() {
    AX.root.addEventListener('click', function (ev) {
      var t = ev.target.closest('[data-ax],[data-scope]');
      if (!t || !AX.root.contains(t)) return;
      var scope = t.getAttribute('data-scope');
      if (scope) { _selectScope(scope); return; }
      var ax = t.getAttribute('data-ax');
      if (ax === 'close') { _close(); }
      else if (ax === 'refresh') { _reloadCurrent(true); }
      else if (ax === 'expand') { _cycleWidth(); }
      else if (ax === 'facets-toggle') { _toggleFacets(); }
    });

    var input = _q('[data-ax="q"]');
    if (input) {
      var deb;
      input.addEventListener('input', function () {
        AX.search.q = input.value;
        clearTimeout(deb);
        deb = setTimeout(_runSearch, 280);
      });
      input.addEventListener('keydown', function (e) { if (e.key === 'Enter') { clearTimeout(deb); _runSearch(); } });
    }
    var facets = _q('[data-ax="facets"]');
    if (facets) {
      facets.addEventListener('change', function () {
        AX.search.nature = (_q('[data-ax="f-nature"]') || {}).value || '';
        AX.search.status = (_q('[data-ax="f-status"]') || {}).value || '';
        AX.search.microverso = (_q('[data-ax="f-micro"]') || {}).value || '';
        _runSearch();
      });
      facets.addEventListener('input', function (e) {
        if (e.target && e.target.getAttribute('data-ax') === 'f-tag') {
          AX.search.tag = e.target.value;
        }
      });
    }
  }

  function _toggleFacets() {
    var f = _q('[data-ax="facets"]');
    if (f) f.hidden = !f.hidden;
  }

  // ----------------------------- resize (T8) -----------------------------
  function _wireResizer() {
    var handle = _q('.ax-resizer');
    if (!handle) return;
    var dragging = false;
    function onMove(clientX) {
      if (!dragging) return;
      var fromRight = window.innerWidth - clientX;
      var w = Math.max(MIN_WIDTH, Math.min(fromRight, _maxWidth()));
      AX.width = w;
      AX.root.style.width = w + 'px';
    }
    function start(ev) {
      dragging = true;
      AX.root.classList.add('ax-resizing');
      ev.preventDefault();
    }
    function end() {
      if (!dragging) return;
      dragging = false;
      AX.root.classList.remove('ax-resizing');
      _persist();
    }
    handle.addEventListener('pointerdown', function (e) { start(e); try { handle.setPointerCapture(e.pointerId); } catch (_) {} });
    handle.addEventListener('pointermove', function (e) { onMove(e.clientX); });
    handle.addEventListener('pointerup', end);
    handle.addEventListener('pointercancel', end);
    // Mouse fallback (in case pointer events unsupported).
    handle.addEventListener('mousedown', function (e) { start(e); document.addEventListener('mousemove', mm); document.addEventListener('mouseup', mu); });
    function mm(e) { onMove(e.clientX); }
    function mu() { end(); document.removeEventListener('mousemove', mm); document.removeEventListener('mouseup', mu); }
    // Keyboard resize for a11y.
    handle.addEventListener('keydown', function (e) {
      var step = 24;
      if (e.key === 'ArrowLeft') { AX.width = Math.min(AX.width + step, _maxWidth()); }
      else if (e.key === 'ArrowRight') { AX.width = Math.max(AX.width - step, MIN_WIDTH); }
      else return;
      AX.root.style.width = AX.width + 'px';
      _persist();
      e.preventDefault();
    });
  }

  function _cycleWidth() {
    // Cycle dock width through narrow → mid → wide presets.
    var presets = [380, 660, 920];
    var cur = AX.width;
    var next = presets.find(function (p) { return p > cur + 10; }) || presets[0];
    AX.width = Math.min(next, _maxWidth());
    AX.root.style.width = AX.width + 'px';
    _persist();
  }

  // ----------------------------- responsive engine (T8) -----------------------------
  function _observe() {
    if (typeof ResizeObserver === 'undefined') { _classify(AX.root.getBoundingClientRect().width); return; }
    AX.ro = new ResizeObserver(function (entries) {
      for (var i = 0; i < entries.length; i++) {
        var w = entries[i].contentRect.width;
        _classify(w);
      }
    });
    AX.ro.observe(AX.root);
  }
  function _classify(w) {
    var cls = w < 520 ? 'ax-narrow' : (w <= 820 ? 'ax-mid' : 'ax-wide');
    if (cls === AX.widthClass && AX.root.classList.contains(cls)) return;
    AX.widthClass = cls;
    AX.root.classList.remove('ax-narrow', 'ax-mid', 'ax-wide');
    AX.root.classList.add(cls);
  }

  // ----------------------------- toggle / open / close (T8) -----------------------------
  function _open() {
    if (!AX.built) { if (!_build()) return; }
    AX.open = true;
    AX.root.classList.add('open');
    AX.root.hidden = false;
    _persist();
    if (!AX.treeNodes.length && !AX.cards.length) {
      _ensureMicroverses().then(function () { _selectScope(AX.scope || 'global'); });
    }
  }
  function _close() {
    if (AX.dirty) {
      var msg = _axL('Há alterações não salvas. Fechar mesmo assim?', 'You have unsaved changes. Close anyway?');
      if (typeof window.confirm === 'function' && !window.confirm(msg)) return;
      AX.dirty = false;
    }
    AX.open = false;
    if (AX.root) AX.root.classList.remove('open');
    _persist();
  }

  function acervoExplorerToggle() {
    if (!AX.built) { _restore(); }
    if (AX.open) { _close(); } else { _open(); }
  }
  window.acervoExplorerToggle = acervoExplorerToggle;

  // Warn before navigating away with unsaved edits.
  window.addEventListener('beforeunload', function (e) {
    if (AX.open && AX.dirty) { e.preventDefault(); e.returnValue = ''; return ''; }
  });

  // ----------------------------- breadcrumb -----------------------------
  function _renderCrumb() {
    var host = _q('[data-ax="crumb"]');
    if (!host) return;
    var parts = [];
    var sc = SCOPES.find(function (s) { return s.key === AX.scope; });
    parts.push(sc ? sc.label() : AX.scope);
    if (AX.scope === 'micro' && AX.slug) {
      var mv = (AX.microverses || []).find(function (m) { return m.slug === AX.slug; });
      parts.push(mv ? (mv.name || mv.slug) : AX.slug);
    } else if (AX.scope === 'macro' && AX.slug) {
      parts.push(AX.slug);
    }
    if (AX.nature) parts.push(_natureLabel(AX.nature));
    if (AX.page && AX.page.rel_path) parts.push(_label(AX.page));
    host.innerHTML = parts.map(function (p, i) {
      return '<span class="ax-crumb-part">' + _esc(p) + '</span>' +
        (i < parts.length - 1 ? '<span class="ax-crumb-sep">▸</span>' : '');
    }).join('');
  }

  // ----------------------------- scope selection -----------------------------
  function _selectScope(scope) {
    AX.scope = scope;
    AX.slug = '';
    AX.nature = '';
    AX.cards = [];
    AX.search.active = false;
    AX.search.results = null;
    _renderScopes();
    _renderCrumb();
    _renderCards();
    if (scope === 'micro') {
      _loadMicroTree();
    } else {
      _loadTree(scope);
    }
  }

  function _reloadCurrent(force) {
    if (AX.search.active) { _runSearch(); return; }
    if (AX.scope === 'micro') { if (force) AX.microverses = null; _loadMicroTree(); }
    else { _loadTree(AX.scope); }
    if (AX.selectedPath) _loadPage(AX.selectedPath);
  }

  // ----------------------------- tree (T9) -----------------------------
  function _treePane() { return _q('[data-ax="tree"]'); }

  function _skeleton(host, msg) {
    if (host) host.innerHTML = '<div class="ax-muted">' + _esc(msg || _axL('Carregando…', 'Loading…')) + '</div>';
  }
  function _emptyMsg(host, msg) {
    if (host) host.innerHTML = '<div class="ax-muted ax-empty">' + _esc(msg) + '</div>';
  }
  function _errMsg(host, msg) {
    if (host) host.innerHTML = '<div class="ax-error">' + _esc(msg) + '</div>';
  }

  async function _ensureMicroverses() {
    if (AX.microverses) return AX.microverses;
    if (!_hasSession()) { AX.microverses = []; return AX.microverses; }
    try {
      var d = await api('/api/acervo/microverses?session_id=' + encodeURIComponent(_sid()));
      AX.microverses = Array.isArray(d && d.microverses) ? d.microverses : [];
    } catch (e) { AX.microverses = []; }
    _renderFacets();
    return AX.microverses;
  }

  async function _loadTree(scope) {
    var host = _treePane();
    if (!_hasSession()) { _emptyMsg(host, _axL('Abra uma conversa para ver o acervo.', 'Open a conversation to see the Acervo.')); return; }
    AX.loadingTree = true;
    _skeleton(host);
    try {
      // depth=1 lists nature nodes; expansion lazy-loads pages with depth=2.
      var url = '/api/acervo/x/tree?session_id=' + encodeURIComponent(_sid()) +
        '&scope=' + encodeURIComponent(scope) + '&depth=1';
      if (AX.slug) url += '&slug=' + encodeURIComponent(AX.slug);
      var d = await api(url);
      AX.treeNodes = Array.isArray(d && d.nodes) ? d.nodes : [];
      _renderTree();
    } catch (e) {
      _errMsg(host, _axL('Falha ao carregar a árvore', 'Failed to load tree') + _detail(e));
    } finally { AX.loadingTree = false; }
  }

  async function _loadMicroTree() {
    var host = _treePane();
    if (!_hasSession()) { _emptyMsg(host, _axL('Abra uma conversa para ver o acervo.', 'Open a conversation to see the Acervo.')); return; }
    _skeleton(host);
    await _ensureMicroverses();
    _renderMicroTree();
  }

  function _renderMicroTree() {
    var host = _treePane();
    if (!host) return;
    var list = AX.microverses || [];
    if (!list.length) { _emptyMsg(host, _axL('Nenhum microverso encontrado.', 'No microverses found.')); return; }
    host.innerHTML = list.map(function (m) {
      var open = AX.slug === m.slug;
      var total = Object.keys(m.natures || {}).reduce(function (a, k) { return a + (m.natures[k] || 0); }, 0);
      var head = '<div class="ax-tree-node ax-tree-mv' + (open ? ' open' : '') + '" role="treeitem"' +
        ' aria-expanded="' + (open ? 'true' : 'false') + '" tabindex="0" data-mv="' + _esc(m.slug) + '">' +
        '<span class="ax-tree-caret">' + (open ? '▾' : '▸') + '</span>' +
        '<span class="ax-tree-label">🌐 ' + _esc(m.name || m.slug) + '</span>' +
        '<span class="ax-count">' + total + '</span></div>';
      var kids = '';
      if (open) {
        var nats = Object.keys(m.natures || {}).filter(function (n) { return (m.natures[n] || 0) > 0; }).sort();
        kids = '<div class="ax-tree-children" role="group">' + nats.map(function (n) {
          var sel = AX.nature === n;
          return '<div class="ax-tree-node ax-tree-leaf' + (sel ? ' selected' : '') + '" role="treeitem"' +
            ' tabindex="0" data-mv-nature="' + _esc(n) + '" data-mv-slug="' + _esc(m.slug) + '">' +
            '<span class="ax-tree-label">' + _esc(_natureLabel(n)) + '</span>' +
            '<span class="ax-count">' + (m.natures[n] || 0) + '</span></div>';
        }).join('') + '</div>';
      }
      return head + kids;
    }).join('');
    _wireTreeEvents();
  }

  function _renderTree() {
    var host = _treePane();
    if (!host) return;
    var natureNodes = AX.treeNodes.filter(function (n) { return n.type === 'nature'; });
    var artifactNodes = AX.treeNodes.filter(function (n) { return n.type === 'artifact'; });
    if (!natureNodes.length && !artifactNodes.length) {
      _emptyMsg(host, _axL('Nada neste escopo ainda.', 'Nothing in this scope yet.'));
      return;
    }
    var html = '';
    html += natureNodes.map(function (n) {
      var sel = AX.nature === n.name;
      return '<div class="ax-tree-node ax-tree-leaf' + (sel ? ' selected' : '') + '" role="treeitem"' +
        ' tabindex="0" data-nature="' + _esc(n.name) + '">' +
        '<span class="ax-tree-label">' + _esc(_natureLabel(n.name)) + '</span>' +
        '<span class="ax-count">' + (n.count || 0) + '</span></div>';
    }).join('');
    if (artifactNodes.length) {
      html += '<div class="ax-tree-section">' + _esc(_axL('Artefatos', 'Artifacts')) + '</div>';
      html += artifactNodes.map(function (n) {
        return '<div class="ax-tree-node ax-tree-leaf" role="treeitem" tabindex="0" data-artifact="' + _esc(n.rel_path) + '">' +
          '<span class="ax-tree-label">📦 ' + _esc(_label(n)) + '</span></div>';
      }).join('');
    }
    host.innerHTML = html;
    _wireTreeEvents();
  }

  function _wireTreeEvents() {
    var host = _treePane();
    if (!host) return;
    host.onclick = function (ev) {
      var mv = ev.target.closest('[data-mv]');
      var mvNat = ev.target.closest('[data-mv-nature]');
      var nat = ev.target.closest('[data-nature]');
      var art = ev.target.closest('[data-artifact]');
      if (mvNat) { _selectMicroNature(mvNat.getAttribute('data-mv-slug'), mvNat.getAttribute('data-mv-nature')); return; }
      if (mv) { _toggleMicroverse(mv.getAttribute('data-mv')); return; }
      if (nat) { _selectNature(nat.getAttribute('data-nature')); return; }
      if (art) { _loadPage(art.getAttribute('data-artifact')); return; }
    };
    host.onkeydown = function (ev) {
      if (ev.key !== 'Enter' && ev.key !== ' ') return;
      var node = ev.target.closest('[role="treeitem"]');
      if (node) { ev.preventDefault(); node.click(); }
    };
  }

  function _toggleMicroverse(slug) {
    AX.slug = (AX.slug === slug) ? '' : slug;
    AX.nature = '';
    _renderMicroTree();
    _renderCrumb();
  }
  function _selectMicroNature(slug, nature) {
    AX.slug = slug;
    AX.nature = nature;
    _renderMicroTree();
    _renderCrumb();
    _loadMicroCards(slug, nature);
  }
  function _selectNature(nature) {
    AX.nature = nature;
    _renderTree();
    _renderCrumb();
    _loadScopeCards(AX.scope, nature);
  }

  // ----------------------------- cards / list pane (T9) -----------------------------
  function _cardsPane() { return _q('[data-ax="cards"]'); }

  async function _loadScopeCards(scope, nature) {
    var host = _cardsPane();
    AX.loadingCards = true;
    _skeleton(host);
    try {
      var url = '/api/acervo/x/tree?session_id=' + encodeURIComponent(_sid()) +
        '&scope=' + encodeURIComponent(scope) + '&depth=2';
      if (AX.slug) url += '&slug=' + encodeURIComponent(AX.slug);
      var d = await api(url);
      var nodes = Array.isArray(d && d.nodes) ? d.nodes : [];
      AX.cards = nodes.filter(function (n) { return n.type === 'page' && (!nature || n.nature === nature); });
      _renderCards();
    } catch (e) {
      _errMsg(host, _axL('Falha ao carregar páginas', 'Failed to load pages') + _detail(e));
    } finally { AX.loadingCards = false; }
  }

  async function _loadMicroCards(slug, nature) {
    var host = _cardsPane();
    AX.loadingCards = true;
    _skeleton(host);
    try {
      var url = '/api/acervo/knowledge?session_id=' + encodeURIComponent(_sid()) +
        '&scope=micro&slug=' + encodeURIComponent(slug);
      if (nature) url += '&nature=' + encodeURIComponent(nature);
      var d = await api(url);
      AX.cards = Array.isArray(d && d.pages) ? d.pages : [];
      _renderCards();
    } catch (e) {
      _errMsg(host, _axL('Falha ao carregar páginas', 'Failed to load pages') + _detail(e));
    } finally { AX.loadingCards = false; }
  }

  function _cardHtml(p) {
    var st = p.status ? '<span class="ax-pill" style="--pill:' + _statusMeta(p.status).color + '">' + _esc(_statusMeta(p.status).label()) + '</span>' : '';
    var natBadge = p.nature ? '<span class="ax-badge">' + _esc(_natureLabel(p.nature)) + '</span>' : '';
    var clsBadge = p['class'] ? '<span class="ax-badge ax-badge-class">' + _esc(p['class']) + '</span>' : '';
    var sel = AX.selectedPath === p.rel_path;
    var desc = p.description || p.snippet || '';
    return '<button type="button" class="ax-card' + (sel ? ' selected' : '') + '" data-page="' + _esc(p.rel_path) + '">' +
      '<div class="ax-card-title">' + _esc(_label(p)) + '</div>' +
      (desc ? '<div class="ax-card-desc">' + _esc(desc) + '</div>' : '') +
      '<div class="ax-card-meta">' + natBadge + st + clsBadge + '</div>' +
      '</button>';
  }

  function _renderCards() {
    var host = _cardsPane();
    if (!host) return;
    if (AX.search.active) { _renderSearchResults(); return; }
    if (AX.loadingCards) { _skeleton(host); return; }
    if (!AX.nature && AX.scope !== 'artifacts') {
      _emptyMsg(host, _axL('Selecione uma natureza à esquerda.', 'Select a nature on the left.'));
      return;
    }
    if (!AX.cards.length) { _emptyMsg(host, _axL('Nenhuma página aqui.', 'No pages here.')); return; }
    host.innerHTML = '<div class="ax-cards-grid">' + AX.cards.map(_cardHtml).join('') + '</div>';
    _wireCardEvents(host);
  }

  function _wireCardEvents(host) {
    host.onclick = function (ev) {
      var c = ev.target.closest('[data-page]');
      if (c) _loadPage(c.getAttribute('data-page'));
    };
  }

  // ----------------------------- preview pane (T9) -----------------------------
  function _previewPane() { return _q('[data-ax="preview"]'); }

  async function _loadPage(relPath) {
    if (!relPath) return;
    if (AX.dirty && !(await _confirmDiscard())) return;
    AX.selectedPath = relPath;
    AX.editing = false;
    AX.dirty = false;
    _renderCards(); // re-mark selected card
    var host = _previewPane();
    AX.loadingPage = true;
    _skeleton(host, _axL('Carregando página…', 'Loading page…'));
    try {
      var d = await api('/api/acervo/x/page?session_id=' + encodeURIComponent(_sid()) +
        '&path=' + encodeURIComponent(relPath));
      AX.page = d;
      _renderPreview();
      _renderCrumb();
    } catch (e) {
      AX.page = null;
      _errMsg(host, _axL('Falha ao abrir a página', 'Failed to open page') + _detail(e));
    } finally { AX.loadingPage = false; }
  }

  async function _confirmDiscard() {
    if (typeof showConfirmDialog === 'function') {
      return await showConfirmDialog({
        title: _axL('Descartar alterações?', 'Discard changes?'),
        message: _axL('Você tem edições não salvas. Descartar?', 'You have unsaved edits. Discard them?'),
        confirmLabel: _axL('Descartar', 'Discard'),
      });
    }
    return true;
  }

  function _renderPreview() {
    var host = _previewPane();
    if (!host) return;
    var p = AX.page;
    if (!p) { _emptyMsg(host, _axL('Selecione uma página para visualizar.', 'Select a page to preview.')); return; }

    // Non-md (pdf/image): embed raw.
    if (p.editable === false && p.raw_url) {
      var rawUrl = p.raw_url + '&session_id=' + encodeURIComponent(_sid());
      var isImg = /^image\//.test(p.mime || '');
      host.innerHTML =
        '<div class="ax-preview-head"><div class="ax-preview-title">' + _esc(_label(p)) + '</div></div>' +
        '<div class="ax-preview-raw">' +
        (isImg
          ? '<img src="' + _esc(rawUrl) + '" alt="' + _esc(_label(p)) + '">'
          : '<iframe src="' + _esc(rawUrl) + '" title="' + _esc(_label(p)) + '"></iframe>') +
        '</div>';
      return;
    }

    if (AX.editing) { _renderEditor(); return; }

    var fm = p.frontmatter || {};
    var actions =
      '<button type="button" class="ax-btn ax-btn-primary" data-pv="edit">✎ ' + _esc(_axL('Editar', 'Edit')) + '</button>' +
      '<button type="button" class="ax-btn" data-pv="stage">+ ' + _esc(_axL('Contexto', 'Context')) + '</button>' +
      '<button type="button" class="ax-btn" data-pv="move">' + _esc(_axL('Mover/Renomear', 'Move/Rename')) + '</button>';

    var metaRows = _fmMetaRows(fm);
    var bodyHtml = (typeof renderMd === 'function') ? renderMd(p.body || '') : _esc(p.body || '');
    var quick = _quickActionsHtml(fm);

    host.innerHTML =
      '<div class="ax-preview-head">' +
      '  <div class="ax-preview-title">' + _esc(_label(p)) + '</div>' +
      '  <div class="ax-preview-actions">' + actions + '</div>' +
      '</div>' +
      quick +
      (metaRows ? '<div class="ax-meta">' + metaRows + '</div>' : '') +
      '<div class="ax-preview-body ax-md">' + bodyHtml + '</div>';

    var mdRoot = host.querySelector('.ax-preview-body');
    if (mdRoot && typeof renderKatexBlocks === 'function') { try { renderKatexBlocks(mdRoot); } catch (_) {} }
    _wirePreviewActions(host);
    _wireQuickActions(host);
  }

  // Quick status + tag editors in read mode → /status and /tags endpoints.
  function _quickActionsHtml(fm) {
    var curStatus = fm.status || '';
    var statusSel = '<option value="">—</option>' + UI_STATUSES.map(function (s) {
      return '<option value="' + s + '"' + (curStatus === s ? ' selected' : '') + '>' + _esc(_statusMeta(s).label()) + '</option>';
    }).join('');
    var tags = Array.isArray(fm.tags) ? fm.tags : (fm.tags ? [String(fm.tags)] : []);
    var chips = tags.map(function (t) {
      return '<span class="ax-chip">' + _esc(t) +
        '<button type="button" class="ax-chip-x" data-tag-remove="' + _esc(t) + '" aria-label="' + _esc(_axL('Remover tag', 'Remove tag')) + '">×</button></span>';
    }).join('');
    return '<div class="ax-quick">' +
      '<label class="ax-quick-status"><span>Status</span>' +
      '<select data-qa="status">' + statusSel + '</select></label>' +
      '<div class="ax-quick-tags">' + chips +
      '<input type="text" class="ax-chip-input" data-qa="tag-add" placeholder="+ tag" aria-label="' + _esc(_axL('Adicionar tag', 'Add tag')) + '">' +
      '</div></div>';
  }

  function _wireQuickActions(host) {
    var sel = host.querySelector('[data-qa="status"]');
    if (sel) {
      sel.addEventListener('change', function () {
        var v = sel.value;
        if (v) _setStatus(v);
      });
    }
    host.querySelectorAll('[data-tag-remove]').forEach(function (b) {
      b.addEventListener('click', function () { _editTags([], [b.getAttribute('data-tag-remove')]); });
    });
    var addIn = host.querySelector('[data-qa="tag-add"]');
    if (addIn) {
      addIn.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          var v = addIn.value.trim();
          if (v) _editTags([v], []);
        }
      });
    }
  }

  async function _setStatus(status) {
    var p = AX.page;
    if (!p || !p.rel_path) return;
    try {
      await api('/api/acervo/x/status', {
        method: 'POST',
        body: JSON.stringify({ session_id: _sid(), path: p.rel_path, status: status }),
      });
      _toast(_axL('Status atualizado', 'Status updated'), 2500, 'success');
      await _loadPage(p.rel_path);
      _reloadCardsAfterWrite();
    } catch (e) {
      _toast(_axL('Falha ao atualizar status', 'Status update failed') + _detail(e), 6000, 'error');
    }
  }

  async function _editTags(add, remove) {
    var p = AX.page;
    if (!p || !p.rel_path) return;
    try {
      var r = await api('/api/acervo/x/tags', {
        method: 'POST',
        body: JSON.stringify({ session_id: _sid(), path: p.rel_path, add: add, remove: remove }),
      });
      if (AX.page && AX.page.frontmatter && r && Array.isArray(r.tags)) AX.page.frontmatter.tags = r.tags;
      _toast(_axL('Tags atualizadas', 'Tags updated'), 2000, 'success');
      _renderPreview();
      _reloadCardsAfterWrite();
    } catch (e) {
      _toast(_axL('Falha ao atualizar tags', 'Tags update failed') + _detail(e), 6000, 'error');
    }
  }

  function _fmMetaRows(fm) {
    var rows = [];
    function row(k, v) {
      if (v === null || v === undefined || v === '') return;
      var val = Array.isArray(v) ? v.join(', ') : String(v);
      rows.push('<div class="ax-meta-row"><span class="ax-meta-k">' + _esc(k) + '</span><span class="ax-meta-v">' + _esc(val) + '</span></div>');
    }
    row(_axL('Status', 'Status'), fm.status);
    row(_axL('Natureza', 'Nature'), fm.nature);
    row('Tags', fm.tags);
    row(_axL('Classe', 'Class'), fm['class']);
    row(_axL('Tipo', 'Type'), fm.kind || fm.type);
    return rows.join('');
  }

  function _wirePreviewActions(host) {
    host.querySelectorAll('[data-pv]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var act = btn.getAttribute('data-pv');
        if (act === 'edit') { AX.editing = true; _renderPreview(); }
        else if (act === 'stage') { _stageCurrent(); }
        else if (act === 'move') { _moveDialog(); }
      });
    });
  }

  // ----------------------------- editor (T10) -----------------------------
  function _renderEditor() {
    var host = _previewPane();
    var p = AX.page;
    if (!host || !p) return;
    var fm = p.frontmatter || {};
    var perene = (fm['class'] === 'perene');
    var tagsCsv = Array.isArray(fm.tags) ? fm.tags.join(', ') : (fm.tags || '');
    var statusSel = UI_STATUSES.map(function (s) {
      return '<option value="' + s + '"' + ((fm.status || 'draft') === s ? ' selected' : '') + '>' + _esc(_statusMeta(s).label()) + '</option>';
    }).join('');
    var natSel = '<option value="">—</option>' + ALL_NATURES.map(function (n) {
      return '<option value="' + n + '"' + ((fm.nature || '') === n ? ' selected' : '') + '>' + _esc(_natureLabel(n)) + '</option>';
    }).join('');

    host.innerHTML =
      '<div class="ax-preview-head">' +
      '  <div class="ax-preview-title">' + _esc(_axL('Editando', 'Editing')) + ': ' + _esc(_label(p)) + '</div>' +
      '  <div class="ax-preview-actions">' +
      '    <button type="button" class="ax-btn ax-btn-primary" data-ed="save">' + _esc(_axL('Salvar', 'Save')) + '</button>' +
      '    <button type="button" class="ax-btn" data-ed="cancel">' + _esc(_axL('Cancelar', 'Cancel')) + '</button>' +
      '  </div>' +
      '</div>' +
      (perene ? '<div class="ax-warn">⚠ ' + _esc(_axL('Esta página é perene (class: perene). Edite com cuidado.', 'This page is perennial (class: perene). Edit with care.')) + '</div>' : '') +
      '<div class="ax-editor">' +
      '  <label class="ax-field"><span>' + _esc(_axL('Título', 'Title')) + '</span>' +
      '    <input type="text" data-ed-fm="title" value="' + _esc(fm.title || '') + '"></label>' +
      '  <div class="ax-field-row">' +
      '    <label class="ax-field"><span>Status</span><select data-ed-fm="status">' + statusSel + '</select></label>' +
      '    <label class="ax-field"><span>' + _esc(_axL('Natureza', 'Nature')) + '</span><select data-ed-fm="nature">' + natSel + '</select></label>' +
      '  </div>' +
      '  <label class="ax-field"><span>Tags <small>(CSV)</small></span>' +
      '    <input type="text" data-ed-fm="tags" value="' + _esc(tagsCsv) + '" placeholder="a, b, c"></label>' +
      '  <label class="ax-field ax-field-grow"><span>' + _esc(_axL('Conteúdo', 'Body')) + '</span>' +
      '    <textarea data-ed="body" spellcheck="false">' + _esc(p.body || '') + '</textarea></label>' +
      '</div>';

    var dirtyMark = function () { AX.dirty = true; };
    host.querySelectorAll('[data-ed-fm],[data-ed="body"]').forEach(function (el) {
      el.addEventListener('input', dirtyMark);
      el.addEventListener('change', dirtyMark);
    });
    host.querySelector('[data-ed="save"]').addEventListener('click', _saveCurrent);
    host.querySelector('[data-ed="cancel"]').addEventListener('click', async function () {
      if (AX.dirty && !(await _confirmDiscard())) return;
      AX.editing = false; AX.dirty = false; _renderPreview();
    });
  }

  async function _saveCurrent() {
    var host = _previewPane();
    var p = AX.page;
    if (!p) return;
    var fmEls = host.querySelectorAll('[data-ed-fm]');
    var bodyEl = host.querySelector('[data-ed="body"]');
    var fm = {};
    fmEls.forEach(function (el) {
      var key = el.getAttribute('data-ed-fm');
      var val = el.value;
      if (key === 'tags') {
        fm.tags = String(val).split(',').map(function (t) { return t.trim(); }).filter(Boolean);
      } else if (val !== '') {
        fm[key] = val;
      }
    });
    var body = bodyEl ? bodyEl.value : (p.body || '');

    // Non-blocking perene confirm.
    if (p.frontmatter && p.frontmatter['class'] === 'perene') {
      var ok = true;
      if (typeof showConfirmDialog === 'function') {
        ok = await showConfirmDialog({
          title: _axL('Página perene', 'Perennial page'),
          message: _axL('Esta página é marcada como perene. Salvar mesmo assim?', 'This page is marked perennial. Save anyway?'),
          confirmLabel: _axL('Salvar', 'Save'),
        });
      }
      if (!ok) return;
    }

    try {
      await api('/api/acervo/x/save', {
        method: 'POST',
        body: JSON.stringify({ session_id: _sid(), path: p.rel_path, frontmatter: fm, body: body }),
      });
      _toast(_axL('Página salva', 'Page saved'), 2500, 'success');
      AX.dirty = false;
      AX.editing = false;
      await _loadPage(p.rel_path);     // reload from disk (merged frontmatter)
      _reloadCardsAfterWrite();
    } catch (e) {
      _toast(_axL('Falha ao salvar', 'Save failed') + _detail(e), 6000, 'error');
      // Keep editor open on error.
    }
  }

  function _reloadCardsAfterWrite() {
    if (AX.search.active) { _runSearch(); return; }
    if (AX.scope === 'micro' && AX.slug) { _loadMicroCards(AX.slug, AX.nature); }
    else if (AX.nature) { _loadScopeCards(AX.scope, AX.nature); }
  }

  // ----------------------------- stage / move (T10) -----------------------------
  async function _stageCurrent() {
    var p = AX.page;
    if (!p || !p.rel_path) return;
    try {
      var r = await api('/api/acervo/x/stage', {
        method: 'POST',
        body: JSON.stringify({ session_id: _sid(), source: p.rel_path }),
      });
      if (r && r.path) {
        if (typeof S !== 'undefined' && S) {
          if (!Array.isArray(S.pendingContextAttachments)) S.pendingContextAttachments = [];
          if (!S.pendingContextAttachments.some(function (a) { return a._ctxSource === p.rel_path; })) {
            S.pendingContextAttachments.push({ name: r.name, path: r.path, mime: r.mime, size: r.size, is_image: !!r.is_image, _ctxSource: p.rel_path });
          }
        }
        if (typeof renderStagedContextChips === 'function') renderStagedContextChips();
        _toast(_axL('Adicionado ao contexto da próxima mensagem', 'Added to next message context'), 3000, 'success');
      }
    } catch (e) {
      _toast(_axL('Falha ao adicionar ao contexto', 'Failed to stage context') + _detail(e), 6000, 'error');
    }
  }

  async function _moveDialog() {
    var p = AX.page;
    if (!p || !p.rel_path) return;
    var dest = (typeof window.prompt === 'function')
      ? window.prompt(_axL('Novo caminho (relativo ao acervo):', 'New path (acervo-relative):'), p.rel_path)
      : null;
    if (!dest || dest === p.rel_path) return;
    dest = String(dest).trim();
    var ok = true;
    if (typeof showConfirmDialog === 'function') {
      ok = await showConfirmDialog({
        title: _axL('Mover/Renomear', 'Move/Rename'),
        message: _axL('Mover para ', 'Move to ') + '“' + dest + '”?',
        confirmLabel: _axL('Mover', 'Move'),
      });
    }
    if (!ok) return;
    try {
      var r = await api('/api/acervo/x/move', {
        method: 'POST',
        body: JSON.stringify({ session_id: _sid(), path: p.rel_path, dest: dest }),
      });
      _toast(_axL('Movido', 'Moved'), 2500, 'success');
      var newRel = (r && r.rel_path) || dest;
      AX.selectedPath = newRel;
      _reloadCurrent(true);   // refresh tree + cards
      _loadPage(newRel);
    } catch (e) {
      _toast(_axL('Falha ao mover', 'Move failed') + _detail(e), 6000, 'error');
    }
  }

  // ----------------------------- search (T10) -----------------------------
  async function _runSearch() {
    var hasQuery = !!(AX.search.q || AX.search.nature || AX.search.status || AX.search.microverso || AX.search.tag);
    if (!hasQuery) {
      AX.search.active = false;
      AX.search.results = null;
      _renderCards();
      return;
    }
    if (!_hasSession()) return;
    AX.search.active = true;
    var host = _cardsPane();
    _skeleton(host, _axL('Buscando…', 'Searching…'));
    try {
      var params = ['session_id=' + encodeURIComponent(_sid())];
      if (AX.search.q) params.push('q=' + encodeURIComponent(AX.search.q));
      if (AX.search.nature) params.push('nature=' + encodeURIComponent(AX.search.nature));
      if (AX.search.status) params.push('status=' + encodeURIComponent(AX.search.status));
      if (AX.search.microverso) params.push('microverso=' + encodeURIComponent(AX.search.microverso));
      if (AX.search.tag) params.push('tag=' + encodeURIComponent(AX.search.tag));
      var d = await api('/api/acervo/x/search?' + params.join('&'));
      AX.search.results = Array.isArray(d && d.results) ? d.results : [];
      AX.search.truncated = !!(d && d.truncated);
      _renderSearchResults();
    } catch (e) {
      _errMsg(host, _axL('Falha na busca', 'Search failed') + _detail(e));
    }
  }

  function _renderSearchResults() {
    var host = _cardsPane();
    if (!host) return;
    var res = AX.search.results || [];
    if (!res.length) { _emptyMsg(host, _axL('Nenhum resultado.', 'No results.')); return; }
    var trunc = AX.search.truncated
      ? '<div class="ax-muted ax-trunc">' + _esc(_axL('Resultados limitados pelo servidor.', 'Results capped by the server.')) + '</div>'
      : '';
    host.innerHTML = '<div class="ax-cards-grid">' + res.map(_cardHtml).join('') + '</div>' + trunc;
    _wireCardEvents(host);
  }

  function _detail(e) { return (e && e.message) ? ': ' + e.message : ''; }

})();
