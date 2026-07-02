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
