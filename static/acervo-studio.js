/* MOD-010 Acervo Studio — self-contained full-screen surface. Read-only Phase 0.
   No ES import/export (sourceType:"script"); reuses app globals S/api/esc/showToast/
   renderMd/humanizeFilename. Prefix: acervoStudio* / AXS / .axs-*. */
'use strict';
(function () {
  var AXS = { built: false, open: false, scope: 'micro', slug: '', selectedPath: '',
    page: null, editing: false, dirty: false, artifactId: '' };

  function _sid() { return (typeof S !== 'undefined' && S && S.session) ? S.session.session_id : ''; }
  function _esc(s) { return (typeof esc === 'function') ? esc(s) : String(s == null ? '' : s); }
  function _toast(m, type) { if (typeof showToast === 'function') showToast(m, 3000, type || ''); }
  function _root() { return document.getElementById('acervoStudioRoot'); }

  // If the Studio is opened with no active chat session, transparently create
  // and bind one (mirrors ui.js promptNewFile/promptNewFolder) so the acervo is
  // browsable standalone. The backend auth gate is UNCHANGED — a real session
  // still exists; this only spares the user from opening a chat first. All app
  // globals are typeof-guarded; on failure (e.g. session API unreachable) the
  // caller falls back to the "Sem sessão ativa." empty state.
  async function _ensureSession() {
    if (_sid()) return true;
    if (typeof S === 'undefined' || !S || typeof api !== 'function') return false;
    var body = {};
    if (typeof S._profileDefaultWorkspace === 'string' && S._profileDefaultWorkspace) {
      body.workspace = S._profileDefaultWorkspace;
    }
    var r;
    try { r = await api('/api/session/new', { method: 'POST', body: JSON.stringify(body) }); }
    catch (e) { return false; }
    if (!r || !r.session) return false;
    S.session = r.session;
    S.messages = [];
    if (typeof syncTopbar === 'function') { try { syncTopbar(); } catch (e) { /* shell refresh best-effort */ } }
    if (typeof renderMessages === 'function') { try { renderMessages(); } catch (e) { /* shell refresh best-effort */ } }
    if (typeof renderSessionList === 'function') { try { await renderSessionList(); } catch (e) { /* shell refresh best-effort */ } }
    return true;
  }

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
  async function _close() {
    if (AXS.dirty && !(await _confirmDiscard())) return;
    AXS.dirty = false;
    AXS.editing = false;
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

  var AXS_STATUSES = ['draft', 'ready', 'archived'];
  var AXS_NATURES = ['context', 'knowledge', 'contracts', 'workflows', 'decisions',
    'templates', 'tools', 'skills', 'persona', 'prompts', 'reflections'];

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
    var root = _root();
    var nav = root && root.querySelector('[data-axs="nav"]');
    if (!nav) return;
    if (!_sid()) {
      nav.innerHTML = '<div class="axs-empty">Preparando sessão…</div>';
      await _ensureSession();
    }
    if (!_sid()) { nav.innerHTML = '<div class="axs-empty">Sem sessão ativa.</div>'; return; }
    var html = '<div class="axs-sec">Acervo</div>';
    // Inbox count badge (best-effort). Fetched ONCE and passed through to
    // acervoStudioSelectScope when inbox is the active scope (Phase-0 minor:
    // the same tree was fetched twice).
    var inboxData = null;
    try { inboxData = await _tree('inbox', ''); } catch (e) { /* badge only */ }
    var inboxCount = (inboxData && inboxData.count) || 0;
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
    if (AXS.scope) {
      acervoStudioSelectScope(AXS.scope, AXS.slug,
        AXS.scope === 'inbox' && !AXS.slug ? inboxData : null);
    }
  }

  async function acervoStudioSelectScope(scope, slug, prefetched) {
    var root = _root();
    if (!root) return;
    AXS.scope = scope; AXS.slug = slug || '';
    var nav = root.querySelector('[data-axs="nav"]');
    if (!nav) return;
    nav.querySelectorAll('.axs-ni').forEach(function (el) {
      el.classList.toggle('on', el.getAttribute('data-scope') === scope);
    });
    var sub = nav.querySelector('[data-sub="' + scope + '"]');
    nav.querySelectorAll('.axs-sub').forEach(function (s) { if (s !== sub) s.innerHTML = ''; });
    if (!sub) return;
    sub.innerHTML = '<div class="axs-empty">Carregando…</div>';
    var data;
    try { data = prefetched || await _tree(scope, slug); }
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
        out += '<div class="axs-pi" data-intake="' + _esc(n.id) + '"><span class="st"></span>' +
          _esc(n.title) + ' · ' + _esc(n.status) + '</div>';
      } else if (n.type === 'artifact') {
        out += '<div class="axs-pi" data-art="' + _esc(n.name) +
          '" data-artkind="' + _esc(n.kind || '') +
          '" data-artpath="' + _esc(n.rel_path) +
          '" data-arttitle="' + _esc(n.title || n.name) + '">📦 ' +
          _esc(n.title || n.name) + '</div>';
      }
    });
    sub.innerHTML = out;
    if (scope === 'inbox') {
      var cap = document.createElement('button');
      cap.type = 'button';
      cap.className = 'axs-cap-add';
      cap.textContent = '＋ Capturar';
      cap.addEventListener('click', acervoStudioCapture);
      sub.insertBefore(cap, sub.firstChild);
    }
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
    sub.querySelectorAll('[data-intake]').forEach(function (el) {
      el.addEventListener('click', function () {
        acervoStudioOpenEnvelope(el.getAttribute('data-intake'));
      });
    });
    sub.querySelectorAll('[data-art]').forEach(function (el) {
      el.addEventListener('click', function () {
        if (el.getAttribute('data-artkind') === 'dir') {
          _openArtifact(el.getAttribute('data-art'), el.getAttribute('data-arttitle'));
        } else if (typeof acervoStudioOpenPage === 'function') {
          acervoStudioOpenPage(el.getAttribute('data-artpath'));
        }
      });
    });
  }
  window.acervoStudioRenderNav = acervoStudioRenderNav;
  window.acervoStudioSelectScope = acervoStudioSelectScope;

  function _chip(label, cls) { return '<span class="' + (cls || '') + '">' + _esc(label) + '</span>'; }

  function _detail(e) {
    var m = e && e.message ? String(e.message) : '';
    return m ? ' — ' + m : '';
  }

  async function _confirmDiscard() {
    if (typeof showConfirmDialog === 'function') {
      return await showConfirmDialog({
        title: 'Descartar alterações?',
        message: 'Há edições não salvas nesta página.',
        confirmLabel: 'Descartar',
        danger: true
      });
    }
    return true;
  }

  function _actionsBar(p) {
    var md = !!(p && p.editable);
    var acts = '';
    if (md) acts += '<button type="button" class="axs-act" data-axs-act="edit">✎ Editar</button>';
    acts += '<button type="button" class="axs-act" data-axs-act="stage">⇪ Enviar ao chat</button>';
    acts += '<button type="button" class="axs-act" data-axs-act="download">⬇ Baixar</button>';
    if (md) acts += '<button type="button" class="axs-act" data-axs-act="more" ' +
      'aria-haspopup="true" aria-label="Mais ações">⋯</button>';
    return '<div class="axs-acts">' + acts + '</div>';
  }

  function _wireActs(reader) {
    reader.querySelectorAll('[data-axs-act]').forEach(function (b) {
      b.addEventListener('click', function () {
        var act = b.getAttribute('data-axs-act');
        if (act === 'edit') acervoStudioEdit();
        else if (act === 'stage') acervoStudioStage();
        else if (act === 'download') acervoStudioDownload();
        else if (act === 'more') _toggleMenu(b);
      });
    });
  }

  function _downloadUrl(qs) {
    return '/api/acervo/x/download?session_id=' + encodeURIComponent(_sid()) + '&' + qs;
  }

  function _triggerDownload(url) {
    var a = document.createElement('a');
    a.href = url;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  function acervoStudioDownload() {
    if (AXS.artifactId) {
      _triggerDownload(_downloadUrl('artifact_id=' + encodeURIComponent(AXS.artifactId)));
      return;
    }
    if (!AXS.selectedPath) return;
    _triggerDownload(_downloadUrl('path=' + encodeURIComponent(AXS.selectedPath)));
  }
  window.acervoStudioDownload = acervoStudioDownload;

  async function acervoStudioStage() {
    var relPath = AXS.selectedPath;
    if (!relPath) { _toast('Abra uma página primeiro', 'error'); return; }
    var r;
    try {
      r = await api('/api/acervo/x/stage', {
        method: 'POST',
        body: JSON.stringify({ session_id: _sid(), source: relPath })
      });
    } catch (e) {
      _toast('Falha ao adicionar ao contexto' + _detail(e), 'error');
      return;
    }
    if (r && r.path) {
      if (typeof S !== 'undefined' && S) {
        if (!Array.isArray(S.pendingContextAttachments)) S.pendingContextAttachments = [];
        if (!S.pendingContextAttachments.some(function (a) { return a._ctxSource === relPath; })) {
          S.pendingContextAttachments.push({
            name: r.name, path: r.path, mime: r.mime, size: r.size,
            is_image: !!r.is_image, _ctxSource: relPath
          });
        }
      }
      if (typeof renderStagedContextChips === 'function') renderStagedContextChips();
      _toast('Adicionado ao contexto da próxima mensagem', 'success');
    }
  }
  window.acervoStudioStage = acervoStudioStage;

  function _openArtifact(id, title) {
    var root = _root();
    if (!root) return;
    AXS.selectedPath = '';
    AXS.page = null;
    AXS.artifactId = id;
    var reader = root.querySelector('[data-axs="reader"]');
    reader.innerHTML =
      '<div class="axs-crumb"><b>_artifacts</b> › ' + _esc(id) +
      '  <div class="axs-acts"><button type="button" class="axs-act" data-axs-act="download">⬇ Baixar (zip)</button></div></div>' +
      '<div class="axs-doc">' +
      '  <h1 class="axs-title">📦 ' + _esc(title || id) + '</h1>' +
      '  <div class="axs-empty">Pacote de artefato — o download inclui manifest.json, source/ e exports/.</div>' +
      '</div>';
    _wireActs(reader);
  }

  function acervoStudioEdit() {
    var p = AXS.page;
    var root = _root();
    if (!p || !p.editable || !root) return;
    AXS.editing = true;
    var reader = root.querySelector('[data-axs="reader"]');
    var fm = p.frontmatter || {};
    var tagsCsv = Array.isArray(fm.tags) ? fm.tags.join(', ') : (fm.tags || '');
    var curSt = (fm.status || '').trim();
    var stInSet = AXS_STATUSES.indexOf(curSt) >= 0;
    var stSel = (curSt && !stInSet
        ? '<option value="" selected>' + _esc('(manter: ' + curSt + ')') + '</option>' : '')
      + AXS_STATUSES.map(function (s) {
          var sel = stInSet ? (curSt === s) : (!curSt && s === 'draft');
          return '<option value="' + s + '"' + (sel ? ' selected' : '') + '>' + s + '</option>';
        }).join('');
    var natSel = '<option value="">—</option>' + AXS_NATURES.map(function (n) {
      return '<option value="' + n + '"' +
        ((fm.nature || '') === n ? ' selected' : '') + '>' + n + '</option>';
    }).join('');
    var perene = String(fm['class'] || '').toLowerCase().indexOf('peren') === 0;
    reader.innerHTML =
      '<div class="axs-crumb">✎ ' + _esc(p.rel_path) +
      '  <div class="axs-acts">' +
      '    <button type="button" class="axs-act axs-act-primary" data-axs-ed="save">Salvar</button>' +
      '    <button type="button" class="axs-act" data-axs-ed="cancel">Cancelar</button>' +
      '  </div></div>' +
      '<div class="axs-doc axs-editor">' +
      (perene ? '<div class="axs-warn">⚠ Página perene (class: perene) — edite com cuidado.</div>' : '') +
      '  <label class="axs-field"><span>Título</span>' +
      '    <input type="text" data-axs-fm="title" value="' + _esc(fm.title || '') + '"></label>' +
      '  <div class="axs-frow">' +
      '    <label class="axs-field"><span>Status</span><select data-axs-fm="status">' + stSel + '</select></label>' +
      '    <label class="axs-field"><span>Natureza</span><select data-axs-fm="nature">' + natSel + '</select></label>' +
      '  </div>' +
      '  <label class="axs-field"><span>Tags (CSV)</span>' +
      '    <input type="text" data-axs-fm="tags" value="' + _esc(tagsCsv) + '" placeholder="a, b, c"></label>' +
      '  <label class="axs-field axs-fgrow"><span>Conteúdo</span>' +
      '    <textarea data-axs-ed="body" spellcheck="false">' + _esc(p.body || '') + '</textarea></label>' +
      '</div>';
    var mark = function () { AXS.dirty = true; };
    reader.querySelectorAll('[data-axs-fm],[data-axs-ed="body"]').forEach(function (el) {
      el.addEventListener('input', mark);
      el.addEventListener('change', mark);
    });
    reader.querySelector('[data-axs-ed="save"]').addEventListener('click', acervoStudioSave);
    reader.querySelector('[data-axs-ed="cancel"]').addEventListener('click', async function () {
      if (AXS.dirty && !(await _confirmDiscard())) return;
      AXS.dirty = false;
      AXS.editing = false;
      acervoStudioOpenPage(p.rel_path);
    });
  }
  window.acervoStudioEdit = acervoStudioEdit;

  async function acervoStudioSave() {
    var p = AXS.page;
    var root = _root();
    if (!p || !root) return;
    var reader = root.querySelector('[data-axs="reader"]');
    var fm = {};
    reader.querySelectorAll('[data-axs-fm]').forEach(function (el) {
      var k = el.getAttribute('data-axs-fm');
      var v = el.value;
      if (k === 'tags') {
        fm.tags = String(v).split(',').map(function (t) { return t.trim(); }).filter(Boolean);
      } else if (v !== '') {
        fm[k] = v;
      }
    });
    var bodyEl = reader.querySelector('[data-axs-ed="body"]');
    var body = bodyEl ? bodyEl.value : (p.body || '');
    var isPerene = p.frontmatter &&
      String(p.frontmatter['class'] || '').toLowerCase().indexOf('peren') === 0;
    if (isPerene && typeof showConfirmDialog === 'function') {
      var ok = await showConfirmDialog({
        title: 'Página perene',
        message: 'Esta página é marcada como perene. Salvar mesmo assim?',
        confirmLabel: 'Salvar'
      });
      if (!ok) return;
    }
    try {
      await api('/api/acervo/x/save', {
        method: 'POST',
        body: JSON.stringify({ session_id: _sid(), path: p.rel_path, frontmatter: fm, body: body })
      });
    } catch (e) {
      _toast('Falha ao salvar' + _detail(e), 'error');
      return; // keep the editor open on error
    }
    AXS.dirty = false;
    AXS.editing = false;
    _toast('Página salva', 'success');
    await acervoStudioOpenPage(p.rel_path);   // reload from disk (merged frontmatter)
    acervoStudioSelectScope(AXS.scope, AXS.slug);  // refresh titles/status dots
  }
  window.acervoStudioSave = acervoStudioSave;

  function _toggleMenu(anchor) {
    var old = document.getElementById('axsMenu');
    if (old) { old.remove(); return; }
    var m = document.createElement('div');
    m.id = 'axsMenu';
    m.className = 'axs-menu';
    m.innerHTML =
      '<button type="button" data-axs-m="move">Mover / renomear…</button>' +
      '<div class="axs-menu-sep"></div>' +
      AXS_STATUSES.map(function (s) {
        return '<button type="button" data-axs-m="st:' + s + '">Status: ' + s + '</button>';
      }).join('');
    document.body.appendChild(m);
    var r = anchor.getBoundingClientRect();
    m.style.top = (r.bottom + 4) + 'px';
    m.style.right = Math.max(8, window.innerWidth - r.right) + 'px';
    m.querySelectorAll('[data-axs-m]').forEach(function (b) {
      b.addEventListener('click', function () {
        m.remove();
        var v = b.getAttribute('data-axs-m');
        if (v === 'move') acervoStudioMove();
        else if (v.indexOf('st:') === 0) acervoStudioSetStatus(v.slice(3));
      });
    });
    setTimeout(function () {
      document.addEventListener('click', function h(ev) {
        if (!m.contains(ev.target)) {
          m.remove();
          document.removeEventListener('click', h);
        }
      });
    }, 0);
  }

  async function acervoStudioMove() {
    var p = AXS.page;
    if (!p || !p.rel_path) return;
    var dest = (typeof showPromptDialog === 'function')
      ? await showPromptDialog({
        title: 'Mover / renomear',
        message: 'Novo caminho (relativo ao acervo):',
        defaultValue: p.rel_path,
        confirmLabel: 'Mover'
      }) : null;
    if (dest == null) return;
    dest = String(dest).trim();
    if (!dest || dest === p.rel_path) return;
    var r;
    try {
      r = await api('/api/acervo/x/move', {
        method: 'POST',
        body: JSON.stringify({ session_id: _sid(), path: p.rel_path, dest: dest })
      });
    } catch (e) {
      _toast('Falha ao mover' + _detail(e), 'error');
      return;
    }
    _toast('Movido', 'success');
    var newRel = (r && r.rel_path) || dest;
    await acervoStudioOpenPage(newRel);
    acervoStudioSelectScope(AXS.scope, AXS.slug);
  }
  window.acervoStudioMove = acervoStudioMove;

  async function acervoStudioSetStatus(status) {
    var p = AXS.page;
    if (!p || !p.rel_path) return;
    try {
      await api('/api/acervo/x/status', {
        method: 'POST',
        body: JSON.stringify({ session_id: _sid(), path: p.rel_path, status: status })
      });
    } catch (e) {
      _toast('Falha ao atualizar status' + _detail(e), 'error');
      return;
    }
    _toast('Status atualizado', 'success');
    await acervoStudioOpenPage(p.rel_path);
    acervoStudioSelectScope(AXS.scope, AXS.slug);
  }
  window.acervoStudioSetStatus = acervoStudioSetStatus;

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
    var root = _root();
    if (!root) return;
    if (AXS.dirty && !(await _confirmDiscard())) return;
    AXS.dirty = false;
    AXS.editing = false;
    AXS.selectedPath = relPath;
    AXS.artifactId = '';
    var reader = root.querySelector('[data-axs="reader"]');
    // Mark the active page in the nav — runs for both md and non-md branches.
    var nav = root.querySelector('[data-axs="nav"]');
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
    if (p && p.editable === false) {
      AXS.page = null;
      // Phase-0 minor fixed: build the raw URL client-side, fully encoded
      // (p.raw_url already embeds session_id unencoded — don't reuse/append).
      var rawUrl = '/api/acervo/x/raw?session_id=' + encodeURIComponent(_sid()) +
        '&path=' + encodeURIComponent(relPath);
      var isImg = (p.mime || '').indexOf('image/') === 0;
      var view = isImg
        ? '<img class="axs-raw" src="' + _esc(rawUrl) + '" alt="' + _esc(relPath) + '">'
        : '<iframe class="axs-raw" src="' + _esc(rawUrl) + '" sandbox title="' + _esc(relPath) + '"></iframe>';
      reader.innerHTML = '<div class="axs-crumb">' + crumb + _actionsBar(p) + '</div>' +
        '<div class="axs-doc">' + view + '</div>';
      _wireActs(reader);
      return;
    }
    AXS.page = p;
    var fm = (p && p.frontmatter) || {};
    var chips = '';
    if (fm.nature) chips += _chip(fm.nature);
    if (fm['class']) {
      var _isPerene = String(fm['class']).toLowerCase().indexOf('peren') === 0;
      chips += _chip((_isPerene ? '🔒 ' : '') + fm['class'], _isPerene ? 'perene' : '');
    }
    if (fm.status) chips += _chip('✓ ' + fm.status);
    (Array.isArray(fm.tags) ? fm.tags : []).forEach(function (t) { chips += _chip('#' + t); });
    var title = p.title || relPath;
    var body = _stripDupTitleH1(p.body || '', title);
    var bodyHtml = (typeof renderMd === 'function') ? renderMd(body) : _esc(body);
    reader.innerHTML =
      '<div class="axs-crumb">' + crumb + _actionsBar(p) + '</div>' +
      '<div class="axs-doc">' +
      '  <div class="axs-fm">' + chips + '</div>' +
      '  <h1 class="axs-title">' + _esc(title) + '</h1>' +
      '  <div class="axs-md">' + bodyHtml + '</div>' +
      '</div>';
    _wireActs(reader);
  }
  window.acervoStudioOpenPage = acervoStudioOpenPage;

  async function acervoStudioSearch(q) {
    var root = _root();
    if (!root) return;
    if (AXS.dirty && !(await _confirmDiscard())) return;
    AXS.dirty = false;
    AXS.editing = false;
    q = (q || '').trim();
    var reader = root.querySelector('[data-axs="reader"]');
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
      el.addEventListener('click', function () {
        if (typeof acervoStudioOpenPage === 'function')
          acervoStudioOpenPage(el.getAttribute('data-path'));
      });
    });
  }
  window.acervoStudioSearch = acervoStudioSearch;

  // ── Phase 2a: inbox envelope detail ──────────────────────────────────────
  async function acervoStudioOpenEnvelope(iid) {
    var root = _root();
    var reader = root && root.querySelector('[data-axs="reader"]');
    if (!reader) return;
    AXS.selectedPath = ''; AXS.page = null; AXS.artifactId = '';
    reader.innerHTML = '<div class="axs-reader-empty">Carregando…</div>';
    var d;
    try {
      d = await api('/api/acervo/x/intake/item?session_id=' + encodeURIComponent(_sid()) +
        '&id=' + encodeURIComponent(iid));
    } catch (e) { reader.innerHTML = '<div class="axs-reader-empty">Erro ao abrir o envelope.</div>'; return; }
    var env = (d && d.envelope) || {};
    var chips = _chip('📥 ' + (env.content_type || 'intake')) + _chip('✓ ' + (env.status || 'received'));
    var caption = env.user_caption || env.original_filename || env.intake_id || iid;
    var files = env.files || [];
    var body = '';
    // Preview the first original file inline (md rendered; else sandboxed iframe/img).
    if (files.length) {
      var rawUrl = '/api/acervo/x/raw?session_id=' + encodeURIComponent(_sid()) +
        '&path=' + encodeURIComponent('_inbox/incoming/' + iid + '/' + files[0]);
      if (/\.(md|txt)$/i.test(files[0])) {
        var txt = '';
        try { var r = await fetch(rawUrl); txt = await r.text(); } catch (e) { txt = ''; }
        body = '<div class="axs-md">' +
          ((typeof renderMd === 'function') ? renderMd(txt) : _esc(txt)) + '</div>';
      } else if (env.content_type === 'image') {
        body = '<img class="axs-raw" src="' + _esc(rawUrl) + '" alt="' + _esc(files[0]) + '">';
      } else {
        body = '<iframe class="axs-raw" src="' + _esc(rawUrl) + '" sandbox title="' + _esc(files[0]) + '"></iframe>';
      }
    }
    var fileList = files.map(function (f) { return '<li>' + _esc(f) + '</li>'; }).join('');
    reader.innerHTML =
      '<div class="axs-crumb"><b>📥 Inbox</b> › ' + _esc(env.intake_id || iid) + '</div>' +
      '<div class="axs-doc axs-env">' +
      '  <div class="axs-fm">' + chips + '</div>' +
      '  <h1 class="axs-title">' + _esc(caption) + '</h1>' +
      (fileList ? '<ul class="axs-env-files">' + fileList + '</ul>' : '') +
      body +
      '  <div class="axs-env-note">Aguardando triagem (Fase 2b). Nada foi escrito na memória semântica.</div>' +
      '</div>';
  }
  window.acervoStudioOpenEnvelope = acervoStudioOpenEnvelope;

  // ── Phase 2a: intake capture ─────────────────────────────────────────────
  function _readFileB64(file) {
    return new Promise(function (resolve, reject) {
      var fr = new FileReader();
      fr.onload = function () {
        var res = String(fr.result || '');
        var comma = res.indexOf(',');
        resolve(comma >= 0 ? res.slice(comma + 1) : res);  // strip data: prefix
      };
      fr.onerror = function () { reject(fr.error || new Error('read failed')); };
      fr.readAsDataURL(file);
    });
  }

  function acervoStudioCapture() {
    var root = _root();
    var reader = root && root.querySelector('[data-axs="reader"]');
    if (!reader) return;
    AXS.selectedPath = ''; AXS.page = null; AXS.artifactId = '';
    reader.innerHTML =
      '<div class="axs-crumb"><b>📥 Inbox</b> › Capturar</div>' +
      '<div class="axs-doc axs-cap">' +
      '  <div class="axs-cap-tabs">' +
      '    <button type="button" class="on" data-cap="text">Texto</button>' +
      '    <button type="button" data-cap="link">Link</button>' +
      '    <button type="button" data-cap="file">Arquivo</button>' +
      '  </div>' +
      '  <label class="axs-field"><span>Legenda (opcional)</span>' +
      '    <input type="text" data-cap-fm="caption" placeholder="do que se trata?"></label>' +
      '  <div data-cap-pane="text">' +
      '    <label class="axs-field axs-fgrow"><span>Texto</span>' +
      '      <textarea data-cap-fm="text" spellcheck="false" placeholder="cole ou escreva…"></textarea></label>' +
      '  </div>' +
      '  <div data-cap-pane="link" hidden>' +
      '    <label class="axs-field"><span>URL</span>' +
      '      <input type="url" data-cap-fm="url" placeholder="https://…"></label>' +
      '  </div>' +
      '  <div data-cap-pane="file" hidden>' +
      '    <label class="axs-field"><span>Arquivo (até 25 MB)</span>' +
      '      <input type="file" data-cap-fm="file"></label>' +
      '  </div>' +
      '  <div class="axs-acts"><button type="button" class="axs-act axs-act-primary" ' +
      '     data-cap-submit>Capturar</button></div>' +
      '</div>';
    var kind = { v: 'text' };
    reader.querySelectorAll('[data-cap]').forEach(function (b) {
      b.addEventListener('click', function () {
        kind.v = b.getAttribute('data-cap');
        reader.querySelectorAll('[data-cap]').forEach(function (x) {
          x.classList.toggle('on', x === b);
        });
        reader.querySelectorAll('[data-cap-pane]').forEach(function (p) {
          p.hidden = p.getAttribute('data-cap-pane') !== kind.v;
        });
      });
    });
    reader.querySelector('[data-cap-submit]')
      .addEventListener('click', function () { acervoStudioSubmitCapture(kind.v); });
  }
  window.acervoStudioCapture = acervoStudioCapture;

  async function acervoStudioSubmitCapture(kind) {
    var root = _root();
    var reader = root && root.querySelector('[data-axs="reader"]');
    if (!reader) return;
    var caption = (reader.querySelector('[data-cap-fm="caption"]') || {}).value || '';
    var url, body;
    if (kind === 'text') {
      var text = (reader.querySelector('[data-cap-fm="text"]') || {}).value || '';
      if (!text.trim()) { _toast('Escreva algum texto', 'error'); return; }
      url = '/api/acervo/x/intake/text';
      body = { session_id: _sid(), caption: caption, text: text };
    } else if (kind === 'link') {
      var u = (reader.querySelector('[data-cap-fm="url"]') || {}).value || '';
      if (!u.trim()) { _toast('Informe uma URL', 'error'); return; }
      url = '/api/acervo/x/intake/link';
      body = { session_id: _sid(), caption: caption, url: u.trim() };
    } else {
      var fi = reader.querySelector('[data-cap-fm="file"]');
      var file = fi && fi.files && fi.files[0];
      if (!file) { _toast('Escolha um arquivo', 'error'); return; }
      if (file.size > 25 * 1024 * 1024) { _toast('Arquivo acima de 25 MB', 'error'); return; }
      var b64;
      try { b64 = await _readFileB64(file); }
      catch (e) { _toast('Falha ao ler o arquivo' + _detail(e), 'error'); return; }
      url = '/api/acervo/x/intake/upload';
      body = { session_id: _sid(), caption: caption, filename: file.name,
               mime: file.type || '', content_b64: b64 };
    }
    try {
      await api(url, { method: 'POST', body: JSON.stringify(body) });
    } catch (e) { _toast('Falha ao capturar' + _detail(e), 'error'); return; }
    _toast('Capturado no inbox', 'success');
    AXS.scope = 'inbox';
    if (typeof acervoStudioRenderNav === 'function') await acervoStudioRenderNav();
  }
  window.acervoStudioSubmitCapture = acervoStudioSubmitCapture;

  function acervoStudioToggle() { if (AXS.open) _close(); else _open(); }
  window.acervoStudioToggle = acervoStudioToggle;

  // Expose module internals to later-task render functions in this IIFE.
  window.__AXS = { state: AXS, sid: _sid, esc: _esc, toast: _toast, root: _root };

  window.addEventListener('beforeunload', function (e) {
    if (AXS.open && AXS.dirty) { e.preventDefault(); e.returnValue = ''; return ''; }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _ensureLauncher);
  } else {
    _ensureLauncher();
  }
})();
