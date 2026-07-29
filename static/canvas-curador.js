/* EXCRTX MOD-013 (F2) evoluído por MOD-016 (C1) — Curador como HELPER de 1ª
 * classe: preenche os containers reservados por renderCockpit (#cvt-cur-acervo/
 * -personas/-skills/-sug) via getElementById. Sem zona-irmã, sem observer de mutação.
 * 2ª EventSource própria (/api/canvas/curador/stream). Aceitar roteia por
 * window.CVT.acceptOps (fonte única do canvas). IIFE, sem deps, sem build, PT-BR. */
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

  function _set(id, html) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;   // null-guard: no-op se o Cockpit não montou
  }

  function _liList(items, fmt) {
    if (!items.length) return '<p class="cvt-empty">—</p>';
    return '<ul class="cvt-cur-list">' + items.map(fmt).join("") + "</ul>";
  }

  function _sugCardsHtml() {
    return Object.values(state.sugestoes).map((s) => {
      const d = (s.parts && s.parts[0] && s.parts[0].data) || s;
      const untrusted = d.trust === "untrusted"
        ? '<span class="cvt-chip-amber">externo (confirme)</span>' : "";
      const fontes = (d.fontes || (d.path ? [d.path] : [])).map(esc).join(", ");
      return '<div class="cvt-sug" data-sid="' + esc(s.artifactId || s.sugestao_id) + '">' +
        '<div class="cvt-sug-porque">' + esc(s.description || d.porque || "") + " " + untrusted + "</div>" +
        '<div class="cvt-sug-fonte">' + esc(fontes) + "</div>" +
        '<button type="button" class="cvt-sug-ok">Aceitar</button>' +
        '<button type="button" class="cvt-sug-no">Dispensar</button></div>';
    }).join("");
  }

  function fill() {
    // fix-3: só pinta se a ilha aponta p/ o cockpit corrente; senão no-op (evita
    // first-paint com cards do canvas anterior antes de onCockpitOpen resetar).
    const curCid = (window.CVT && window.CVT.currentCid && window.CVT.currentCid()) || "";
    if (!state.cid || state.cid !== curCid) return;
    const c = (window.CVT && window.CVT.getCanvas && window.CVT.getCanvas()) || {};
    const aplicado = c.acervo_aplicado || [];
    const acervo = aplicado.filter((a) => (a.nature || "") !== "skill");
    const skills = aplicado.filter((a) => (a.nature || "") === "skill");   // SINGULAR
    const personas = (c.personas || {}).suggested || [];
    _set("cvt-cur-acervo", "<h2>📚 Acervo aplicado</h2>" +
      _liList(acervo, (a) => "<li>" + esc(a.path) + " — " + esc(a.porque || a.nature) + "</li>"));
    _set("cvt-cur-personas", "<h2>🎭 Personas</h2>" +
      _liList(personas, (p) => "<li>" + esc(p) + "</li>"));
    _set("cvt-cur-skills", "<h2>🛠️ Skills sugeridas</h2>" +
      _liList(skills, (a) => '<li class="cvt-cur-skill">' + esc(a.path) + " — " + esc(a.porque || "") + "</li>"));
    _set("cvt-cur-sug", "<h2>Sugestões do Curador</h2>" +
      '<button type="button" id="cvt-cur-pedir" class="cvt-btn">Atualizar</button>' +
      (_sugCardsHtml() || '<p class="cvt-empty">—</p>'));
  }

  async function _accept(sid) {
    const s = state.sugestoes[sid];
    if (!s) return;
    const ops = (s.metadata && s.metadata.ops) || s.ops || [];
    delete state.sugestoes[sid];   // fix: remove antes p/ um único paint consistente
    fill();
    if (ops.length && window.CVT && window.CVT.acceptOps) {
      try { await window.CVT.acceptOps(ops); } catch (_) { /* status já mostrado */ }
    }
  }
  function _dismiss(sid) { delete state.sugestoes[sid]; fill(); }

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
      fill();
    };
    const onGap = (e) => {
      if (e.lastEventId) state.cursor = Number(e.lastEventId);
      const g = JSON.parse(e.data);
      state.sugestoes["gap-" + state.cursor] = {
        artifactId: "gap-" + state.cursor, description: "Lacuna: " + (g.motivo || ""),
        ops: g.ops, parts: [{ data: { porque: g.motivo } }] };
      fill();
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
    fill();
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

  window.CanvasCurador = { onCockpitOpen, pedirSugestoes, fill };
})();
