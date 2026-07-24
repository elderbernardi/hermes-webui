/* EXCRTX MOD-011 (spike F0) — Canvas de Tarefas: render mínimo. Global CVT, namespace .cvt-* */
(function () {
  "use strict";
  const $ = (sel) => document.querySelector(sel);
  let canvas = null;

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

  function zona(titulo, corpoHtml) {
    return `<div class="cvt-zona"><h2>${titulo}</h2>${corpoHtml}</div>`;
  }

  function render() {
    if (!canvas) return;
    const micro = (canvas.microversos && canvas.microversos.primary) || "—";
    const gaps = (canvas.gaps || [])
      .map((g) => `<li>${g}</li>`).join("") || "<li>—</li>";
    $("#cvt-canvas").innerHTML =
      zona("Foco", `<p>${canvas.focus || "…"}</p>`) +
      zona("Vetor", `<p class="cvt-vetor cvt-vetor-${canvas.vector}">` +
        `${canvas.vector || "…"} · ${canvas.intent_type || ""}</p>`) +
      zona("Microverso âncora", `<p>${micro}</p>`) +
      zona("Lacunas", `<ul>${gaps}</ul>`);
  }

  async function iniciar() {
    const texto = $("#cvt-input").value.trim();
    if (!texto) return;
    $("#cvt-status").textContent = "enquadrando…";
    const r = await fetch("/api/canvas/draft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: texto }),
    });
    const { canvas_id: cid } = await r.json();
    const es = new EventSource(
      "/api/canvas/stream?canvas_id=" + encodeURIComponent(cid));
    es.addEventListener("canvas_snapshot", (e) => {
      canvas = JSON.parse(e.data); render();
    });
    es.addEventListener("canvas_delta", (e) => {
      applyPatch(canvas, JSON.parse(e.data)); render();
    });
    es.addEventListener("canvas_done", (e) => {
      const d = JSON.parse(e.data);
      $("#cvt-status").textContent = d.valid
        ? "✓ canvas válido (schema v0.4)"
        : "⚠ inválido: " + d.errors.join("; ");
      es.close();
    });
  }

  window.CVT = { iniciar, applyPatch };
  document.addEventListener("DOMContentLoaded", () => {
    $("#cvt-go").addEventListener("click", iniciar);
    $("#cvt-input").addEventListener("keydown", (e) => {
      if (e.key === "Enter") iniciar();
    });
  });
})();
