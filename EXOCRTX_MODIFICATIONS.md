# EXOCRTX_MODIFICATIONS.md

Catálogo das modificações Exocórtex aplicadas sobre o fork de `nesquena/hermes-webui`.
Cada entrada documenta arquivo, propósito e risco de conflito para guiar o rebase
(`git rebase upstream/master`) e o comando `./ctl.sh update`.

- **Fork:** `elderbernardi/hermes-webui`
- **Branch de produção:** `exocortex/stable` (roda na porta 8787)
- **Base atual:** upstream `v0.51.440` (Release PA, commit `e47f685b`)
- **Política:** todas as modificações vivem no fork — sem PRs upstream (divergência arquitetural elevada).

> Convenção de commit: cada modificação carrega a tag `[MOD-NNN]` no assunto para rastreio no `git log`.

---

## Camada 1 — Skin EXCRTX (rebranding visual)

As cinco modificações abaixo introduzem a skin `excrtx` e o rebranding Hermes → EXCRTX.IA.

### MOD-001: Registrar skin `excrtx` no backend (v0.51.440 base)
- **Arquivos:** `api/config.py`
- **Tipo:** backend
- **Propósito:** adiciona `"excrtx"` ao conjunto `_SETTINGS_SKIN_VALUES` e define `"skin": "excrtx"` como default em `_SETTINGS_DEFAULTS`, para que a skin seja válida e ativa por padrão.
- **Reaplicar se:** upstream alterar `_SETTINGS_DEFAULTS` ou `_SETTINGS_SKIN_VALUES` (ex.: novas skins, refatoração de settings).
- **Conflito provável:** `api/config.py` — médio. Upstream mexe nessa lista ao adicionar skins próprias.

### MOD-002: Adicionar EXCRTX à lista de skins do frontend (v0.51.440 base)
- **Arquivos:** `static/boot.js`
- **Tipo:** frontend
- **Propósito:** adiciona a entrada `{name:'EXCRTX', value:'excrtx', colors:[...]}` ao array `_SKINS`, para a skin aparecer no seletor de aparência com as cores da marca.
- **Reaplicar se:** upstream adicionar/reordenar entradas em `_SKINS`.
- **Conflito provável:** `static/boot.js` — baixo. Inserção de uma linha no fim do array.

### MOD-003: Rebranding do shell para EXCRTX.IA (v0.51.440 base)
- **Arquivos:** `static/index.html`, `static/excrtx-logo.png`, `static/excrtx-titlebar.svg`
- **Tipo:** frontend + assets
- **Propósito:** substitui marca Hermes por EXCRTX.IA — `<title>`, ícone/título da titlebar (usa `excrtx-titlebar.svg`), logo do empty-state (usa `excrtx-logo.png`), headline `Exocórtex.IA — cognição estendida`, e ajusta default de skin/tema nos scripts inline de boot (`excrtx` / `light`).
- **Reaplicar se:** upstream alterar o markup da titlebar, do empty-state ou os scripts inline de inicialização de tema/skin.
- **Conflito provável:** `static/index.html` — alto. Os scripts inline de boot mudam com frequência no upstream e tocam exatamente as linhas modificadas.

### MOD-004: Folha de estilo da skin EXCRTX (v0.51.440 base)
- **Arquivos:** `static/style.css`
- **Tipo:** CSS
- **Propósito:** adiciona o bloco de variáveis/regras da skin `excrtx` (paleta da marca) ao final do stylesheet.
- **Reaplicar se:** upstream reestruturar o sistema de skins/tokens de cor em `style.css`.
- **Conflito provável:** `static/style.css` — baixo. Bloco aditivo no fim do arquivo.

### MOD-005: Listar skin `excrtx` no `cmd_theme` dos locales (v0.51.440 base)
- **Arquivos:** `static/i18n.js`
- **Tipo:** frontend (i18n)
- **Propósito:** acrescenta `/excrtx` à enumeração de skins na string `cmd_theme` em todos os idiomas, para a ajuda do comando refletir a skin disponível.
- **Reaplicar se:** upstream adicionar skins (muda a mesma string em todos os locales) ou novos idiomas.
- **Conflito provável:** `static/i18n.js` — médio. Mesma chave repetida por idioma; upstream toca nela ao introduzir skins.

### MOD-006: Tradução PT-BR completa — 125 chaves (v0.51.440 base)
- **Arquivos:** `static/i18n.js`
- **Tipo:** frontend (i18n)
- **Propósito:** traduzir 125 chaves faltantes no bloco `pt:` para PT-BR, elevando cobertura de 91.4% para 99.9%. Cobre MCP (59 chaves), excalidraw (9), insights (7), previews CSV/HTML/PDF (15), skills (5), YOLO (5), e 14 domínios menores. Termos técnicos mantidos em inglês (MCP, YOLO, tokens, CSV, HTML, PDF, diff, patch, sandbox, schema, runtime, stdio, timeout, job, archive).
- **Reaplicar se:** upstream adicionar novas chaves no bloco `en:` ou alterar a ordem dos blocos de locale.
- **Conflito provável:** `static/i18n.js` — baixo. Bloco aditivo no fim do locale `pt:`, sem alterar chaves existentes.

---

## Camada 2 — Funcionalidades Exocórtex

### MOD-007: Aba "Acervo" — catálogo humano de artefatos + export Drive
- **Arquivos:** `static/acervo.js` (novo), `api/routes.py` (handlers `_handle_acervo_artifacts` + `_handle_acervo_status` + dispatch `/api/acervo/artifacts` e `/api/acervo/status`), `static/index.html` (botão de aba + container `#workspaceAcervo` + include do script), `static/workspace.js` (caso `'acervo'` em `switchWorkspacePanelTab`), `static/style.css` (bloco `.acervo-*` + regras `data-active-tab="acervo"`).
- **Tipo:** frontend + backend (read + status-write) + CSS.
- **Propósito:** substituir a visão de árvore crua por um catálogo humano dos artefatos do Acervo. Lê o schema de `manifest.json` (`friendly_name`, `status`, `artifact_type`, `primary_microverso`, `task_id`, `evaluation`, `publication`, `provenance`) e renderiza: banda "Nesta sessão" (cruzando `collectSessionArtifacts()`), vistas Pipeline/Microverso/Tarefa/Galeria, cartões por nome amigável com pill de status e ícone de tipo, drawer de detalhe, e filtros de ruído (notas soltas e arquivados ocultos por padrão). Reusa `/api/artifact/zip` (#84) e `/api/artifact/publish` (#82) para baixar e publicar no Drive (Draft-First). `/api/acervo/status` muda o campo `status` do manifest (draft/ready/archived) validando com `validate_artifact_manifest.py` — promover/arquivar/restaurar; quarentena/purge destrutivos ficam com o `excrtx-memory-syndic`.
- **Reaplicar se:** upstream reestruturar `switchWorkspacePanelTab`/as abas do painel direito, ou o dispatcher de rotas GET em `routes.py`.
- **Conflito provável:** `static/index.html` — médio (bloco de abas e includes de script mudam no upstream). `static/workspace.js` — médio (a função de troca de aba). `api/routes.py`, `static/acervo.js`, `static/style.css` — baixo (aditivos). Registro COLLAB: `.harness/changes/2026-06-20_collab_hermes-webui-acervo-view.md` (umbrella).

### MOD-008: Workspace orientado à sessão + navegador de microversos + enriquecimento de contexto
- **Arquivos:** `static/friendly.js` (novo), `static/acervo.js` (navegador de microversos `_acRenderMicroverses*`, `openMicroverse`, `acervoAddToContext`, `resetAcervoForSession`), `static/workspace.js` (default `_workspacePanelActiveTab='artifacts'`, `renderSessionArtifacts` com nomes amigáveis, `openFilesBrowser`, `_refreshActiveWorkspaceTab`), `static/sessions.js` (chama `_refreshActiveWorkspaceTab` em `loadSession`), `static/ui.js` (`renderStagedContextChips`, `S.pendingContextAttachments`), `static/messages.js` (mescla contexto staged nos `attachments` do envio), `static/index.html` (aba default Sessão, botão Files oculto, ícone de rail "Arquivos", `#ctxTray`, include do `friendly.js`), `static/style.css` (`.acervo-mv-*`, `.acervo-kn*`, `.acervo-ctx-btn`, `.ctx-tray/.ctx-chip`, `.workspace-artifact-name`), `api/routes.py` (`_acervo_root`, `_read_frontmatter_meta`, `_humanize_slug`, handlers `_handle_acervo_microverses/knowledge/titles/stage_context` + dispatch).
- **Tipo:** frontend + backend (read + stage) + CSS.
- **Propósito:** (1) o painel direito passa a abrir na vista **Sessão** (artefatos + arquivos tocados na sessão, com nomes amigáveis) em vez da árvore crua; (2) o **sistema de arquivos** sai da régua de abas e passa a ser acessado pelo ícone **"Arquivos"** no rail esquerdo; (3) camada de **nomes amigáveis** (manifest/frontmatter → filename humanizado); (4) **navegador de microversos** (`Acervo ▸ Microversos`) que lista microversos e suas páginas de conhecimento por Nature; (5) **"Adicionar ao contexto"** que copia uma página do acervo para o diretório de anexos da sessão (`/api/acervo/stage-context`) e a anexa à próxima mensagem, reusando o pipeline de attachments. Inclui correção: o workspace agora re-renderiza ao trocar de chat (`_refreshActiveWorkspaceTab`).
- **Reaplicar se:** upstream reestruturar a régua de abas do painel direito, `switchWorkspacePanelTab`, o rail/sidebar de navegação, o caminho de envio de mensagem (`messages.js`) ou o dispatcher de rotas.
- **Conflito provável:** `static/index.html` — médio (abas, rail, includes). `static/workspace.js`/`static/messages.js`/`static/sessions.js` — médio (funções centrais tocadas). `static/friendly.js`, `static/acervo.js`, `static/ui.js` (bloco aditivo), `static/style.css`, `api/routes.py` — baixo (aditivos). Registro COLLAB: `.harness/changes/2026-06-20_collab_hermes-webui-acervo-view.md` (umbrella).

---

## Workflow de atualização (rebase)

```bash
git fetch upstream
git checkout exocortex/stable
git rebase upstream/master
# resolver conflitos guiado por este catálogo (ver "Conflito provável")
# rodar testes e smoke-test do servidor antes de promover
```

O comando `./ctl.sh update` (v1) automatiza apenas: fetch + diff stat + confirmação.
Rebase, testes e restart permanecem manuais nesta versão.
