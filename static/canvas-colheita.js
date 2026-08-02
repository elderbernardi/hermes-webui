/* EXCRTX MOD-017 (F4) — ilha da Colheita: bandeja de colheita de artefatos.
 * IIFE, sem deps, sem build, PT-BR. EventSource própria (/api/canvas/colheita/stream);
 * zona própria (#cvt-colheita-zone) que renderCockpit() reserva mas não reescreve.
 * Controles de checkout: [Preparar] → [Aprovar tudo | Item a item | Rejeitar].
 * Ação "colher" nos cards da Sala viva → POST /api/canvas/colheita/adotar.
 * Badge de gate por card (draft-first / forced-draft / auto).
 * NÃO edita módulos quentes nem style.css/index.html. */
(function () {
  "use strict";
  const esc = (window.CVT && window.CVT.esc) || ((s) => String(s == null ? "" : s));

  // ── state ───────────────────────────────────────────────────────────────────
  const state = { cid: "", es: null, cursor: 0, cards: {}, prepared: null, mode: null };
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
  function _cardHTML(id, c) {
    const badge = _gateBadge(c.gate);
    const title = `<div class="cvt-colheita-title">${esc(c.title || id)}${badge}</div>`;
    const sub = c.sub ? `<div class="cvt-colheita-sub">${esc(c.sub)}</div>` : "";
    const diffBtn = `<button type="button" class="cvt-colheita-diff" data-id="${esc(id)}">Ver diff</button>`;
    const diffPre = `<pre class="cvt-colheita-receipt" id="cvt-col-receipt-${esc(id)}" hidden></pre>`;
    // ação "colher" apenas em candidate / rejected
    const colherBtn = (c.kind === "candidate" || c.kind === "rejected")
      ? `<button type="button" class="cvt-colheita-colher" data-id="${esc(id)}">Colher</button>` : "";
    return `<div class="cvt-colheita-card cvt-colheita-${esc(c.kind)}" data-id="${esc(id)}">${title}${sub}${diffBtn}${diffPre}${colherBtn}</div>`;
  }

  // ── controles de checkout ───────────────────────────────────────────────────
  function _checkoutControlsHTML() {
    const hasPrepared = state.prepared && state.prepared.length;
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

  // ── stream ──────────────────────────────────────────────────────────────────
  function _openStream(cid) {
    if (state.es) { state.es.close(); state.es = null; }
    const es = new EventSource(
      "/api/canvas/colheita/stream?canvas_id=" + encodeURIComponent(cid) +
      "&since=" + state.cursor
    );
    state.es = es;
    const cur = (e) => { if (e.lastEventId) state.cursor = Number(e.lastEventId); };

    // ── evento: candidato para colheita (artefato produzido pela Sala) ──────
    es.addEventListener("colheita_candidate", (e) => {
      cur(e);
      const d = JSON.parse(e.data);
      _put("cand-" + (d.artifact_id || state.cursor), {
        kind: "candidate",
        title: "📦 " + (d.title || d.artifact_id || "artefato"),
        sub: d.path || "",
        gate: d.gate || "auto",
        artifact_id: d.artifact_id,
        receipt: d.receipt || null,
      });
    });

    // ── evento: preparado para checkout (após /preparar) ────────────────────
    es.addEventListener("colheita_prepared", (e) => {
      cur(e);
      const d = JSON.parse(e.data);
      state.prepared = d.items || [];
      _put("prep-" + state.cursor, {
        kind: "prepared",
        title: "✅ Pronto para checkout",
        sub: (d.items || []).length + " item(s)",
        gate: d.gate || null,
      });
    });

    // ── evento: artefato commitado com sucesso ──────────────────────────────
    es.addEventListener("colheita_committed", (e) => {
      cur(e);
      const d = JSON.parse(e.data);
      _put("comm-" + (d.artifact_id || state.cursor), {
        kind: "committed",
        title: "🎉 Commitado: " + (d.title || d.artifact_id || "artefato"),
        sub: d.ref || "",
        gate: null,
      });
    });

    // ── evento: artefato rejeitado ──────────────────────────────────────────
    es.addEventListener("colheita_rejected", (e) => {
      cur(e);
      const d = JSON.parse(e.data);
      _put("rej-" + (d.artifact_id || state.cursor), {
        kind: "rejected",
        title: "🚫 Rejeitado: " + (d.title || d.artifact_id || "artefato"),
        sub: d.reason || "",
        gate: null,
        artifact_id: d.artifact_id,
      });
    });

    es.onerror = () => { es.close(); if (state.es === es) state.es = null; };
  }

  // ── ações ───────────────────────────────────────────────────────────────────

  // "diff sob demanda": busca o receipt do card e exibe inline
  async function _showDiff(id) {
    const c = state.cards[id];
    const z = _zone();
    if (!c || !z) return;
    const pre = z.querySelector("#cvt-col-receipt-" + id);
    if (!pre) return;
    if (!pre.hidden) { pre.hidden = true; return; }
    if (c.receipt) { pre.textContent = c.receipt; pre.hidden = false; return; }
    // receipt não foi emitido inline → buscar via artifact_id
    if (c.artifact_id) {
      try {
        const r = await fetch("/api/canvas/colheita/receipt?artifact_id=" +
          encodeURIComponent(c.artifact_id));
        const d = await r.json().catch(() => ({}));
        pre.textContent = d.receipt || "(sem diff)";
      } catch (_) { pre.textContent = "(erro ao buscar diff)"; }
    } else {
      pre.textContent = "(sem diff disponível)";
    }
    pre.hidden = false;
  }

  // "colher" — adota artefato da Sala para a bandeja de Colheita
  async function _colher(id) {
    const c = state.cards[id];
    if (!c || !c.artifact_id) return;
    try {
      await postJSON("/api/canvas/colheita/adotar",
        { canvas_id: state.cid, artifact_id: c.artifact_id });
    } catch (_) {}
    delete state.cards[id]; render();
  }

  // preparar o checkout
  async function _preparar() {
    if (!state.cid) return;
    try {
      const d = await postJSON("/api/canvas/colheita/preparar", { canvas_id: state.cid });
      state.prepared = d.items || [];
      render();
    } catch (_) {}
  }

  // aprovar tudo de uma vez
  async function _aprovarTudo() {
    if (!state.cid) return;
    try {
      await postJSON("/api/canvas/colheita/checkout",
        { canvas_id: state.cid, mode: "all" });
      state.prepared = null; render();
    } catch (_) {}
  }

  // item a item: trocar para modo guiado
  function _itemAItem() {
    state.mode = "item-a-item";
    render();
  }

  // rejeitar tudo
  async function _rejeitarTudo() {
    if (!state.cid) return;
    try {
      await postJSON("/api/canvas/colheita/checkout",
        { canvas_id: state.cid, mode: "reject" });
      state.prepared = null; render();
    } catch (_) {}
  }

  // ── delegação de cliques ────────────────────────────────────────────────────
  document.addEventListener("click", (e) => {
    const diff = e.target.closest(".cvt-colheita-diff");
    if (diff) { _showDiff(diff.dataset.id); return; }

    const colher = e.target.closest(".cvt-colheita-colher");
    if (colher) { _colher(colher.dataset.id); return; }

    if (e.target.id === "cvt-col-preparar") { _preparar(); return; }
    if (e.target.id === "cvt-col-aprovar-tudo") { _aprovarTudo(); return; }
    if (e.target.id === "cvt-col-item-a-item") { _itemAItem(); return; }
    if (e.target.id === "cvt-col-rejeitar") { _rejeitarTudo(); return; }
  });

  // ── API pública ─────────────────────────────────────────────────────────────
  function onCockpitOpen(cid) {
    state.cid = cid; state.cursor = 0; state.cards = {};
    state.prepared = null; state.mode = null;
    render(); _openStream(cid);
  }

  // colherFromSala: exposta para a ilha da Sala acionar a Colheita diretamente
  function colherFromSala(artifactId, meta) {
    if (!artifactId) return;
    postJSON("/api/canvas/colheita/adotar",
      { canvas_id: state.cid, artifact_id: artifactId, meta: meta || {} }
    ).catch(() => {});
  }

  window.CanvasColheita = { onCockpitOpen, colherFromSala, renderColheita: render };
})();
