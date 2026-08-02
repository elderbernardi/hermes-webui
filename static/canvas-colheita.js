/* EXCRTX MOD-017 (F4) — ilha da Colheita: bandeja de colheita de artefatos.
 * IIFE, sem deps, sem build, PT-BR. EventSource própria (/api/canvas/colheita/stream);
 * zona própria (#cvt-colheita-zone) que renderCockpit() reserva mas não reescreve.
 * Controles de checkout: [Preparar] → [Aprovar tudo | Item a item | Rejeitar].
 * Ação "colher" nos cards da Sala viva → POST /api/canvas/colheita/adotar.
 * Badge de gate por card (draft-first / forced-draft / auto).
 * NÃO edita módulos quentes nem style.css/index.html.
 *
 * CONTRATO DE BACKEND (api/canvas_colheita.py — fonte da verdade):
 *  - card = {id, nature, scope, title, porque, ref, body, class, source_trust,
 *            gate, status, origin} (+ receipt quando prepared).
 *  - SSE colheita_candidate  -> card (status "pending").
 *  - SSE colheita_prepared   -> {...card, status:"prepared", receipt}.
 *  - SSE colheita_committed  -> {...card, status, judge}.
 *  - SSE colheita_rejected   -> {...card, status:"rejected"}.
 *  - POST /adotar   {canvas_id, source_event:{...}, nature?, scope?}.
 *  - POST /preparar {canvas_id}   (prepara todos os pending).
 *  - POST /checkout {canvas_id, mode, decisions:[{card_id, action}]}
 *                   action ∈ {"aprovar","rejeitar"}; o backend itera decisions. */
(function () {
  "use strict";
  const esc = (window.CVT && window.CVT.esc) || ((s) => String(s == null ? "" : s));

  // ── state ───────────────────────────────────────────────────────────────────
  // cards indexados pelo id real do backend (h_<sha1>); status vem do card do backend.
  const state = { cid: "", es: null, cursor: 0, cards: {}, mode: null };
  // mode: null | "item-a-item" (controla aprovação um a um)
  const GATE_LABEL = { "draft-first": "rascunho primeiro", "forced-draft": "draft forçado", "auto": "automático" };

  // ── helpers ─────────────────────────────────────────────────────────────────
  async function postJSON(url, body) {
    const r = await fetch(url, { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || ("HTTP " + r.status));
    return d;
  }

  // "há cards preparados?" deriva do próprio status dos cards (nunca de state.prepared)
  function _preparedCards() {
    return Object.values(state.cards).filter((c) => c.status === "prepared");
  }

  function _zone() {
    let z = document.getElementById("cvt-colheita-zone");
    if (!z) {
      // tenta montar dentro do cvt-body do canvasRoot
      const body = document.querySelector("#canvasRoot .cvt-body");
      if (!body) return null;
      z = document.createElement("div");
      z.id = "cvt-colheita-zone";
      z.className = "cvt-zona cvt-colheita-zone";
      body.appendChild(z);
      // visibilidade atrelada ao cockpit
      const cockpit = document.getElementById("cvt-cockpit");
      if (cockpit) {
        const sync = () => { z.hidden = cockpit.hidden; };
        sync();
        new MutationObserver(sync).observe(cockpit, { attributes: true, attributeFilter: ["hidden"] });
      }
    }
    return z;
  }

  // ── badge de gate ───────────────────────────────────────────────────────────
  function _gateBadge(gate) {
    if (!gate) return "";
    const label = esc(GATE_LABEL[gate] || gate);
    return `<span class="cvt-colheita-badge cvt-colheita-badge-${esc(gate)}">${label}</span>`;
  }

  // ── renderers de card ───────────────────────────────────────────────────────
  // kind = status do backend (pending | prepared | committed | committed_unverified | rejected)
  function _cardHTML(id, c) {
    const kind = c.status || "pending";
    const badge = _gateBadge(c.gate);
    const title = `<div class="cvt-colheita-title">${esc(c.title || id)}${badge}</div>`;
    const sub = c.sub ? `<div class="cvt-colheita-sub">${esc(c.sub)}</div>` : "";
    const diffBtn = `<button type="button" class="cvt-colheita-diff" data-id="${esc(id)}">Ver diff</button>`;
    const diffPre = `<pre class="cvt-colheita-receipt" id="cvt-col-receipt-${esc(id)}" hidden></pre>`;
    // botões por card em modo item-a-item (apenas para cards prepared) —
    // data-id carrega o id REAL do backend (h_<sha1>), usado como card_id no checkout.
    const itemButtons = (state.mode === "item-a-item" && kind === "prepared")
      ? `<button type="button" class="cvt-colheita-aprovar-item cvt-btn cvt-btn-primary" data-id="${esc(id)}">Aprovar</button>` +
        `<button type="button" class="cvt-colheita-rejeitar-item cvt-btn cvt-colheita-btn-danger" data-id="${esc(id)}">Rejeitar</button>`
      : "";
    return `<div class="cvt-colheita-card cvt-colheita-${esc(kind)}" data-id="${esc(id)}">${title}${sub}${diffBtn}${diffPre}${itemButtons}</div>`;
  }

  // ── controles de checkout ───────────────────────────────────────────────────
  function _checkoutControlsHTML() {
    const hasPrepared = _preparedCards().length > 0;
    if (!hasPrepared) {
      return `<div class="cvt-colheita-controls">
        <button type="button" id="cvt-col-preparar" class="cvt-btn">Preparar</button>
      </div>`;
    }
    return `<div class="cvt-colheita-controls">
      <button type="button" id="cvt-col-aprovar-tudo" class="cvt-btn cvt-btn-primary">Aprovar tudo</button>
      <button type="button" id="cvt-col-item-a-item" class="cvt-btn">Item a item</button>
      <button type="button" id="cvt-col-rejeitar" class="cvt-btn cvt-colheita-btn-danger">Rejeitar</button>
    </div>`;
  }

  // ── render principal ─────────────────────────────────────────────────────────
  function render() {
    const z = _zone();
    if (!z) return;
    const cards = Object.entries(state.cards).map(([id, c]) => _cardHTML(id, c)).join("");
    const controls = _checkoutControlsHTML();
    z.innerHTML = `<h2>Colheita</h2>${controls}` +
      (cards || '<p class="cvt-empty">—</p>');
  }

  function _put(id, card) { state.cards[id] = card; render(); }

  // funde uma atualização de card do backend (mantém campos anteriores; usa o id real)
  function _upsert(d) {
    const id = d.id;
    if (!id) return;
    const prev = state.cards[id] || {};
    state.cards[id] = { ...prev, ...d };
    render();
  }

  // ── stream ──────────────────────────────────────────────────────────────────
  function _openStream(cid) {
    if (state.es) { state.es.close(); state.es = null; }
    const es = new EventSource(
      "/api/canvas/colheita/stream?canvas_id=" + encodeURIComponent(cid) +
      "&since=" + state.cursor
    );
    state.es = es;
    const cur = (e) => { if (e.lastEventId) state.cursor = Number(e.lastEventId); };

    // ── evento: candidato para colheita (card completo, status "pending") ────
    es.addEventListener("colheita_candidate", (e) => {
      cur(e);
      const d = JSON.parse(e.data);
      _upsert({
        id: d.id,
        title: "📦 " + (d.title || d.id || "artefato"),
        sub: d.porque || d.scope || d.ref || "",
        gate: d.gate || "auto",
        nature: d.nature,
        scope: d.scope,
        status: d.status || "pending",
        receipt: d.receipt || null,
      });
    });

    // ── evento: preparado para checkout (atualiza o card existente, anexa receipt) ──
    es.addEventListener("colheita_prepared", (e) => {
      cur(e);
      const d = JSON.parse(e.data);
      // ATUALIZA o card existente (achado pelo id real) → status "prepared" +
      // receipt, para que os botões Aprovar/Rejeitar por card apareçam.
      _upsert({
        id: d.id,
        title: "✅ " + (d.title || d.id || "artefato"),
        sub: d.porque || d.scope || "",
        gate: d.gate || null,
        status: d.status || "prepared",
        receipt: d.receipt || null,
      });
    });

    // ── evento: artefato commitado com sucesso ──────────────────────────────
    es.addEventListener("colheita_committed", (e) => {
      cur(e);
      const d = JSON.parse(e.data);
      _upsert({
        id: d.id,
        title: "🎉 Commitado: " + (d.title || d.id || "artefato"),
        sub: d.ref || d.scope || "",
        gate: null,
        status: d.status || "committed",
      });
    });

    // ── evento: artefato rejeitado ──────────────────────────────────────────
    es.addEventListener("colheita_rejected", (e) => {
      cur(e);
      const d = JSON.parse(e.data);
      _upsert({
        id: d.id,
        title: "🚫 Rejeitado: " + (d.title || d.id || "artefato"),
        sub: d.porque || d.scope || "",
        gate: null,
        status: d.status || "rejected",
      });
    });

    es.onerror = () => { es.close(); if (state.es === es) state.es = null; };
  }

  // ── ações ───────────────────────────────────────────────────────────────────

  // "diff sob demanda": exibe receipt inline se disponível no card
  async function _showDiff(id) {
    const c = state.cards[id];
    const z = _zone();
    if (!c || !z) return;
    const pre = z.querySelector("#cvt-col-receipt-" + id);
    if (!pre) return;
    if (!pre.hidden) { pre.hidden = true; return; }
    // usa apenas o receipt inline do evento SSE (colheita_prepared / colheita_candidate)
    // não há endpoint GET para buscar diff — exibe o que veio no payload ou mensagem padrão
    const rc = c.receipt;
    pre.textContent = rc ? (typeof rc === "string" ? rc : JSON.stringify(rc, null, 2)) : "(sem diff disponível)";
    pre.hidden = false;
  }

  // "colher" — adota artefato (da Sala) para a bandeja de Colheita.
  // Envia o body correto {canvas_id, source_event:{...}, nature?, scope?}.
  async function _colher(sourceEvent, nature, scope) {
    if (!state.cid) return;
    try {
      await postJSON("/api/canvas/colheita/adotar", {
        canvas_id: state.cid,
        source_event: sourceEvent || {},
        nature: nature || "knowledge",
        scope: scope || "",
      });
    } catch (_) {}
  }

  // preparar o checkout (prepara todos os pending no backend)
  async function _preparar() {
    if (!state.cid) return;
    try {
      await postJSON("/api/canvas/colheita/preparar", { canvas_id: state.cid });
      // o backend emite colheita_prepared por card → o stream atualiza o estado.
    } catch (_) {}
  }

  // constrói o array de decisions a partir de TODOS os cards atualmente prepared
  function _bulkDecisions(action) {
    return _preparedCards().map((c) => ({ card_id: c.id, action: action }));
  }

  // aprovar tudo de uma vez: envia decisions=[{card_id, action:"aprovar"} ...]
  async function _aprovarTudo() {
    if (!state.cid) return;
    const decisions = _bulkDecisions("aprovar");
    if (!decisions.length) return;
    try {
      await postJSON("/api/canvas/colheita/checkout",
        { canvas_id: state.cid, mode: "aprovar_tudo", decisions: decisions });
      // status vem do stream (colheita_committed); nada a limpar manualmente.
    } catch (_) {}
  }

  // item a item: trocar para modo guiado (per-card approval)
  function _itemAItem() {
    state.mode = "item-a-item";
    render();
  }

  // decisão individual: aprovar ou rejeitar um único card (card_id = id real)
  async function _decidirItem(cardId, action) {
    if (!state.cid || !cardId) return;
    try {
      await postJSON("/api/canvas/colheita/checkout", {
        canvas_id: state.cid,
        mode: "item_a_item",
        decisions: [{ card_id: cardId, action: action }],
      });
      // se não restam cards prepared, sair do modo item-a-item
      const remaining = _preparedCards().filter((c) => c.id !== cardId);
      if (!remaining.length) { state.mode = null; }
      render();
    } catch (_) {}
  }

  // rejeitar tudo: envia decisions=[{card_id, action:"rejeitar"} ...]
  async function _rejeitarTudo() {
    if (!state.cid) return;
    const decisions = _bulkDecisions("rejeitar");
    if (!decisions.length) return;
    try {
      await postJSON("/api/canvas/colheita/checkout",
        { canvas_id: state.cid, mode: "rejeitar_tudo", decisions: decisions });
    } catch (_) {}
  }

  // ── delegação de cliques ────────────────────────────────────────────────────
  document.addEventListener("click", (e) => {
    const diff = e.target.closest(".cvt-colheita-diff");
    if (diff) { _showDiff(diff.dataset.id); return; }

    const aprovarItem = e.target.closest(".cvt-colheita-aprovar-item");
    if (aprovarItem) { _decidirItem(aprovarItem.dataset.id, "aprovar"); return; }

    const rejeitarItem = e.target.closest(".cvt-colheita-rejeitar-item");
    if (rejeitarItem) { _decidirItem(rejeitarItem.dataset.id, "rejeitar"); return; }

    if (e.target.id === "cvt-col-preparar") { _preparar(); return; }
    if (e.target.id === "cvt-col-aprovar-tudo") { _aprovarTudo(); return; }
    if (e.target.id === "cvt-col-item-a-item") { _itemAItem(); return; }
    if (e.target.id === "cvt-col-rejeitar") { _rejeitarTudo(); return; }
  });

  // ── API pública ─────────────────────────────────────────────────────────────
  function onCockpitOpen(cid) {
    // idempotente: se já aberto para este cid com stream ativo, não faz nada (I3)
    if (state.cid === cid && state.es) return;
    state.cid = cid; state.cursor = 0; state.cards = {};
    state.mode = null;
    render(); _openStream(cid);
  }

  // colherFromSala: exposta para a ilha da Sala acionar a Colheita diretamente.
  // salaCard = dados identificadores do card da Sala (title + body/path);
  // vira o source_event do POST /adotar. nature/scope são editados na zona de
  // colheita antes do preparar, então aqui vão com defaults sensatos/em branco.
  function colherFromSala(salaCard, nature, scope) {
    if (!salaCard) return;
    const sc = salaCard || {};
    const source_event = {
      title: sc.title || sc.text || sc.subject || "",
      body: sc.body || sc.text || "",
      ref: sc.path || sc.ref || null,
    };
    return _colher(source_event, nature, scope);
  }

  window.CanvasColheita = { onCockpitOpen, colherFromSala, renderColheita: render };
})();
