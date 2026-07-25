/* EXCRTX MOD-013 (F2) — ilha do Curador: cards proativos (aceitar/dispensar).
 * IIFE, sem deps, sem build, PT-BR. 2ª EventSource própria (/api/canvas/curador/
 * stream); zona em container próprio (#cvt-curador-zone) que renderCockpit() não
 * reescreve. Aceitar roteia por window.CVT.acceptOps (fonte única do canvas).
 * NÃO edita os módulos quentes do Cockpit nem a folha de estilo/HTML principais. */
(function () {
  "use strict";
  const esc = (window.CVT && window.CVT.esc) || ((s) => String(s == null ? "" : s));
  const state = { cid: "", es: null, cursor: 0, sugestoes: {} };

  async function postJSON(url, body) {
    const r = await fetch(url, { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || ("HTTP " + r.status));
    return d;
  }

  function _zone() {
    let z = document.getElementById("cvt-curador-zone");
    if (!z) {
      const body = document.querySelector("#canvasRoot .cvt-body");
      if (!body) return null;
      z = document.createElement("div");
      z.id = "cvt-curador-zone";
      z.className = "cvt-zona cvt-curador-zone";
      body.appendChild(z);
      // minor: switchView (canvas-tarefas.js) só alterna #cvt-hangar/#cvt-cockpit e
      // não toca esta zona-irmã. Espelha o `hidden` do Cockpit p/ escondê-la fora dele.
      const cockpit = document.getElementById("cvt-cockpit");
      if (cockpit) {
        const sync = () => { z.hidden = cockpit.hidden; };
        sync();
        new MutationObserver(sync).observe(cockpit, {
          attributes: true, attributeFilter: ["hidden"] });
      }
    }
    return z;
  }

  function _canvasZones() {
    // renderiza /personas/suggested e /acervo_aplicado já aplicados (lidos do canvas)
    const c = (window.CVT && window.CVT.getCanvas && window.CVT.getCanvas()) || {};
    const personas = ((c.personas || {}).suggested || []);
    const aplicado = (c.acervo_aplicado || []);
    let html = "";
    if (personas.length) {
      html += "<h3>🎭 Personas</h3><ul>" +
        personas.map((p) => `<li>${esc(p)}</li>`).join("") + "</ul>";
    }
    if (aplicado.length) {
      html += "<h3>📚 Acervo aplicado</h3><ul>" +
        aplicado.map((a) => `<li>${esc(a.path)} — ${esc(a.porque || a.nature)}</li>`).join("") + "</ul>";
    }
    return html;
  }

  function render() {
    const z = _zone();
    if (!z) return;
    const cards = Object.values(state.sugestoes).map((s) => {
      const d = (s.parts && s.parts[0] && s.parts[0].data) || s;
      const untrusted = d.trust === "untrusted"
        ? '<span class="cvt-chip-amber">externo (confirme)</span>' : "";
      const fontes = (d.fontes || (d.path ? [d.path] : [])).map(esc).join(", ");
      return `<div class="cvt-sug" data-sid="${esc(s.artifactId || s.sugestao_id)}">` +
        `<div class="cvt-sug-porque">${esc(s.description || d.porque || "")} ${untrusted}</div>` +
        `<div class="cvt-sug-fonte">${esc(fontes)}</div>` +
        `<button type="button" class="cvt-sug-ok">Aceitar</button>` +
        `<button type="button" class="cvt-sug-no">Dispensar</button></div>`;
    }).join("");
    z.innerHTML = "<h2>Sugestões do Curador</h2>" +
      '<button type="button" id="cvt-cur-pedir" class="cvt-btn">Pedir sugestões</button>' +
      (cards || '<p class="cvt-empty">—</p>') + _canvasZones();
  }

  async function _accept(sid) {
    const s = state.sugestoes[sid];
    if (!s) return;
    const ops = (s.metadata && s.metadata.ops) || s.ops || [];
    if (ops.length && window.CVT && window.CVT.acceptOps) {
      try { await window.CVT.acceptOps(ops); } catch (_) { /* status já mostrado */ }
    }
    delete state.sugestoes[sid];
    render();
  }
  function _dismiss(sid) { delete state.sugestoes[sid]; render(); }

  async function pedirSugestoes() {
    if (!state.cid) return;
    try { await postJSON("/api/canvas/curador/delegar",
      { canvas_id: state.cid, kind: "sugerir_itens" }); }
    catch (_) { /* silencioso: card não aparece se falhar */ }
  }

  function _openStream(cid, cursor) {
    if (state.es) { state.es.close(); state.es = null; }
    const es = new EventSource("/api/canvas/curador/stream?canvas_id=" +
      encodeURIComponent(cid) + "&since=" + cursor);
    state.es = es;
    const onSug = (e) => {
      if (e.lastEventId) state.cursor = Number(e.lastEventId);
      const art = JSON.parse(e.data);
      state.sugestoes[art.artifactId || art.sugestao_id || String(state.cursor)] = art;
      render();
    };
    const onGap = (e) => {
      if (e.lastEventId) state.cursor = Number(e.lastEventId);
      const g = JSON.parse(e.data);
      state.sugestoes["gap-" + state.cursor] = {
        artifactId: "gap-" + state.cursor, description: "Lacuna: " + (g.motivo || ""),
        ops: g.ops, parts: [{ data: { porque: g.motivo } }] };
      render();
    };
    es.addEventListener("curador_sugestao", onSug);
    es.addEventListener("curador_gap", onGap);
    es.onerror = () => { es.close(); if (state.es === es) state.es = null; };
  }

  function _autoFireOnFraming(cid) {
    // best-effort: leitor transitório do stream do enquadrador só p/ captar
    // canvas_done e disparar 1 sugerir_itens; se a janela já passou, no-op.
    let es;
    try { es = new EventSource("/api/canvas/stream?canvas_id=" + encodeURIComponent(cid)); }
    catch (_) { return; }
    const done = () => { es.close(); pedirSugestoes(); };
    es.addEventListener("canvas_done", done);
    es.onerror = () => { es.close(); };
    setTimeout(() => { try { es.close(); } catch (_) {} }, 60000);
  }

  function onCockpitOpen(cid) {
    state.cid = cid;
    state.cursor = 0;
    state.sugestoes = {};
    render();
    _openStream(cid, 0);
    _autoFireOnFraming(cid);
  }

  document.addEventListener("click", (e) => {
    if (e.target.closest("#cvt-cur-pedir")) { pedirSugestoes(); return; }
    const ok = e.target.closest(".cvt-sug-ok");
    if (ok) { _accept(ok.closest(".cvt-sug").dataset.sid); return; }
    const no = e.target.closest(".cvt-sug-no");
    if (no) { _dismiss(no.closest(".cvt-sug").dataset.sid); return; }
  });

  window.CanvasCurador = { onCockpitOpen, pedirSugestoes };
})();
