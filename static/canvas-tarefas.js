/* EXCRTX MOD-011 (F1) — Canvas de Tarefas: Hangar (lobby) + Cockpit (sala ativa).
 * Global window.CVT, namespace .cvt-*. IIFE, sem dependências novas, sem build.
 * Mirrors acervo-studio.js's surface pattern (reparent-to-body dialog + own
 * floating launcher + best-effort runtime injection into the Studio's mode
 * bar) but does NOT edit acervo-studio.js/ui.js/messages.js/index.html.
 */
(function () {
  "use strict";

  // Rule 1: every dynamic value that lands in an innerHTML template goes
  // through esc() — closes the F0 self-XSS (unescaped focus/gaps/etc.).
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));

  const VETOR_OPTS = ["execucao", "evolucao", "manutencao", "ambiguo"];
  const INTENT_OPTS = ["explorar", "decidir", "produzir", "revisar", "manter",
    "publicar", "ingestao", "outro"];
  const SHAPE_OPTS = ["pergunta", "plano-primeiro", "tarefa"];

  // Editable scalar zones — mirrors the server whitelist in canvas_tarefas.py
  // (_WHITELIST_RAW). done_criteria/verification are rendered separately
  // (Zona Pronto, rule 7) but stay in this table so startEdit() can look
  // them up uniformly regardless of which zone drew them.
  const FIELDS = [
    { path: "/focus", label: "Foco" },
    { path: "/vetor", label: "Vetor", options: VETOR_OPTS },
    { path: "/intent_type", label: "Tipo de intenção", options: INTENT_OPTS },
    { path: "/shape", label: "Formato", options: SHAPE_OPTS },
    { path: "/microversos/primary", label: "Microverso âncora" },
    { path: "/done_criteria", label: "Pronto quando" },
    { path: "/verification", label: "Verificação" },
  ];
  const FIELD_BY_PATH = {};
  FIELDS.forEach((f) => { FIELD_BY_PATH[f.path] = f; });
  const GRID_FIELDS = FIELDS.filter(
    (f) => f.path !== "/done_criteria" && f.path !== "/verification");

  const LIST_FIELDS = [
    { path: "/gaps", label: "Lacunas" },
    { path: "/scope", label: "Escopo" },
    { path: "/assumptions", label: "Suposições" },
    { path: "/microversos/related", label: "Microversos de apoio" },
    { path: "/artifacts/expected", label: "Artefatos esperados" },
    { path: "/next_moves", label: "Próximos passos" },
  ];

  const RECONNECT_MS = 1500;

  let canvas = null;
  const state = {
    built: false, open: false, view: "hangar", cid: "",
    es: null, cursor: 0, reconnectTimer: null,
    valid: null, errors: [],
  };

  // ── RFC 6902 subset (from F0 — reused verbatim, exposed as CVT.applyPatch) ──
  function applyPatch(doc, ops) {
    for (const op of ops) {
      const parts = op.path.split("/").slice(1)
        .map((p) => p.replace(/~1/g, "/").replace(/~0/g, "~"));
      let parent = doc;
      for (const part of parts.slice(0, -1)) {
        parent = parent[Array.isArray(parent) ? Number(part) : part];
      }
      const key = parts[parts.length - 1];
      if (Array.isArray(parent)) {
        const idx = key === "-" ? parent.length : Number(key);
        if (op.op === "add") parent.splice(idx, 0, op.value);
        else if (op.op === "replace") parent[idx] = op.value;
        else if (op.op === "remove") parent.splice(idx, 1);
      } else if (op.op === "remove") {
        delete parent[key];
      } else {
        parent[key] = op.value;
      }
    }
  }

  function ptrGet(doc, path) {
    const parts = path.split("/").slice(1)
      .map((p) => p.replace(/~1/g, "/").replace(/~0/g, "~"));
    let cur = doc;
    for (const part of parts) {
      if (cur == null) return undefined;
      cur = cur[Array.isArray(cur) ? Number(part) : part];
    }
    return cur;
  }

  // ── fetch helpers — plain fetch (not the app's api() helper: canvas-dev.html
  // runs standalone, without workspace.js loaded) ─────────────────────────
  async function getJSON(url) {
    const r = await fetch(url);
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || ("HTTP " + r.status));
    return data;
  }
  async function postJSON(url, body) {
    const r = await fetch(url, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || ("HTTP " + r.status));
    return data;
  }

  function _root() { return document.getElementById("canvasRoot"); }
  function _toast(msg) {
    if (typeof showToast === "function") showToast(msg, 4000, "success");
    else status(msg);
  }
  function status(msg, bad) {
    const el = _root() && _root().querySelector("#cvt-status");
    if (!el) return;
    el.textContent = msg || "";
    el.classList.toggle("cvt-status-bad", !!bad);
  }
  function setValidity(valid, errors) {
    state.valid = valid == null ? null : !!valid;
    state.errors = errors || [];
  }

  // ── zona/render helpers ──────────────────────────────────────────────────
  function zona(titulo, corpoHtml) {
    return `<div class="cvt-zona"><h2>${esc(titulo)}</h2>${corpoHtml}</div>`;
  }

  function editableSpanHtml(path, val) {
    const shown = (val == null || val === "") ? "…" : String(val);
    return `<span class="cvt-field" data-field="${esc(path)}">` +
      `<span class="cvt-edit" contenteditable="false">${esc(shown)}</span>` +
      `<button type="button" class="cvt-pencil" aria-label="Editar">✎</button></span>`;
  }

  function fieldZoneHtml(f) {
    return zona(f.label, editableSpanHtml(f.path, ptrGet(canvas, f.path)));
  }

  function listZoneHtml(f) {
    const arr = ptrGet(canvas, f.path) || [];
    const items = arr.map((v, i) =>
      `<li>${esc(v)}<button type="button" class="cvt-x" data-list="${esc(f.path)}" ` +
      `data-idx="${i}" aria-label="Remover">×</button></li>`
    ).join("") || '<li class="cvt-empty">—</li>';
    return zona(f.label, `<ul class="cvt-list">${items}</ul>` +
      `<input type="text" class="cvt-add" data-list="${esc(f.path)}" placeholder="+ adicionar">`);
  }

  function doneZoneHtml() {
    const done = canvas.done_criteria, verif = canvas.verification;
    const chip = (!done && !verif) ? '<span class="cvt-chip-amber">definir pronto</span>' : "";
    return `<h2>Pronto ${chip}</h2>` +
      `<div class="cvt-pronto-row"><label class="cvt-row-label">Quando</label>` +
      editableSpanHtml("/done_criteria", done) + "</div>" +
      `<div class="cvt-pronto-row"><label class="cvt-row-label">Verificação</label>` +
      editableSpanHtml("/verification", verif) + "</div>";
  }

  function ambiguousCardHtml() {
    return '<div class="cvt-ambig"><p>Vetor ambíguo — como tratar esta tarefa?</p>' +
      '<button type="button" class="cvt-ambig-btn" data-vetor="execucao">Executar</button>' +
      '<button type="button" class="cvt-ambig-btn" data-vetor="evolucao">Explorar</button>' +
      '<button type="button" class="cvt-ambig-btn" data-vetor="manutencao">Manter</button></div>';
  }

  function cockpitHeaderHtml() {
    let badge = "";
    if (state.valid === true) badge = '<span class="cvt-badge cvt-badge-ok">✓ válido</span>';
    else if (state.valid === false) {
      badge = `<span class="cvt-badge cvt-badge-bad">⚠ ${esc(String(state.errors.length))} erro(s)</span>`;
    }
    return '<div class="cvt-cockpit-head"><button type="button" id="cvt-back" ' +
      `class="cvt-link">← Hangar</button>${badge}</div>`;
  }

  function briefSectionHtml() {
    return '<div class="cvt-brief"><button type="button" id="cvt-brief-btn" class="cvt-btn">' +
      'Preview do brief</button><pre id="cvt-brief-pre" class="cvt-brief-pre" hidden></pre></div>';
  }
  function launchSectionHtml() {
    return '<div class="cvt-launch" id="cvt-launch-wrap"><button type="button" ' +
      'id="cvt-launch-btn" class="cvt-btn cvt-btn-primary">Lançar</button></div>';
  }

  function renderCockpit() {
    if (!canvas) return;
    const el = _root().querySelector("#cvt-cockpit");
    let html = cockpitHeaderHtml();
    if (canvas.vetor === "ambiguo") html += ambiguousCardHtml();
    html += '<div class="cvt-canvas">' + GRID_FIELDS.map(fieldZoneHtml).join("") + "</div>";
    html += '<div class="cvt-zona cvt-zona-pronto">' + doneZoneHtml() + "</div>";
    html += '<div class="cvt-canvas">' + LIST_FIELDS.map(listZoneHtml).join("") + "</div>";
    html += briefSectionHtml() + launchSectionHtml();
    el.innerHTML = html;
  }

  function cardHtml(c) {
    const focus = c.focus || "(sem foco)";
    const vetor = c.vetor || "";
    return `<div class="cvt-card" data-cid="${esc(c.canvas_id)}">` +
      `<div class="cvt-card-focus">${esc(focus)}</div><div class="cvt-card-meta">` +
      `<span class="cvt-vetor cvt-vetor-${esc(vetor)}">${esc(vetor || "—")}</span>` +
      `<span class="cvt-card-status">${esc(c.status || "")}</span></div></div>`;
  }

  async function renderHangar() {
    const el = _root().querySelector("#cvt-hangar");
    el.innerHTML = '<p class="cvt-empty">carregando…</p>';
    let list;
    try { list = await getJSON("/api/canvas/list"); }
    catch (e) { el.innerHTML = '<p class="cvt-empty">erro ao listar tarefas</p>'; return; }
    el.innerHTML = list.length
      ? '<div class="cvt-cards">' + list.map(cardHtml).join("") + "</div>"
      : '<p class="cvt-empty">Nenhuma tarefa ainda — descreva algo acima para começar.</p>';
  }

  function switchView(view) {
    const root = _root();
    root.querySelector("#cvt-hangar").hidden = view !== "hangar";
    root.querySelector("#cvt-cockpit").hidden = view !== "cockpit";
    state.view = view;
  }

  // ── edição in-loco (rule 6) ──────────────────────────────────────────────
  function startEdit(wrap) {
    const path = wrap.dataset.field;
    const val = ptrGet(canvas, path);
    const conf = FIELD_BY_PATH[path];
    const input = (conf && conf.options)
      ? document.createElement("select") : document.createElement("input");
    if (conf && conf.options) {
      conf.options.forEach((o) => input.appendChild(new Option(o, o, false, o === val)));
    } else {
      input.type = "text";
      input.value = val == null ? "" : val;
    }
    input.className = "cvt-input";
    wrap.innerHTML = "";
    wrap.appendChild(input);
    input.focus();
    let done = false;
    const commit = () => { if (done) return; done = true; submitOps([{ op: "replace", path, value: input.value }]); };
    const cancel = () => { if (done) return; done = true; renderCockpit(); };
    input.addEventListener("blur", commit);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); commit(); input.blur(); }
      else if (e.key === "Escape") { e.preventDefault(); cancel(); }
    });
  }

  async function submitOps(ops) {
    try {
      const r = await postJSON("/api/canvas/patch", { canvas_id: state.cid, ops });
      applyPatch(canvas, ops);
      setValidity(r.valid, r.errors);
      status("");
    } catch (e) {
      status("erro ao salvar: " + e.message, true);
    }
    renderCockpit();
  }
  const addItem = (path, value) => submitOps([{ op: "add", path: path + "/-", value }]);
  const removeItem = (path, idx) => submitOps([{ op: "remove", path: path + "/" + idx }]);

  async function toggleBrief() {
    const pre = _root().querySelector("#cvt-brief-pre");
    if (!pre.hidden) { pre.hidden = true; return; }
    pre.hidden = false;
    pre.innerHTML = esc("carregando…");
    try {
      const r = await getJSON("/api/canvas/brief?canvas_id=" + encodeURIComponent(state.cid));
      pre.innerHTML = esc(r.brief);
    } catch (e) {
      pre.innerHTML = esc("erro ao gerar o brief: " + e.message);
    }
  }

  function showGotoChat(sid) {
    const wrap = _root().querySelector("#cvt-launch-wrap");
    if (!wrap) return;
    wrap.innerHTML = `<button type="button" id="cvt-goto-chat" class="cvt-btn cvt-btn-primary" ` +
      `data-sid="${esc(sid)}">Ir para o chat</button>`;
  }

  async function launchCanvas() {
    status("lançando…");
    let res;
    try { res = await postJSON("/api/canvas/launch", { canvas_id: state.cid }); }
    catch (e) { status("erro ao lançar: " + e.message, true); return; }
    try {
      await postJSON("/api/chat/start",
        { session_id: res.session_id, message: res.brief, attachments: res.attachments });
    } catch (e) { status("erro ao iniciar o chat: " + e.message, true); return; }
    status("");
    _toast("Cockpit lançada — sessão " + res.session_id);
    showGotoChat(res.session_id);
  }

  function backToHangar() { _closeStream(); switchView("hangar"); renderHangar(); }

  function onCockpitClick(e) {
    const editEl = e.target.closest(".cvt-edit, .cvt-pencil");
    if (editEl) { const wrap = editEl.closest(".cvt-field"); if (wrap) startEdit(wrap); return; }
    const xBtn = e.target.closest(".cvt-x");
    if (xBtn) { removeItem(xBtn.dataset.list, Number(xBtn.dataset.idx)); return; }
    const ambigBtn = e.target.closest(".cvt-ambig-btn");
    if (ambigBtn) { submitOps([{ op: "replace", path: "/vetor", value: ambigBtn.dataset.vetor }]); return; }
    if (e.target.closest("#cvt-brief-btn")) { toggleBrief(); return; }
    if (e.target.closest("#cvt-launch-btn")) { launchCanvas(); return; }
    const goto = e.target.closest("#cvt-goto-chat");
    if (goto) {
      const sid = goto.dataset.sid;
      _close();
      if (typeof loadSession === "function") loadSession(sid);
      else status("Abra a sessão " + sid + " manualmente no Chat.");
      return;
    }
    if (e.target.closest("#cvt-back")) backToHangar();
  }
  function onCockpitKeydown(e) {
    if (e.key === "Enter" && e.target.classList.contains("cvt-add")) {
      e.preventDefault();
      const val = e.target.value.trim();
      if (val) addItem(e.target.dataset.list, val);
    }
  }

  // ── stream (rule 5): reattach on error via the last-seen cursor; re-entrancy
  // guard closes any previous EventSource before opening a new one ──────────
  function _closeStream() {
    clearTimeout(state.reconnectTimer);
    state.reconnectTimer = null;
    if (state.es) { state.es.close(); state.es = null; }
  }

  function openStream(cid, cursor) {
    _closeStream();
    const es = new EventSource(
      "/api/canvas/stream?canvas_id=" + encodeURIComponent(cid) + "&since=" + cursor);
    state.es = es;
    const onFrame = (name) => (e) => {
      if (e.lastEventId) state.cursor = Number(e.lastEventId);
      if (name === "canvas_snapshot") canvas = JSON.parse(e.data);
      else if (name === "canvas_delta") applyPatch(canvas, JSON.parse(e.data));
      else if (name === "canvas_validity") {
        const d = JSON.parse(e.data); setValidity(d.valid, d.errors);
      } else if (name === "canvas_done") {
        const d = JSON.parse(e.data);
        setValidity(d.valid, d.errors);
        status(d.valid ? "✓ canvas válido (schema v0.4)" : "⚠ inválido: " + d.errors.join("; "));
        _closeStream();
      } else if (name === "canvas_launched") {
        const d = JSON.parse(e.data);
        status("lançada — sessão " + d.session_id);
      }
      renderCockpit();
    };
    ["canvas_snapshot", "canvas_delta", "canvas_validity", "canvas_done", "canvas_launched"]
      .forEach((name) => es.addEventListener(name, onFrame(name)));
    es.onerror = () => {
      if (state.es !== es) return;
      status("reconectando…", true);
      es.close();
      state.es = null;
      state.reconnectTimer = setTimeout(() => {
        if (state.cid === cid) openStream(cid, state.cursor);
      }, RECONNECT_MS);
    };
  }

  // ── entry points exposed on window.CVT (rule 1) ─────────────────────────
  async function iniciar() {
    const input = _root().querySelector("#cvt-input");
    const texto = input.value.trim();
    if (!texto) return;
    _closeStream();
    status("enquadrando…");
    let r;
    try { r = await postJSON("/api/canvas/draft", { text: texto }); }
    catch (e) { status("erro ao enquadrar: " + e.message, true); return; }
    input.value = "";
    abrirCockpit(r.canvas_id);
  }

  async function abrirCockpit(cid) {
    _build();
    const root = _root();
    root.hidden = false;
    state.open = true;
    _showLauncher(false);
    _closeStream();
    state.cid = cid;
    state.cursor = 0;
    setValidity(null, []);
    switchView("cockpit");
    status("carregando…");
    try {
      canvas = await getJSON("/api/canvas/get?canvas_id=" + encodeURIComponent(cid));
    } catch (e) { status("canvas não encontrado", true); return; }
    renderCockpit();
    let job = null;
    try { job = await getJSON("/api/canvas/job?canvas_id=" + encodeURIComponent(cid)); }
    catch (e) { /* sem job ao vivo (draft antigo ou já limpo) */ }
    if (job && job.status === "running") {
      status("enquadrando…");
      openStream(cid, job.n_events || 0);
    } else if (job) {
      setValidity(job.valid, job.errors);
      status(job.valid ? "✓ canvas válido (schema v0.4)"
        : (job.errors || []).length ? "⚠ inválido: " + job.errors.join("; ") : "");
      renderCockpit();
    } else {
      status("");
    }
  }

  // ── surface (rule 2): reparent to <body>, dialog semantics ──────────────
  function _build() {
    if (state.built) return;
    let root = document.getElementById("canvasRoot");
    if (!root) { root = document.createElement("div"); root.id = "canvasRoot"; root.hidden = true; }
    if (root.parentElement !== document.body) document.body.appendChild(root);
    root.className = "cvt-root";
    root.setAttribute("role", "dialog");
    root.setAttribute("aria-modal", "true");
    root.setAttribute("aria-label", "Canvas de Tarefas");
    root.innerHTML =
      '<div class="cvt-top"><div class="cvt-mode">' +
      '<button type="button" data-cvt="chat">Chat</button>' +
      '<button type="button" data-cvt="acervo">Acervo</button>' +
      '<button type="button" class="on" data-cvt="canvas">Canvas</button></div>' +
      '<div class="cvt-intake"><input id="cvt-input" type="text" ' +
      'placeholder="O que vamos fazer?"><button type="button" id="cvt-go">Enquadrar</button>' +
      "</div></div>" +
      '<p id="cvt-status" class="cvt-status"></p>' +
      '<div class="cvt-body"><div id="cvt-hangar"></div><div id="cvt-cockpit" hidden></div></div>';
    root.querySelector('[data-cvt="chat"]').addEventListener("click", _close);
    root.querySelector('[data-cvt="acervo"]').addEventListener("click", () => {
      _close();
      if (typeof acervoStudioToggle === "function") acervoStudioToggle();
    });
    root.querySelector("#cvt-go").addEventListener("click", iniciar);
    root.querySelector("#cvt-input").addEventListener("keydown", (e) => {
      if (e.key === "Enter") iniciar();
    });
    root.querySelector("#cvt-hangar").addEventListener("click", (e) => {
      const card = e.target.closest(".cvt-card");
      if (card) abrirCockpit(card.dataset.cid);
    });
    root.querySelector("#cvt-cockpit").addEventListener("click", onCockpitClick);
    root.querySelector("#cvt-cockpit").addEventListener("keydown", onCockpitKeydown);
    root.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      const tag = (e.target && e.target.tagName || "").toLowerCase();
      if (tag !== "input" && tag !== "textarea" && tag !== "select") { e.preventDefault(); _close(); }
    });
    state.built = true;
  }

  function _open() {
    _build();
    _root().hidden = false;
    state.open = true;
    _showLauncher(false);
    switchView("hangar");
    renderHangar();
  }
  function _close() {
    _closeStream();
    const root = _root();
    if (root) root.hidden = true;
    state.open = false;
    _showLauncher(true);
  }
  function toggle() { if (state.open) _close(); else _open(); }

  // ── own launcher + degradable runtime injection into the Studio (rule 3) ─
  function _ensureLauncher() {
    if (document.getElementById("cvtLauncher")) return;
    const b = document.createElement("button");
    b.id = "cvtLauncher";
    b.className = "cvt-launcher";
    b.type = "button";
    b.title = "Abrir o Canvas de Tarefas";
    b.innerHTML = "<span>🗺️</span><span>Canvas</span>";
    b.addEventListener("click", toggle);
    document.body.appendChild(b);
  }
  function _showLauncher(show) {
    const b = document.getElementById("cvtLauncher");
    if (b) b.style.display = show ? "" : "none";
  }
  function _injectStudioButton() {
    const bar = document.querySelector("#acervoStudioRoot .axs-mode");
    if (!bar || bar.querySelector('[data-axs="canvas"]')) return;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.setAttribute("data-axs", "canvas");
    btn.textContent = "Canvas";
    btn.addEventListener("click", () => {
      if (typeof acervoStudioToggle === "function") acervoStudioToggle();
      toggle();
    });
    bar.appendChild(btn);
  }

  function _bootstrap() {
    _ensureLauncher();
    setTimeout(_injectStudioButton, 800);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", _bootstrap);
  else _bootstrap();

  window.CVT = { toggle, iniciar, abrirCockpit, applyPatch, esc };
})();
