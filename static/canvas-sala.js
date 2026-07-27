/* EXCRTX MOD-014 (F3) — ilha da Sala viva: cards da execução ao vivo.
 * IIFE, sem deps, sem build, PT-BR. EventSource própria (/api/canvas/sala/stream);
 * zona própria (#cvt-sala-zone) que renderCockpit() não reescreve. Aceitar roteia
 * por window.CVT.acceptOps. HITL responde via /api/clarify/respond e /api/approval/
 * respond (endpoints existentes). NÃO edita módulos quentes nem style.css/index.html. */
(function () {
  "use strict";
  const esc = (window.CVT && window.CVT.esc) || ((s) => String(s == null ? "" : s));
  const state = { cid: "", sid: "", es: null, cursor: 0, cards: {}, phase: null };
  // M6: phase tokens are technical identifiers; show a PT-BR label to the user.
  const PHASE_PT = { classify: "classificar", define_done: "definir pronto", evidence: "evidência",
    decide: "decidir", act: "agir", verify: "verificar", report: "reportar" };

  async function postJSON(url, body) {
    const r = await fetch(url, { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || ("HTTP " + r.status));
    return d;
  }

  function _zone() {
    let z = document.getElementById("cvt-sala-zone");
    if (!z) {
      const body = document.querySelector("#canvasRoot .cvt-body");
      if (!body) return null;
      z = document.createElement("div");
      z.id = "cvt-sala-zone";
      z.className = "cvt-zona cvt-sala-zone";
      body.appendChild(z);
      const cockpit = document.getElementById("cvt-cockpit");
      if (cockpit) {
        const sync = () => { z.hidden = cockpit.hidden; };
        sync();
        new MutationObserver(sync).observe(cockpit, { attributes: true, attributeFilter: ["hidden"] });
      }
    }
    return z;
  }

  function _cardHTML(id, c) {
    const acc = c.ops && c.ops.length
      ? `<button type="button" class="cvt-sala-ok" data-id="${esc(id)}">Aceitar</button>` : "";
    const dismiss = `<button type="button" class="cvt-sala-no" data-id="${esc(id)}">Dispensar</button>`;
    let body = `<div class="cvt-sala-title">${esc(c.title)}</div><div class="cvt-sala-sub">${esc(c.sub || "")}</div>`;
    // M5: only clarify-backed cards can be answered; an empty_search gap has no clarify_id -> no dead-end input.
    if ((c.kind === "gap" || c.kind === "interrupt") && c.clarify_id) {
      body += `<input type="text" class="cvt-sala-resp" data-id="${esc(id)}" placeholder="Responder ao agente…">`;
    }
    if (c.kind === "draft") {
      body += `<textarea class="cvt-sala-drafttext" readonly>${esc(c.draft_text)}</textarea>` +
        `<input type="text" class="cvt-sala-auth" data-id="${esc(id)}" placeholder="Palavras exatas de autorização…">` +
        `<button type="button" class="cvt-sala-approve" data-id="${esc(id)}">Autorizar</button>`;
    }
    return `<div class="cvt-sala-card cvt-sala-${esc(c.kind)}" data-id="${esc(id)}">${body}${acc}${dismiss}</div>`;
  }

  function render() {
    const z = _zone();
    if (!z) return;
    const chip = state.phase
      ? `<span class="cvt-sala-chip" title="fase do loop">${esc(PHASE_PT[state.phase] || state.phase)}</span>` : "";
    const cards = Object.entries(state.cards).map(([id, c]) => _cardHTML(id, c)).join("");
    z.innerHTML = `<h2>Sala viva ${chip}</h2>` + (cards || '<p class="cvt-empty">—</p>');
  }

  function _put(id, card) { state.cards[id] = card; render(); }

  function _openStream(cid) {
    if (state.es) { state.es.close(); state.es = null; }
    const es = new EventSource("/api/canvas/sala/stream?canvas_id=" +
      encodeURIComponent(cid) + "&since=" + state.cursor);
    state.es = es;
    const cur = (e) => { if (e.lastEventId) state.cursor = Number(e.lastEventId); };
    const grab = (d) => { if (d.session_id) state.sid = d.session_id; };
    es.addEventListener("sala_phase", (e) => { cur(e); state.phase = JSON.parse(e.data).phase; render(); });
    es.addEventListener("sala_kanban", (e) => { cur(e); /* coluna projetada; chip de fase já cobre v1 */ });
    es.addEventListener("sala_artifact", (e) => { cur(e); const d = JSON.parse(e.data);
      _put("art-" + state.cursor, { kind: "artifact", title: "📄 " + d.title, sub: d.path, ops: d.ops }); });
    es.addEventListener("sala_next_move", (e) => { cur(e); const d = JSON.parse(e.data);
      _put("nm-" + state.cursor, { kind: "next_move", title: "➡️ " + d.text, ops: d.ops }); });
    es.addEventListener("sala_trace", (e) => { cur(e); const d = JSON.parse(e.data);
      _put("tr-" + state.cursor, { kind: "trace", title: "🔎 " + d.kind + ": " + d.title,
        sub: JSON.stringify(d.evidence), ops: d.ops || [] }); });
    es.addEventListener("sala_gap", (e) => { cur(e); const d = JSON.parse(e.data); grab(d);
      _put("gap-" + (d.clarify_id || state.cursor), { kind: "gap", title: "❓ " + d.question,
        clarify_id: d.clarify_id, ops: d.ops }); });
    es.addEventListener("sala_interrupt", (e) => { cur(e); const d = JSON.parse(e.data); grab(d);
      _put("int-" + (d.clarify_id || state.cursor), { kind: "interrupt",
        title: "🛑 " + (d.hypothesis || "bound atingido"), sub: (d.tried || ""),
        clarify_id: d.clarify_id, ops: d.ops }); });
    es.addEventListener("sala_draft", (e) => { cur(e); const d = JSON.parse(e.data); grab(d);
      _put("draft-" + (d.approval_id || state.cursor), { kind: "draft", title: "📋 DRAFT — " + d.action,
        draft_text: d.draft_text, approval_id: d.approval_id, action: d.action, session_id: d.session_id }); });
    es.addEventListener("sala_finding", (e) => { cur(e); const d = JSON.parse(e.data);
      _put("find-" + state.cursor, { kind: "finding", title: "⚠️ divergência: " + d.subject,
        sub: "código=" + d.code + " · check=" + d.check + " · spec=" + d.spec +
             " → autoridade: " + (d.authority || []).join(">") }); });
    es.onerror = () => { es.close(); if (state.es === es) state.es = null; };
  }

  async function _accept(id) {
    const c = state.cards[id];
    if (c && c.ops && c.ops.length && window.CVT && window.CVT.acceptOps) {
      try { await window.CVT.acceptOps(c.ops); } catch (_) {}
    }
    delete state.cards[id]; render();
  }

  async function _respond(id, text) {
    const c = state.cards[id];
    if (!c || !state.sid || !c.clarify_id) return;
    try { await postJSON("/api/clarify/respond",
      { session_id: state.sid, clarify_id: c.clarify_id, response: text }); } catch (_) {}
    delete state.cards[id]; render();
  }

  async function _approve(id, words) {
    const c = state.cards[id];
    if (!c) return;
    const sid = c.session_id || state.sid;
    // 1) if this draft came from a RUNTIME tool-permission gate, grant it.
    //    C4: the endpoint reads `choice` (once|session|always|deny), NOT `decision`;
    //    `choice:"once"` is the grant — `decision:"approve"` would default to deny.
    if (sid && c.approval_id) {
      try { await postJSON("/api/approval/respond",
        { session_id: sid, approval_id: c.approval_id, choice: "once" }); } catch (_) {}
    }
    // 2) record the executive's VERBATIM words into authorization[] (must-fix #5)
    if (words && window.CVT && window.CVT.acceptOps) {
      const at = new Date().toISOString();
      try { await window.CVT.acceptOps([{ op: "add", path: "/authorization/-",
        value: { action: c.action, words: words, at: at } }]); } catch (_) {}
    }
    delete state.cards[id]; render();
  }

  function onCockpitOpen(cid) {
    state.cid = cid; state.cursor = 0; state.cards = {}; state.phase = null;
    render(); _openStream(cid);
  }

  document.addEventListener("click", (e) => {
    const ok = e.target.closest(".cvt-sala-ok"); if (ok) { _accept(ok.dataset.id); return; }
    const no = e.target.closest(".cvt-sala-no"); if (no) { delete state.cards[no.dataset.id]; render(); return; }
    const ap = e.target.closest(".cvt-sala-approve");
    if (ap) { const inp = _zone().querySelector('.cvt-sala-auth[data-id="' + ap.dataset.id + '"]');
      _approve(ap.dataset.id, inp ? inp.value.trim() : ""); return; }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    const r = e.target.closest(".cvt-sala-resp");
    if (r) { _respond(r.dataset.id, r.value.trim()); }
  });

  window.CanvasSala = { onCockpitOpen };
})();
