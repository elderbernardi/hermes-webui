# EXOCRTX_MODIFICATIONS.md

Catálogo das modificações Exocórtex aplicadas sobre o fork de `nesquena/hermes-webui`.
Cada entrada documenta arquivo, propósito e risco de conflito para guiar o rebase
(`git rebase upstream/master`) e o comando `./ctl.sh update`.

- **Fork:** `elderbernardi/hermes-webui`
- **Branch de produção:** `exocortex/stable` (roda na porta 8787)
- **Base atual (merge-base real):** upstream **`exp-v0.52.61`** (commit `d486394f`) — **re-fundação HW-1 Strategy C executada 2026-07-14** (ver seção HW-1 no fim). Base anterior: `v0.51.448` (`32458c44`), preservada na tag `pre-refound-2026-07-13`.
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

### MOD-009: Acervo Explorer — file-explorer semântico com capacidade de *escrita* no acervo
- **Arquivos:** `api/acervo_explorer.py` (novo — backend inteiro: `_safe_acervo_path`, helpers de frontmatter `_split_fm`/`_dump_fm`/`_reassemble`/`_save_page_frontmatter`/`_atomic_write`, handlers de leitura `tree`/`page`/`search`, handlers de escrita `save`/`tags`/`move`/`status`/`stage`, e os dois dispatchers `handle_acervo_x_get`/`handle_acervo_x_post`), `static/acervo-explorer.js` + `static/acervo-explorer.css` (novos — painel IIFE redimensionável, layout responsivo 3/2/1 painéis via ResizeObserver, estado persistido em `localStorage`), `api/routes.py` (**+3 linhas efetivas** — dois blocos de dispatch de 3 linhas: GET após `/api/acervo/titles`, POST após `/api/acervo/stage-context`, ambos por prefixo `startswith("/api/acervo/x/")`), `static/index.html` (exatamente 3 edits — `<link>` do CSS, `<script defer>` do JS, mount `#acervoExplorerRoot` + botão `⤢` no header da aba Acervo), `tests/test_mod009_acervo_explorer.py` (novo — testes herméticos).
- **Tipo:** backend (read **+ write**) + frontend + CSS. **Primeiro MOD de *acoplamento de escrita* no acervo** (MOD-007/008 só liam ou copiavam páginas para anexos; MOD-009 edita frontmatter OKF + corpo das páginas *in-place* no acervo governado pelo Exocórtex).
- **Propósito:** file-explorer semântico premium e auto-contido sobre o acervo (`_acervo_root()`, nunca o workspace da sessão), com escrita **delimitada**: editar corpo+frontmatter, mover/renomear, status, tags, stage-context. Endpoints sob o prefixo `/api/acervo/x/` (`tree`/`page`/`raw`/`search` GET; `save`/`move`/`status`/`tags`/`stage` POST). **Sem deletar, sem criar-novo**; `.quarantine/` totalmente bloqueado (`_safe_acervo_path` rejeita qualquer componente iniciado por `.`, além de traversal `..`, symlink-escape e caminho absoluto). **Preservação OKF:** carrega o dict de frontmatter completo e sobrescreve só as chaves enviadas; nunca inventa campos; só atualiza `last_accessed_at`/`timestamp`/`updated` se já existirem; preserva ordem de chaves e unicode; escrita atômica (temp + `os.replace`). Status de página restrito a `{draft,ready,archived}`; status de artefato delega ao `_handle_acervo_status` (MOD-007), que revalida via `validate_artifact_manifest.py`. `page` serializa frontmatter via `_json_safe` (datas YAML → ISO, evita 500); `raw` faz stream de não-md (pdf/imagem) com `nosniff`+CSP sandbox; `search` casa título/descrição/tags + varredura de corpo limitada (`_body_snippet`, 256 KB), com `fulltext=0` para modo só-títulos.
- **Funcionalidades de UX (validadas em E2E headless Chromium):** painel docado à direita redimensionável com layout adaptativo árvore|cards|preview (3/2/1 zonas via ResizeObserver); preview markdown (reusa `renderMd`/`renderKatexBlocks`) + pdf/imagem; editor de corpo+frontmatter com aviso `perene` e guarda de não-salvo; busca com **realce do termo** (`mark.ax-hl`) e toggle **Tudo/Títulos**; **naturezas vazias ocultas** com toggle; escopo **Artefatos** com vínculo **tarefa↔artefato** ("Por tarefa" + grupo "Nesta sessão" via `collectSessionArtifacts`, banner de volta à tarefa no preview); **launcher de borda** auto-contido `#axLauncher` (entrada garantida quando a régua de abas colapsa). **Correções de robustez** pós-lançamento: o mount é **reparentado para `<body>`** em runtime porque `aside.rightpanel` tem `transform` (aprisiona `position:fixed` → painel invisível); `_loadScopeCards` limpa `loadingCards` antes de renderizar.
- **Rebase-safety (ponto central do desenho):** todo o comportamento novo vive em arquivos NOVOS; os arquivos do upstream só ganham o mínimo — `routes.py` recebe um dispatch por **prefixo `/api/acervo/x/`** (+3 linhas) que nunca colide com as rotas exact-match do upstream, e `index.html` recebe 3 linhas de include/mount. Isso torna o MOD-009 muito menos sujeito a conflito que os handlers inline `_handle_acervo_*` do MOD-007/008 diante da churn pesada de `routes.py` no upstream.
- **Reaplicar se:** upstream reestruturar o dispatcher de rotas GET/POST em `routes.py` (mover os pontos de inserção `/api/acervo/titles` / `/api/acervo/stage-context`), ou a área de header da aba Acervo / includes em `index.html`.
- **Conflito provável:** `api/routes.py` — baixo (só os 2 blocos de prefixo). `static/index.html` — baixo/médio (3 linhas de include/mount). `api/acervo_explorer.py`, `static/acervo-explorer.{js,css}`, `tests/test_mod009_acervo_explorer.py` — nulo (arquivos novos). Registro COLLAB: `.harness/changes/2026-06-23_collab_hermes-webui-acervo-explorer.md` (umbrella).

### MOD-010: Acervo Studio (Phases 0–1 — navegação + edição/download/bridge)
- **Arquivos:** `api/acervo_explorer.py` (**edit, não novo** — extensão da árvore unificada: helpers `_micro_nodes`/`_inbox_nodes` + os valores `scope=micro`/`scope=inbox` em `handle_tree`, +112/−2 linhas na Fase 0; na Fase 1 recebe só a delegação de fallback para os sub-paths que não lhe pertencem, mais `kind` aditivo e a harmonização `_micro_title`), `static/acervo-studio.js` + `static/acervo-studio.css` (**novos** na Fase 0, crescidos na Fase 1 — toolbar/editor/menu), `static/index.html` (**3 linhas**: `<link>` do CSS, `<script defer>` do JS, mount `<div id="acervoStudioRoot" hidden>`), `tests/test_mod010_acervo_studio.py` (**novo** na Fase 0, estendido na Fase 1). **Fase 1 adiciona `api/acervo_studio.py`** (**novo** — endpoint `x/download`; dispatchers-alvo da delegação). **`api/routes.py` — segue 0 linhas** em ambas as fases: o Studio reusa o dispatcher de prefixo `/api/acervo/x/` que o MOD-009 já registrou; nenhuma rota nova foi adicionada. **`static/index.html` — 0 linhas novas na Fase 1** (as 3 da Fase 0 cobrem tudo).
- **Tipo:** backend (read + **write via bridge**) + frontend (surface própria) + CSS. **Sucessor da surface**, não do backend: troca o painel docado do MOD-009 por uma view full-screen própria (toggle Chat ⇄ Acervo). Fase 0 era estritamente read-only; **a partir da Fase 1 a escrita também flui pelo Studio** — o editor inline chama os endpoints já existentes do MOD-009 (`x/save`, `x/tags`, `x/status`, `x/move`) e o botão de stage-to-chat chama `x/stage`; **nenhum caminho de escrita novo** foi criado — `x/download` (novo endpoint da Fase 1) é read-only (anexo de arquivo único ou zip de artifact-deliverables). **Fase 1.1 (UX):** ao abrir o Studio sem sessão de chat ativa, ele cria+vincula uma sessão transparentemente (`_ensureSession` → `POST /api/session/new`, espelhando `ui.js promptNewFile`/`promptNewFolder`) para o acervo ser navegável standalone; o gate de sessão do backend (`_resolve_session_workspace`) permanece **inalterado** — apenas deixa de exigir que o usuário abra um chat antes.
- **Fronteira de escrita:** inalterada desde o MOD-009 (RFC §6.3) — editar-existente apenas; sem create/delete; `.quarantine/` inalcançável; páginas perenes exigem confirmação; mesclagem preservando OKF no save; status restrito a `{draft,ready,archived}`; toda rota é sessão-gated; raiz sempre `_acervo_root()`.
- **Propósito:** unifica a navegação do acervo — `global`/`shared`/`macro`/`artifacts` (já existentes no MOD-009) mais os dois escopos novos **`micro`** (microversos por slug, com contagem de páginas por natureza, diretórios `_`/`.`-prefixados ocultos) e **`inbox`** (envelopes de `_inbox/incoming/`, título/status lidos do `manifest.json` quando presente, sem extrair nem promover — isso é Fase 2) — numa view full-screen com navegador + leitor + busca por command-bar (`⌘K`-style, `acervoStudioSearch`). Ver spec completa em `docs/rfcs/acervo-studio.md` (esta é a fatia de Fase 0: §4 IA unificada, §5.1 forma, §6 backend, §8 coexistência, §11 Fase 0).
- **Namespaces (distintos do MOD-009):** CSS `.axs-*` (MOD-009 usa `.ax-*`), estado global `AXS` (MOD-009 usa `AX`), funções `acervoStudio*` — `acervoStudioToggle`, `acervoStudioRenderNav`, `acervoStudioSelectScope`, `acervoStudioOpenPage`, `acervoStudioSearch` — expostas em `window.*`; nav emite `data-path`/`data-mv`/`data-scope` consumidos pelos mesmos listeners. Launcher auto-contido próprio (`#axsLauncher`, distinto do `#axLauncher` do MOD-009). IIFE vanilla, `sourceType:"script"` (sem `import`/`export`), reusa globais do app (`S`/`api`/`esc`/`showToast`/`renderMd`/`humanizeFilename`).
- **Tema:** segue o controle de Tema/Skin já existente do app (`System/Dark/Light` + skin) — claro usa a paleta **EXCRTX atual do web-ui** (`#f4f5f8` bg / `#ffffff` surfaces / `#03123f` ink / accent `#1376ed`); escuro usa a paleta nova **"Graphite Neutral"** (`#1b1d21` bg / `#26292e` surfaces / accent `#3b8af0`), desenhada para reduzir a fadiga do navy saturado padrão do EXCRTX em sessões longas. Nenhum controle de tema próprio — reflow automático quando o operador troca em Settings.
- **Rebase-safety:** o novo comportamento vive em **arquivos novos** (`static/acervo-studio.{js,css}`, `tests/test_mod010_acervo_studio.py`) e num edit aditivo ao módulo já fork-owned `api/acervo_explorer.py` (dois `if scope ==` a mais + duas funções privadas). O ponto central: **reuso do dispatch por prefixo `/api/acervo/x/tree`** que o MOD-009 já instalou em `routes.py` — o Studio não precisou tocar `routes.py` em nenhuma linha. `index.html` recebe apenas as mesmas 3 linhas de padrão include/mount que o MOD-009 estabeleceu.
- **Reaplicar se:** upstream reestruturar `handle_tree`/o dispatcher `/api/acervo/x/` (ambos fork-owned, risco baixo) ou a área de includes/mounts do painel direito em `index.html`.
- **Conflito provável:** `api/routes.py` — nulo (zero linhas tocadas). `static/index.html` — baixo (3 linhas de include/mount, mesmo padrão do MOD-009). `api/acervo_explorer.py` — baixo (edit aditivo, fork-owned). `static/acervo-studio.{js,css}`, `tests/test_mod010_acervo_studio.py` — nulo (arquivos novos). Registro COLLAB: `.harness/changes/2026-07-02_collab_hermes-webui-acervo-studio.md` (Fase 0) + `.harness/changes/2026-07-03_collab_hermes-webui-acervo-studio-phase1.md` (Fase 1), ambos na umbrella. Spec: `docs/rfcs/acervo-studio.md`.
- **Fase 2a — Intake Capture (agentless, 2026-07-11):** capturar material de entrada (texto/link/arquivo) como um **IntakeEnvelope** em `_inbox/incoming/{id}/` + navegar/inspecionar os envelopes no Studio. **Sem agente, sem escrita semântica** — envelope ≠ memória (input is not memory), funciona com o Hermes offline (verificado no E2E: servidor sem runtime → `run_agent: ModuleNotFoundError` e a captura funciona mesmo assim). Backend só em `api/acervo_studio.py` (helpers `_slugify`/`_intake_id`/`_write_envelope`/`_read_envelope`/`_list_envelopes` + rotas `POST x/intake/{text,link,upload}` e `GET x/intake` (lista) / `x/intake/item?id=` (detalhe), roteadas via `handle_studio_{get,post}`). **Upload = base64-in-JSON** (o servidor não tem parser multipart; o dispatch POST entrega `body` JSON já parseado) com cap de 25 MiB (HTTP 413). Frontend: unit `intake` em `acervo-studio.{js,css}` — painel "＋ Capturar" (abas texto/link/arquivo) no escopo inbox + view de detalhe do envelope (preview via `x/raw`), namespaces `.axs-cap*`/`.axs-env*`. **`api/routes.py` e `static/index.html` — seguem 0 linhas.** Suíte MOD-010 49/49; rebase-safety EMPTY. **Triagem + promote (agente, primeira WRITE-coupling → COLLAB) = Fase 2b**, plano separado. Spike de invocação resolvido em `docs/acervo-studio/SPIKE-hermes-invocation.md`; plano em `docs/acervo-studio/PLAN-phase2a.md`.
- **Fase 2b — Intake Triage + Promote (agent-mediated; primeira escrita SEMÂNTICA, 2026-07-12):** o Hermes propõe um destino para um envelope do inbox (triagem, **read-only**) e, com aprovação do owner (**propose-then-approve**), o envelope vira uma página semântica em `micro/{slug}/{nature}/`. Arquivo novo `api/acervo_studio_agent.py` (mediação `USER→GUI→SERVER→HERMES`, self-contained/rebase-safe): `propose_triage` roda um turno `run_conversation` **tool-less** e parseia um JSON `{scope,slug,nature,title,rationale,keep_in_inbox}` (normalizado/validado); `promote` roda um turno tool-less que **redige o corpo** da página (`{body_markdown,class,description,tags}`) e o servidor **escreve determinística e semanticamente** via o control-plane `acervoctl.py prepare-write`+`commit-write` (o guard de escopo roda dentro do commit; index/log atualizados; recibo estruturado). **Padrão híbrido (spike Task 0):** o agente propõe/redige (cognição), o servidor escreve (determinístico) — evita confiar operações de arquivo ao LLM. Rotas `POST x/intake/item/{triage,promote}` (via `handle_studio_post`, **0 linhas em routes.py**); front: botão "🔎 Triar com IA" + painel de proposta editável + "✓ Promover à memória" (`.axs-prop*`), estados operacionais retornam 200 com flag `ok/offline` (UI calma). **Micro-scope only** (o guard nega global/shared/macro); frontmatter OKF/v0.2 construído no servidor (`commit-write` valida mas não sintetiza). Control-plane runnable em `~/.exocortex-installer/scripts/` (não em `~/.hermes`). Governança: `.quarantine`/traversal inalcançáveis, session-gated, degradação graciosa (Hermes offline → triagem/promote mostram "agente offline", captura/leitura seguem). Verificado: suíte MOD-010 (helpers+rotas com agente **mockado**) + **escrita real** via acervoctl contra um acervo **fixture** (página committed + log CREATED + recibo) + degradação offline **ao vivo** + guards 400. `api/routes.py`/`index.html` **0 linhas**. ⚠️ Testado só contra fixture — nunca o acervo real (o `_inbox`/promote escrevem no `_acervo_root()`, que resolve `$ACERVO`; o profile do `~/.hermes` real sobrescreve `$ACERVO` por request, então o E2E usa um `HERMES_HOME` temporário). Plano em `docs/acervo-studio/PLAN-phase2b.md`.
- **Fase 3 — Publish outbound (determinístico, sem cognição, 2026-07-12):** publicar um pacote de artefato (`_artifacts/items/{id}/`) no Google Drive a partir do Studio — **gate de qualidade → confirmação Draft-First → recibo SHA-256**. Espelho do promote: onde o promote tinha o agente **redigir** conteúdo e o servidor escrever, o publish **não tem cognição** — o servidor faz shell-out direto às duas CLIs canônicas (list-form, sem `shell=True`, exatamente como o `_acervoctl` do 2b): `global/tools/harness/validate_artifact_manifest.py --json` (gate antislop/taste; draft só gera warnings) e `global/tools/artifact_publish.py publish` (upload determinístico com recibo). Arquivo novo `api/acervo_studio_publish.py` (self-contained/rebase-safe): `_valid_artifact_id`/`_artifact_dir` (id sem `/`,`\\`,`.`-líder, ≤128; path resolvido rejeita escape via symlink p/ `.`-prefixados — mesma postura do `x/download`), `_resolve_tools_dir` (prefere `global/tools` do acervo servido, depois `~/.hermes` e `~/exocortex`), `_run_validator`/`_run_publish` (ACERVO fixado na raiz servida; timeouts 60s/300s), `prepare()` (gate + alvo Drive + opções de visibilidade, read-only) e `publish()` (o gate **re-roda** no confirm p/ um prepare velho não passar artefato reprovado). Rotas `POST x/publish/prepare` + `POST x/publish` (via `handle_studio_post`, **0 linhas em routes.py**); front: card do artefato ganha "⇪ Publicar no Drive" + painel `.axs-pub*` (gate → confirm Draft-First → recibo com links **só https**, filtrados por `_safeHttp`). **Draft-First / owner-gate:** o publicador hardcoda `visibility:"private"` e **não tem** flag pública — `visibility:"public"` é recusado calmamente (`public_gated`) **mesmo com `approve_public:true`**; compartilhamento público continua um passo de aprovação do owner fora da ferramenta. **Degradação graciosa (HTTP 200 + flag):** `tools_missing` (CLIs ausentes no runtime), `drive_unconfigured` (sem `google_api.py` — detecção casada com a mensagem específica da ferramenta, não o mero filename), `gate_failed` (+issues), `public_gated`; malformado/ausente = 400/404. Verificado: suíte MOD-010 **121/121** (inclui testes que rodam CLIs **fake reais** dentro do fixture p/ exercitar o subprocess) + E2E **ao vivo** com o validador e o publicador **reais** contra um acervo **fixture** + `HERMES_HOME` temporário (gate antislop reprovou artefato `ready` sloppy ao vivo; draft limpo preparou; publish degradou p/ "Drive não configurado"; owner-gate público segurou; link `javascript:` filtrado; 0 erros de console). Review whole-branch (opus) fechou 1 Important (500-leak em `drive_target` não-dict → guard + regressão) + 2 Minors. `api/routes.py`/`index.html` **0 linhas**; rebase-safety EMPTY. ⚠️ O upload Drive real precisa de credenciais no runtime (provisioning, owner-gated) — não exercitado ao vivo; o recibo foi verificado via stub de rede pelo handler real. Plano em `docs/acervo-studio/PLAN-phase3.md`; E2E em `.superpowers/sdd/e2e-report-phase3.md`.
- **Fase 4 — Assist + Ask-the-acervo (cognição SOMENTE-PROPOSTA, 2026-07-12):** duas features de cognição inline que **não escrevem nada**. **Assist** (`POST x/assist {path, op}`, `op∈{rewrite,summarize,suggest_tags,contradiction_check}`): lê **uma** página `.md` existente (via `_safe_acervo_path` + guard de dot resolvido, `.quarantine` inalcançável, corpo limitado a 12k chars), roda um turno `run_conversation` **tool-less** e retorna uma proposta JSON validada por-op; aplicar reescrita/tags **pré-preenche o editor MOD-009 existente** (o `x/save` continua o **único** caminho de escrita). **Ask ("perguntar ao acervo")** (`POST x/ask {question}`): `_ask_context` = recuperação in-process limitada (overlap de termos: title×3/tags×2/desc×2/body×1, ≤2000 arquivos, pula dirs `_`/`.`) que ancora uma resposta tool-less; as `sources` citadas são **validadas no servidor como um subconjunto** dos caminhos recuperados (grounding). Recuperação própria em vez de `acervoctl retrieve` (que exige um `catalog.sqlite` pré-construído via `reindex`; probing deu `found:false` mesmo em hits de termo). Ambas em `api/acervo_studio_agent.py` (append: `propose_assist`, `_page_content_for_assist`, `_clean_tags`, `_normalize_assist`, `_ask_context`, `ask_acervo`). Rotas via `handle_studio_post` (**0 linhas em routes.py**); front: strip "✦ Assistir" (`.axs-ai*`, 4 ops, aplicar-no-editor) + "✦ Perguntar ao acervo" na busca (`.axs-ask*`, fontes clicáveis). Estados operacionais = HTTP 200 + `{ok:false, offline|no_context|error}`; op desconhecida / pergunta vazia = 400. Verificado: suíte MOD-010 **154/154** (grounding-subset, dot-skip, offline/no_context, non-md reject, regressões de review); E2E **ao vivo** num fixture + `HERMES_HOME` temporário que tinha um agente **funcional** — assist summarize funcionou **ao vivo** (cognição real ancorada); ask degradou calmamente em HTTP 200 ~8s sob **falha real do LLM** (garantia de estado operacional provada sob falha genuína, **nunca 500**); recuperação verificada ao vivo (ranqueia a página certa, exclui `_meta`, sem escrita); reescrita renderiza XSS-safe + aplica no editor; 0 erros de console; acervo real intocado. Review whole-branch (opus) fechou **2 Important** (mesma classe integration-only da Fase 1/3): (A) `_normalize_assist` 500-leak quando o modelo retorna `findings` não-lista → guard `isinstance`; (B) `_ask_context` vazava `.quarantine`/`_meta` via symlink de nome limpo resolvendo dentro da raiz (assimétrico com o guard do assist) → rejeita parts dot/underscore **antes** de ler o corpo. Confirmado PASS: proposal-only/no-write, rebase-safety, grounding-subset, XSS/vanilla, path safety. `api/routes.py`/`index.html` **0 linhas**; rebase-safety EMPTY. ⚠️ Fixture-only; a etapa de resposta do LLM no ask é intermitente no ambiente (degrada com calma). Plano em `docs/acervo-studio/PLAN-phase4.md`; E2E em `.superpowers/sdd/e2e-report-phase4.md`.
- **Fase 5 — Consolidate (frontend + docs, 2026-07-12):** o Studio atinge paridade → consolidação. **(1) Aposentar/redirecionar o painel docado do MOD-009 SEM editar `acervo-explorer.*`** (rebase-safety): um hook `_consolidateMod009()` (em `acervo-studio.js`, no bootstrap DOM-ready) esconde o launcher de corpo do MOD-009 (`#axLauncher` → `display:none`) e **redireciona** o global `window.acervoExplorerToggle` para abrir o Studio, preservando o original em `window.__acervoExplorerToggleLegacy` (escape hatch — nada é removido, só afunilado). O botão ⤢ do index.html (`onclick="acervoExplorerToggle()"`) passa a abrir o Studio; o painel docado `#acervoExplorerRoot` nunca mais abre pelos entry points. **(2) a11y:** `.axs-root` ganha `role="dialog"`/`aria-modal`/`aria-label`; handler de teclado (Escape fecha quando o foco NÃO está em input/textarea/select; Enter/Espaço ativam um item de nav focado); o foco vai para a busca ao abrir e volta ao launcher ao fechar (`AXS._returnFocus`); itens de nav (`.axs-ni` escopos + `.axs-pi` páginas/mv/intake/art) viram `role="button"`+`tabindex="0"` com anel `:focus-visible`. **(3) perf:** medido ao vivo (abrir ~3ms, render da nav ~0ms, troca de escopo ~2ms — o fetch do badge do inbox é assíncrono e não bloqueia) → **sem otimização** (YAGNI). **(4) docs:** `docs/acervo-studio/UPSTREAM-SYNC.md` (checkpoint de sync + gatilhos de reaplicar) + RFC §1/§11 marcados **DELIVERED (Fases 0–5)**. Verificado: E2E ao vivo (consolidação: `#axLauncher` escondido, toggle redirecionado abre o Studio e deixa o `#acervoExplorerRoot` escondido, legacy preservado; a11y: role/foco/Enter/Escape/retorno-de-foco todos OK; 0 erros de console); suíte MOD-010 **154/154** inalterada (Fase 5 = FE+docs); `acervo-explorer.*`/`routes.py`/`index.html` **byte-untouched**; rebase-safety EMPTY. Plano em `docs/acervo-studio/PLAN-phase5.md`; E2E em `.superpowers/sdd/e2e-report-phase5.md`.

### MOD-011: Canvas de Tarefas (spike F0, **experimental**)
- **Resumo:** `/api/canvas/*` prefix dispatch + store em `$ACERVO/_tasks` + página dev. Arquivos novos: `api/canvas_{store,validate,enquadrador,tarefas}.py`, `scripts/{spike_llm_cmd,spike_canvas_latency}.py`, `static/canvas-{dev.html,tarefas.js,tarefas.css}`, `tests/{test_canvas_store,test_canvas_validate,test_canvas_enquadrador,test_canvas_routes}.py` + fixtures (`tests/fixtures/stub_llm_{ok,ruim}.py`); `api/routes.py` **+8 linhas/2 hooks** (dispatch por prefixo `/api/canvas/`, mesmo padrão do MOD-009/MOD-010, um hook em `handle_get` outro em `handle_post`).
- **Tipo:** backend (novo endpoint, escrita restrita a `$ACERVO/_tasks/`) + frontend (página dev isolada, sem integração com `index.html`/`ui.js`) + testes. **Experimental / spike de descoberta** — não é feature entregue: prova 1 frase → núcleo do canvas validado (schema v0.4) → deltas via SSE → render mínimo no browser, para decidir duas ADRs de arquitetura antes da F1 (Sala/MVP).
- **Propósito:** `api/canvas_store.py` mantém o ciclo de vida do canvas (`create_draft`/`load_canvas`/`save_canvas`) em `$ACERVO/_tasks/{canvas_id}/canvas.yaml`, com patch RFC 6902 (`apply_patch`) e mapeamento núcleo→documento (`core_to_patch`); `api/canvas_validate.py` valida o núcleo contra o schema oficial (`$ACERVO/global/tools/harness/canvas_schema.py`, carregado dinamicamente via `load_schema()`); `api/canvas_enquadrador.py` transforma uma frase executiva em núcleo validado via um seam de LLM externo (`CANVAS_LLM_CMD`, subprocess, com retry em caso de resposta inválida); `api/canvas_tarefas.py` expõe `POST /api/canvas/draft` (cria draft + dispara enquadrador em thread) e `GET /api/canvas/{get,stream}` (snapshot/patch/estado via YAML e SSE — `canvas_snapshot`→`canvas_delta`→`canvas_done`); `static/canvas-dev.html`/`canvas-tarefas.js`/`canvas-tarefas.css` renderizam as 4 zonas (Foco/Vetor/Microverso âncora/Lacunas) a partir do stream, standalone (não linkado do `index.html`).
- **Achados de framework (ver `F0-RESULTADO.md` para detalhe):** drift de nomenclatura `vetor` (schema) × `vector` (template `canvas.yaml`) e enum de `intent_type` divergente (5 valores no schema vs 8 no template) — resolvidos no spike com duas camadas núcleo/documento explícitas (`core_to_patch`); recomendação registrada para unificar em canvas v0.5 durante a F1. `CANVAS_LLM_CMD` precisa de caminho **absoluto** (cwd do subprocess = diretório do agente Hermes, não a raiz do repo).
- **Rebase-safety:** todo o comportamento novo vive em arquivos NOVOS (`api/canvas_*.py`, `scripts/spike_*.py`, `static/canvas-*`, testes/fixtures); `api/routes.py` recebe apenas os 2 blocos de dispatch por prefixo (padrão MOD-009/MOD-010, EXCRTX MOD-011 marcado no comentário); nenhum arquivo do upstream é editado; `static/index.html`/`ui.js`/`messages.js`/`sessions.js`/`panels.js`/`boot.js`/`style.css` **não tocados** (a página dev é acessada direto por URL, sem link/mount na UI principal).
- **Decisões de arquitetura (ADRs, medidas com LLM real `deepseek-v4-pro`):** ADR-CT-04 decidiu **job+poll** (invocação síncrona streamada não sustentada — `first_delta` ficou entre 13.4–18.5s, acima do limite de 8s da regra); ADR-CT-05 decidiu **vanilla JS** para a F1 (`canvas-tarefas.js` com 80 linhas, render stateless, zero bugs de sincronização). Ver `exocortex.saas/docs/plans/2026-07-23_canvas-tarefas/adr/`.
- **Reaplicar se:** upstream reestruturar o dispatcher de rotas GET/POST em `routes.py` (mover os pontos de inserção usados pelos hooks do MOD-011) — risco baixo, mesmo padrão de prefixo já usado pelo MOD-009/MOD-010.
- **Conflito provável:** `api/routes.py` — baixo (só os 2 hooks de prefixo, +8 linhas). Todos os demais arquivos do MOD-011 — nulo (novos). Registro: `exocortex.saas/docs/plans/2026-07-23_canvas-tarefas/` (F0-PLANO, F0-RESULTADO, ADR-CT-04, ADR-CT-05), issue F0 `elderbernardi/exocortex.saas#131` (filha da meta issue #130). **Status: spike concluído, gate fechado pelo owner (#131 CLOSED, merge em `exocortex/stable`)** — F1 (MVP Cockpit) construída em cima, ver MOD-012.

### MOD-012: Canvas de Tarefas — MVP Cockpit (F1, feature entregue)
- **Resumo:** promove o spike F0 (MOD-011) a feature: superfície **Hangar** (lobby) + **Cockpit** (sala de tarefa ativa) + pipeline de launch (canvas → tarefa registrada + sessão Hermes com brief). Consome o **canvas v0.5** (exocortex.saas ADR-CT-06, mergeado em main). Arquivos: evoluídos `api/canvas_{store,validate,enquadrador,tarefas}.py` + `static/canvas-{tarefas.js,tarefas.css,dev.html}`; novo `api/canvas_brief.py`; testes canvas expandidos. `api/routes.py` **inalterado** (os 2 hooks do MOD-011 já cobrem `/api/canvas/*`).
- **Tipo:** backend (novos endpoints `/api/canvas/{list,job,patch,brief,launch}` + `stream?since=` re-anexável) + frontend (superfície Hangar/Cockpit, edição in loco, preview do brief, launch) + testes. **Feature entregue** (não spike).
- **Propósito por superfície:** enquadrador agora **in-process** (`agent.auxiliary_client.call_llm` sob `profile_env_for_background_worker`, ADR-CT-04; seam `CANVAS_LLM_CMD` = override de teste/dev); registry job/event-log **não-destrutivo** com replay por cursor (`_emit`/`_emit_final`/`CANVAS_JOBS`, mata a double-connect race); `POST /api/canvas/patch` com whitelist de paths editáveis + `re.fullmatch` (sem newline-injection) + 400 em op de alvo ruim; `api/canvas_brief.py::compile_brief` compilador determinístico PT-BR (rejeita `ambiguo`); `POST /api/canvas/launch` = register (subprocess) + `new_session` + stage (`_upload_destination`) → front dispara `/api/chat/start`. UI: `window.CVT`, namespace `.cvt-*`, `#canvasRoot` reparentado ao `<body>` (padrão Acervo Studio), launcher próprio + injeção runtime typeof-guarded de botão de modo no Studio; **toda interpolação DOM via `esc()`** (fecha o self-XSS do F0).
- **Espelhos do esquema:** `api/canvas_validate.py` (`_ENUMS`/`_ALLOWED`) e `api/canvas_store.py` (`_MINIMAL`/`_CORE_TO_DOC`, chave `vetor` com fallback de leitura `vector`) espelham o schema v0.5 do exocortex — atualizar em conjunto num COLLAB se o schema mudar. Contrato: `projetob/.harness/contracts/exocortex-hermes-webui.md`.
- **Achado pré-existente (registrado):** MOD-008 `#ctxTray` — `S.pendingContextAttachments` é renderizado mas **não** consumido no `send()` do chat nativo (sem consumidor no caminho de envio). O launch do canvas NÃO depende disso (usa o contrato programático session/new → stage → chat/start com attachments). Bug do fork pré-existente, não corrigido aqui.
- **Rebase-safety:** comportamento novo em arquivos novos/já-fork-owned do MOD-011; `api/routes.py`/`index.html`/`ui.js`/`messages.js`/`acervo-studio.js` **byte-untouched** (injeção do botão de modo é runtime, não commit em index.html).
- **Registro:** `exocortex.saas/docs/plans/2026-07-23_canvas-tarefas/` (F1a-PLANO, F1b-PLANO, F1-CHARTER, ADR-CT-06), issue F1 `elderbernardi/exocortex.saas#132`. Naming Hangar/Cockpit decidido pelo owner 2026-07-24 (antes Átrio/Sala).

### MOD-013: Curador (F2) — agente paralelo in-process, semântica A2A
- **Resumo:** adiciona um agente "Curador" que roda **em paralelo** ao enquadrador/Cockpit do MOD-012, respondendo delegações (`buscar_acervo`/`sugerir_itens`/`pesquisar`) devolvendo à Sala **só o artefato destilado citado** (≤700 tokens), nunca a trilha de busca. Registro/transporte **próprio** (`CURADOR_ROOMS` ≠ `CANVAS_JOBS` do MOD-012) + SSE próprio, para que os 3 obstáculos herdados do F1b (stream fecha em `canvas_done`, `_schedule_cleanup` de 300s, Cockpit não reabre) não se apliquem por construção. Arquivos novos: `api/curador_a2a.py` (protocolo A2A puro: `new_task`/`new_message`/`new_artifact`/`new_part`, `TaskStore`, `transition()` máquina 6-estados), `api/canvas_curador.py` (transporte+worker: `CURADOR_ROOMS`, SSE, singleton `_CURADOR_BUSY`+fila FIFO `_QUEUE`/`_pump`, `_call_llm_curator`, bounds+`_budget_guard`+ledger de higiene, as 3 skills, `handle_curador_get/post`, `delegar`), `api/canvas_curador_retrieve.py` (wrapper só-leitura do acervo: `curador_retrieve`/`curador_posture`, nenhum verbo de escrita importado), `api/curador_capabilities.py` (memória viva off-trail: `build_agent_card`/`refresh_capability_cache`/`load_capability_card`), `static/canvas-curador.js` (ilha de UI: 2ª `EventSource`, zona "Sugestões do Curador", aceitar→`window.CVT.acceptOps`).
- **Tipo:** backend (novos endpoints `/api/canvas/curador/{delegar,stream,job}`, despachados por **forward**, não por hook em `routes.py`) + frontend (ilha vanilla JS, sem build) + testes. **Feature entregue** (F2 do épico Canvas de Tarefas).
- **Propósito por superfície:** `api/curador_a2a.py` = protocolo puro (sem transporte/FS), shapes wire-idênticos ao A2A real (estados hifenizados `input-required`, `Part.kind`, `contextId`), testável isoladamente; `api/canvas_curador.py` orquestra o worker in-process (ADR-CT-04: job+poll, thread daemon + `Condition` + log append-only) com **singleton** (`_CURADOR_BUSY`) + **fila FIFO global ordenada** (`collections.deque`, drenada sob `_QLOCK` — decisão travada (d)); `api/canvas_curador_retrieve.py` chama `acervoctl.py retrieve`/`posture` via subprocess (mesmo padrão `_resolve_acervoctl_dir`/`_acervoctl` de `acervo_studio_agent.py`, MOD-010 Fase 2b) — sem `--json` (posture rejeita o flag; `main()` já imprime JSON); `api/curador_capabilities.py` implementa a memória viva v1 = **off-trail cache** em `global/tools/state/curador/capabilities.json` (decisão travada (b)) — índice derivado, escrito só pela rotina de refresh dedicada, nunca pelo caminho de leitura do worker; `static/canvas-curador.js` renderiza cards (aceitar/dispensar em 1 clique) e handshake com o Cockpit via `window.CanvasCurador.onCockpitOpen`/`window.CVT.acceptOps`.
- **Forward em vez de hook em `routes.py`:** o F1b (MOD-012) já esgotou o teto de 8 linhas novas da regra 3 (2 hooks × 4 linhas, dispatch incondicional em L13110-13113/15068-15071). O F2 despacha `/api/canvas/curador/*` por **forward** no topo de `handle_canvas_get`/`handle_canvas_post` (já fork-owned, já recebem toda requisição `/api/canvas/*`) — **`routes.py` fica em 0 linhas novas**. Edição em `api/canvas_tarefas.py` também espelha a whitelist de patch (`_WHITELIST_RAW`: `/personas/suggested/*`, `/acervo_aplicado/*`) e o `_MINIMAL` em `api/canvas_store.py` recebe `personas`/`acervo_aplicado`.
- **Guardrails:** Curador **nunca escreve no acervo** — estrutural para `buscar_acervo`/`sugerir_itens` (só importa verbos de leitura `retrieve`/`posture`; nenhum import de `prepare_write`/`commit_write`/`new-object`); config-trust para `pesquisar` (role auxiliar `call_llm(task="curator")`, toolset web-only restrito, atrás de `CURADOR_ENABLE_PESQUISAR`). Bounds fable-method **só em código** na v1 (contadores mecânicos: "2 buscas sem informação nova → gap", "3 ciclos falha-conserto → pare"); as skills `excrtx-conduct-*` ficam para F3. Sharing na leitura via `retrieve`/`--scope`/`--allow-scope` + `sensitivity:restricted` (deny-sempre) — **correção ao charter**: `acervo_validate_scope` é guarda de **escrita**, não se aplica ao Curador (read-only); `allow_scopes` validado server-side.
- **Relação com MOD-011/MOD-012:** o F2 é construído **sobre** o F1b (MOD-012) não-mergeado, na mesma branch `collab/canvas-tarefas`; reusa `TaskStore`/schema v0.5/whitelist de patch do MOD-012 sem alterar seu comportamento existente (o forward do Curador roda **antes** do dispatch normal do MOD-012 dentro de `handle_canvas_get/post`, sem tocar a lógica de `draft`/`get`/`list`/`job`/`stream`/`patch`/`brief`/`launch`). `routes.py` continua nos mesmos 8 linhas do MOD-011/012 (0 linhas a mais).
- **Rebase-safety:** comportamento novo majoritariamente em arquivos novos (`api/curador_*.py`, `api/canvas_curador*.py`, `static/canvas-curador.js`); edições aditivas em arquivos já fork-owned do MOD-011/012 (`api/canvas_tarefas.py` forward, `api/canvas_store.py` `_MINIMAL`, `static/canvas-tarefas.js` 2 edições mínimas — surface `window.CVT`+hook `onCockpitOpen`, `static/canvas-dev.html` 1 `<script>`, `static/canvas-tarefas.css` classes da ilha). `api/routes.py`/`index.html`/`ui.js`/`messages.js`/`sessions.js`/`panels.js`/`boot.js`/`style.css` **byte-untouched**.
- **Conflito provável:** `api/routes.py` — nulo (0 linhas). `api/canvas_tarefas.py`/`canvas_store.py`/`static/canvas-tarefas.js`/`canvas-dev.html`/`canvas-tarefas.css` — baixo (edições aditivas pequenas, mesmo padrão MOD-011/012). Demais arquivos do MOD-013 — nulo (novos).
- **Registro:** `exocortex.saas/docs/plans/2026-07-23_canvas-tarefas/F2-PLANO.md` (00-INDEX, charter F2, ADR-CT-04/05/06). Contrato: `projetob/.harness/contracts/exocortex-hermes-webui.md` §(f). Change record COLLAB: `.harness/changes/2026-07-25_COLLAB_curador.md`. Testes: `tests/test_curador_{a2a,worker,retrieve,bounds,skills,capabilities,ui_source,doc_extension,hygiene}.py`.

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

---

## Status de Upstream — auditoria 2026-06-23

Snapshot da divergência com `nesquena/hermes-webui`:

- **Atraso:** `exocortex/stable` está **18 commits à frente / 607 commits atrás** de `upstream/master`.
- **Faixa de releases:** base `v0.51.448` → upstream `v0.51.607` (**159 patch releases**, ~5 meses).
- **Volume:** ~312 arquivos alterados (+48,9k / −2,6k linhas).
- **Risco central:** `api/routes.py` mudou em **89 commits (+3.427 linhas)** — exatamente onde vivem os handlers do Acervo (`_handle_acervo_*`). Um `git rebase upstream/master` integral conflita pesado e provavelmente quebra MOD-007/008. **Recomendado: cherry-pick faseado, não rebase completo.**

### Cherry-pick priorizado (alto valor, baixo conflito)

**Fase 1 — Segurança + estabilidade (puxar primeiro):**

| Item | Refs | Impacto | Conflito |
|---|---|---|---|
| Vazamento de credenciais entre perfis | `c55ba5df`, `239529f9`, `1293f030`, `51dd69b4`, `4eb069be`, `bf548a25`, `d60ad140` (#3961/#4544) | 🔴 Segurança crítica | Médio (`profiles.py`, `config.py`, `gateway_chat.py`) |
| Hardening de isolated-profile (2ª porta de escape) | `f7e144d5`, `fba80e69`, `cb7efedc`, `17eb82f0` (#4589/#4620) | 🔴 Segurança | Baixo (se não usa isolated-mode) |
| Hardening wiki/symlink (não vazar path-alvo, rejeitar hardlink) | `077de545`, `0fe707b2`, `22bfed43` (#4375/#4581) | 🟠 Segurança | Baixo |
| Throttle do SSE de reasoning (corrige **congelamento da aba**) | `eabe1426`, `8f5ffea4`, `fa51e341` (#4729) | 🟠 UX crítico | Baixo (isolado em `streaming.py`) |

**Fase 2 — Performance + polish:**

| Item | Refs | Impacto | Conflito |
|---|---|---|---|
| Cache do app-shell template | `c6994b50`, `7c9fef2f` (#4774) | 🟢 Perf | Baixo |
| Hot-path caching de backend (fases 2+3) | `f9a687d0`, `8006db22`, `4f071895` (#4662) | 🟢 Perf | Baixo-médio (`config.py`) |
| Footer jitter no virtual-scroll | `028fb61f`, `8b74045b` (#4346) | 🟡 Suavidade | Baixo (`style.css`, `ui.js`) |
| TLS handshake não trava o accept loop | `a43a9365` (#4727) | 🟡 Estabilidade | Baixo |
| Scroll de live-stream + sessão mobile | `d6133458` (PR #4785: #4778/#4777/#4780) | 🟠 UX live-mode | Médio-alto (sidebar/worklog) |

**Fase 3 — Avaliar antes (features novas, dependem de conferir compatibilidade com o Acervo):**

| Item | Refs | Nota |
|---|---|---|
| Kanban de tarefas + dependências | `947b770a` (#3797) | Código majoritariamente novo; checar sobreposição com a view "Tarefa" do Acervo |
| Wiki LLM (read-only) no painel Insights | `4e5eebd0` (#2941) | Conflito médio em `panels.js` |
| Skeletons de profile-switch | `b084535b`, `12180079` (#4671/#4717) | Conflito médio em `ui.js`/`workspace.js` |
| Symlinks na árvore de workspace | `53adcfc3` (#4226) | Baixo; vem com hardening |
| Atalho Ctrl/Cmd+, para Settings | `8c68bc6b` (#4391) | Trivial |

### Conflito esperado (arquivos customizados pelo fork × mudanças upstream)

| Arquivo | Commits upstream | Risco | Razão |
|---|---|---|---|
| `api/routes.py` | 89 (+3427) | 🔴 Crítico | Handlers do Acervo + dispatcher de rotas |
| `static/style.css` | 39 (+451) | 🟠 Alto | Bloco `.acervo-*` aditivo no fim colide com novas regras |
| `static/ui.js` | +2256 | 🟠 Alto | `renderStagedContextChips` (MOD-008) × refactors de scroll |
| `static/panels.js` | +1458 | 🟠 Alto | Painel workspace × novos painéis (Wiki/Kanban) |
| `static/index.html` | 17 (+143) | 🟡 Médio | Régua de abas, rail, includes (MOD-003/007/008) |
| `static/sessions.js` | +835 | 🟡 Médio | `_refreshActiveWorkspaceTab` (MOD-008) × filtro de fonte |
| `static/workspace.js` | 6 (+113) | 🟡 Médio | `switchWorkspacePanelTab`, `renderSessionArtifacts` (MOD-007/008) |
| `api/config.py` | +823 | 🟡 Médio | MOD-001 (skin) × caching de config |

### Estratégia recomendada

1. Branch de trabalho a partir de `exocortex/stable` (ex.: `chore/upstream-sync-2026q2`).
2. `git cherry-pick` da **Fase 1** item a item, resolvendo conflito guiado pela tabela de MODs acima; rodar `npm run lint:runtime` + smoke-test do servidor a cada item.
3. **Fase 2** idem.
4. **Não** tentar `git rebase upstream/master` integral nesta janela — o custo/risco em `routes.py` não compensa.
5. Após estabilizar, atualizar a linha "Base atual" e registrar no change-log da umbrella se algum item tocar contrato/superfície compartilhada.

### Resultado da Fase 1 — executado 2026-06-23 (branch `chore/upstream-sync-2026q2`)

Cherry-pick faseado, item a item, validado por testes. Resumo:

| Item de segurança | Resultado | Commits aplicados |
|---|---|---|
| **SSE reasoning throttle — corrige congelamento de aba (#4729)** | ✅ Aplicado | `eabe1426` (-m1) → `fa51e341` → `8f5ffea4`. Teste `test_issue4729_reasoning_sse_coalesce.py` 5/5. |
| **Vazamento de credenciais entre perfis (#3961/#4544)** | ✅ Aplicado | merge `239529f9` (-m1, 9 conflitos resolvidos p/ a versão endurecida) + follow-ups `1293f030` `4eb069be` `bf548a25` `51dd69b4` `d60ad140`. Teste `test_issue3957_profile_providers_models.py` 33/33. |
| Wiki path-traversal (#4375/#4581 wiki) | ⏭️ N/A | Os endpoints `/api/wiki/browse` e `/api/wiki/page` (feature #2941 `4e5eebd0`) **não existem** na base do fork — só `/api/wiki/status`. A vuln não está presente. |
| Isolated-profile hardening (#4589/#4620) | ⏭️ N/A | A feature isolated-HERMES_HOME mode (#2698, `963f7c38`/`36dbe1a4`) é **pós-base** e não está no fork; `HERMES_WEBUI_ISOLATED_PROFILE` inexistente. |
| Symlink target-disclosure (#4581 workspace) | ⏭️ Deferido | Entrelaçado com a feature symlink-display do upstream (#4226) + i18n MOD-006 (13 blocos em `i18n.js`, HEAD vazio em `ui.js` → risco de handler duplicado). Severidade moderada — navegação/leitura já bloqueada por `safe_resolve_ws`. Reavaliar junto com #4226. |

**Adaptação do fork (necessária):** o fix #3961 espera `/api/models/live` envolvido em `profile_env_for_active_request(...)`; o fork extraiu esse handler em `_handle_live_models()`, então o wrapper foi aplicado manualmente na chamada em `routes.py` (mantém paridade com o guard estrutural do teste). `/api/providers` e `/api/provider/quota` ficaram cobertos pelo próprio change set.

**Regressão:** suíte completa **9036 passaram / 17 falharam**. As 17 falhas foram trianguladas como **pré-existentes** (não causadas pelos cherry-picks): testes de cobertura de locales (i18n MOD-006), skins/tema default (catppuccin/sienna/verdigris — MOD-001/003/005), `sprint33` confirm nativo, e `issue1426` openrouter (falha idêntica em `exocortex/stable`); mais 4 flakes de ordenação da suíte (`issue3957` ×2 e `pr1970_lmstudio` ×2) que **passam isolados**. Diff acumulado: `api/{config,profiles,providers,routes,streaming}.py` (+837/−45, fora testes); `routes.py` apenas +23 linhas — handlers do Acervo intactos.

### Resultado da Fase 2 — executado 2026-06-23 (branch `chore/upstream-sync-2026q2-perf`)

Cherry-pick de performance, validado por testes.

| Item de performance | Resultado | Commits |
|---|---|---|
| **Cache do app-shell template (#4774)** | ✅ Aplicado | `c6994b50` (deixa de reler/re-renderizar `index.html` a cada request; cache por (size, mtime_ns)) + `9cc3f30d` (atualiza o guard `test_pwa_manifest_sw` para o helper `_render_index_shell_base` relocado). Testes 46/46. |
| **Cache mtime do config (#4662 Phase 2)** | ✅ Aplicado | `8006db22` — `_load_yaml_config_file_raw` memoiza o parse de `config.yaml` por (path, mtime_ns, size); `reload_config` no hot-path (profile switch) não re-parseia arquivo inalterado. Teste 3/3. **Resolução manual:** o merge "theirs" interleou mal a função (faltou `st = config_path.stat()`, `return` precoce com expansão deixando o cache morto); substituída pela versão canônica do commit. |
| **TLS handshake não trava o accept loop (#4727)** | ✅ Aplicado | `a43a9365` (-m1) — handshake TLS movido para fora do accept loop em `server.py`. Teste 8/8. |
| Sidebar redaction read-once (#4662) | ⏭️ Pulado | Depende do helper upstream `_sidebar_session_response_item` (ausente no fork, que monta a resposta inline) e **perderia** o campo `attention` do fork. Ganho marginal. |
| Virtual-scroll footer jitter (#4346) | ⏭️ N/A | Patcha o sistema de measurement-delta (`_compensateScrollForMeasurementDelta`/`vscroll-measuring`) que **não existe** no fork (feature pós-base). |

**Regressão:** suíte completa **9044 passaram / 17 falharam** — as mesmas 17 pré-existentes da Fase 1 (zero novas; a 18ª falha transitória foi o próprio guard do #4774, corrigido por `9cc3f30d`).

> **Promoção (local):** Fase 1 e Acervo UX **mescladas em `exocortex/stable`** (merges `--no-ff`); Fase 2 mesclada em seguida. **Nada foi pushado para `origin` nem reiniciado em produção (porta 8787).** Atualizar a linha "Base atual" e push/restart ficam para uma janela de promoção dedicada.

---

## HW-1 — Estratégia de sync com upstream (reauditoria 2026-07-10)

> Reauditoria pedida pelo owner ("aderir melhor ao upstream do fork, mantendo o
> acervo o mais independente possível"), a ser feita **antes** do passe final de
> validação human+agente. **Esta seção é uma DECISÃO DE ESTRATÉGIA aguardando
> sign-off do owner** — nada foi executado; a sincronização em si é uma sessão
> própria de risco sobre uma superfície de PRODUÇÃO AO VIVO (8787 serve o acervo
> real com escrita).

### Divergência atual (mudou muito desde 2026-06-23)

| Métrica | 2026-06-23 | **2026-07-10** |
|---|---|---|
| Base (merge-base) | `v0.51.448` (`32458c44`) | `v0.51.448` — **inalterada** |
| Upstream HEAD | `v0.51.607` | **`exp-v0.52.26`** (`157714a1`) |
| À frente / atrás | 18 / **607** | 77 / **2681** |
| `api/routes.py` (upstream desde a base) | +3.427 | **+8.413 / −871** |
| `static/index.html` (upstream desde a base) | +143 | +300 / −90 |

O cherry-pick incremental **não está fechando o gap** — o atraso quase quadruplicou
(607 → 2681) em ~1 mês, e o upstream cruzou uma minor (`v0.51` → `v0.52`).

### Achado decisivo — a superfície de conflito do fork é 100% aditiva e centrada no acervo

Medindo o lado do **fork** nos arquivos compartilhados (o que um sync teria de re-aplicar):

- `api/routes.py`: fork **+837 / −13**. Dessas, **~627 linhas** são um bloco único de
  `def _handle_acervo_*` / `_handle_artifact_*` / `_acervo_root` / `_normalize_artifact`
  (backend do **MOD-007/008** *inlined* em routes.py, apendado após `_handle_folder_download`)
  — **não editam lógica do upstream, apenas adicionam**. O resto são ganchos pequenos
  (wrapper do fix de credenciais #3961 ~9 linhas; linhas de dispatch dos MODs).
- `static/index.html`: fork **+26 / −37** (régua de abas + includes do acervo).
- Arquivos **fork-owned do acervo** (`api/acervo_explorer.py`, `api/acervo_studio.py`,
  `static/acervo-{explorer,studio}.{js,css}`): **ausentes no upstream** → **zero conflito**.

Ou seja: **nenhum commit do fork reescreve o upstream** — tudo é acréscimo isolável.
Isso torna uma **re-fundação limpa** viável, e é o que melhor honra o objetivo do owner.

### Três estratégias

**A — Cherry-pick incremental contínuo (status quo, comprovado).**
Puxar correções pontuais sobre `exocortex/stable`. Baixo risco por item; **não fecha o
gap** (base continua v0.51.448, atraso volta a crescer); triar 2681+ commits a cada
janela fica cada vez mais caro. Bom só para *hotfixes* críticos.

**B — Merge amplo `upstream/master` → `exocortex/stable` (in-place).**
Um `git merge`. Fecha o gap, mas concentra um conflito **grande** em routes.py (fork
+837 aditivas × upstream +8.413/−871, arquivo de ~18k linhas) + risco difuso em
style.css/ui.js/panels.js/sessions.js. O modo de falha "interleaving" já mordeu antes
(gotcha 2026-06-23: quebrou `_load_yaml_config_file_raw`). Regressão sobre produção ao
vivo. Esforço multi-dia, risco difuso e difícil de revisar.

**C — Re-fundação limpa da camada de customização (RECOMENDADA).**
Nova branch a partir do `upstream/master` atual; re-aplicar **só** a camada do fork:
1. Copiar os 6 arquivos fork-owned do acervo (aplicam limpos — ausentes no upstream).
2. **Extrair** o bloco MOD-007/008 de routes.py para um módulo novo (ex.: `api/acervo_tab.py`)
   e re-plugar pelo mesmo padrão de prefix-dispatch → **zera a superfície em routes.py**.
3. Re-aplicar MOD-001..006 (skin/rebrand/i18n: registry em config.py, bloco em style.css,
   locales, shell em index.html) pontualmente.
4. Triar os cherry-picks de segurança: #3961/#4544 provavelmente **já entrou no upstream
   atual** → dropa; caso contrário, re-aplicar.
5. Re-verificar: suíte pytest completa + `lint:runtime` + smoke ao vivo do acervo em 8787.

Prós: fecha o gap de verdade; risco **concentrado e revisável** (a camada do fork, não
2681 commits de merge); leva ao limite a filosofia do RFC "isolation + near-zero upstream
touch" e **reduz a superfície futura** (MOD-007/008 vira módulo). Contras: reescreve a
linhagem de `exocortex/stable` (é publicada → exige branch v2 + push coordenado); exige
re-verificação completa; tem o trabalho de extração do MOD-007/008.

### Recomendação

**Estratégia C** como direção — é a única que realmente "adere melhor ao upstream" e
ainda deixa o acervo mais independente. **Interino, independente da escolha:** rodar uma
triagem de segurança dos 2681 commits e cherry-pickar só *hotfixes* críticos (Estratégia
A) já, para não ficar exposto enquanto a re-fundação é agendada.

**Decisão do owner necessária antes de executar:** (1) A, B ou C; (2) se C, aprovar a
extração do MOD-007/008 para módulo e a criação de `exocortex/stable` v2; (3) janela —
o owner quer HW-1 **antes** do passe final de validação, e produção ao vivo (8787) está
em jogo.

### Triagem de segurança dos 2681 commits (2026-07-10)

Passo interino/insumo da Estratégia C. Agente varreu `32458c44..upstream/master`
(~45 commits em ~20 clusters), cada linha confirmada lendo o diff **e** conferindo se a
superfície existe no fork. **Notícia boa: quase tudo é moot ou já aplicado. Um único
achado crítico.**

- 🔴 **RCE do terminal embutido sem gate** — upstream `d257e5f3` (+ `34342b9f`, #5857/#5764).
  Os 5 handlers do terminal do fork (`_handle_terminal_start/input/resize/close/output`,
  `api/routes.py:10890+`, dispatch `:9073-9082`) **não têm** gate de origem local; e
  `check_auth` retorna `True` incondicionalmente quando **passwordless** (`api/auth.py:568`,
  via `is_auth_enabled()`). O `_onboarding_gate_allows`/`_onboarding_request_is_local`
  existe no fork mas **não** é aplicado ao terminal. Num bind passwordless, qualquer
  request (direto ou **drive-by de browser** cross-origin, agravado pelo CORS `*` — ver
  🟠) abre um shell como o usuário do servidor. Fix upstream = adicionar o gate local aos
  handlers do terminal.
  > **⚠️ Verificação da instância AO VIVO (2026-07-10, importante):** a 8787 atual **NÃO
  > está exposta** — probe `POST /api/terminal/start` → **HTTP 401** (`Authentication
  > required`), i.e. **auth ESTÁ habilitada** na instância provisionada (contradiz o
  > "no password" do ledger de 2026-07-04 — foi reconfigurada, ou passkey), **e** o bind é
  > `127.0.0.1:8787` (localhost). Portanto é um **bug latente no código**, não uma
  > exposição ativa. Ainda assim vale corrigir (defense-in-depth; a postura passwordless
  > é documentada como padrão → um restart sem senha reexpõe). **A re-fundação (Estratégia
  > C) já traz o fix de graça**; se C não for imediata, cherry-pick `d257e5f3`+`34342b9f`
  > como interino. Não empurrar para produção sem gate do owner (EX-08).
- 🟠 **CORS preflight `Access-Control-Allow-Origin: *`** — `4e8978f0`. `server.py:424
  do_OPTIONS` emite `*`. Fix depende de `_check_same_origin_browser_request` (o fork
  substituiu por token-CSRF `_check_csrf`/`_allowed_public_origins`) → **adaptar** (ecoar
  Origin só se permitido, `Vary: Origin`, nunca `*`). Compõe o vetor drive-by do 🔴.
- 🟡 Redação de segredos no tool-card (`#4926/#4928`) — o `_redactToolTargetLabel`
  (`static/ui.js:10872`) mascara só `sshpass -p`/`password=`; não `--token`/`--api-key`/
  headers/`FOO=secret`. Baixa urgência (labels truncados ~112 chars). + correção-só:
  `0d3ee7de` write atômico de `settings.json` + `state.db` read-only (integridade).
- **Moot (não portar):** TTS SSRF (#5079/#5291/#5407/#5430 — o `/api/tts` do fork é
  Edge-TTS custom, endpoint fixo, sem base_url do usuário); OIDC SSO (`api/auth_oidc.py`
  inexistente no fork); skin-picker XSS (`registerHermesSkin` ausente); subagent
  writable-session (#5307 — feature ausente; *confirmar* antes de descartar);
  STREAM_SESSION_OWNERS (símbolo ausente). **Já aplicado:** follow-ups #3961
  (credential-scrub em `profiles.py:754+`), symlink memory-write (#4242, rejeitado em
  `routes.py:15783+`), remote workspace trust (#3664, `safe_resolve_ws`/O_NOFOLLOW).

**Resumo:** um único buraco crítico real e latente (RCE do terminal), **não ativo** na
8787 atual (auth on + localhost). Prioridade dentro do HW-1, resolvido pela re-fundação
ou por cherry-pick interino `d257e5f3`+`34342b9f`.



### HW-1 — EXECUTADO (Strategy C, 2026-07-14)

Re-fundação limpa concluída em `exocortex/stable-v2` (worktree `.worktrees/hw1-v2`) e
promovida a `exocortex/stable` no cutover. Fatos:

- **Base nova:** `upstream/master` @ `exp-v0.52.61` (`d486394f`); gap fechado de 2850/124.
  A linhagem antiga vive na tag **`pre-refound-2026-07-13`** (pushada ao origin).
- **Extração MOD-007/008 → `api/acervo_tab.py`:** o bloco inline (~620 linhas,
  `_read_frontmatter_title` → `_handle_artifact_receipt` + inbox handlers) movido verbatim;
  helpers core acessados via `routes.<name>` com `import api.routes as routes` no FIM do
  módulo (circular-safe nas duas direções). `routes.py` agora tem ≈30 linhas de superfície
  acervo: 2 delegações de dispatch + bloco de re-export (`_ACERVO_NATURES`,
  `_ACERVO_UI_STATUSES`, `_acervo_root`, `_read_frontmatter_meta`, `_read_frontmatter_title`,
  `_humanize_slug`, `_handle_acervo_status`, `_handle_acervo_stage_context`) — os módulos
  fork-owned continuam byte-idênticos referenciando `routes.<name>`.
  ⚠️ Lição do review: os dispatchers devem retornar **True** no match (os handlers retornam
  `routes.j()` → None; devolver None fazia o server emitir uma SEGUNDA resposta 404 —
  dessinc de keep-alive). Corrigido + teste de 3 requests na mesma conexão.
- **Classificação (docs/hw1/CLASSIFICATION.md):** cherry-picks 2026-06-23 **DROPados**
  (já upstream): #3961/#4544 credential-scrub (profiles.py inteiro), #4727 TLS accept
  (server.py inteiro), #4650/#4662 config caching, #4774 shell-cache. **REAPPLY** = só a
  camada MOD (skin/i18n/shell/acervo) + `_resolve_session_workspace`/`_enrich_artifact_entries`/
  hooks do list_dir/sha256-no-save.
- **Segurança de graça:** o RCE do terminal (gate `_embedded_terminal_gate_allows` + teste
  CVD3) e o CORS same-origin (`Vary: Origin`, nunca `*`) **já estão no v0.52** — zero
  cherry-picks de segurança pendentes.
- **Contratos de teste novos do v0.52 absorvidos:** cobertura por-locale (as 16 chaves
  `artifact_*`/`inbox_*` traduzidas em TODOS os locales, inseridas após `_label`/`_lang`);
  `verdigris)` como skin final no `cmd_theme` (excrtx entra ANTES); tema boot default
  `dark`; a linha-marcador literal `let _workspacePanelActiveTab = 'files';` preservada
  (reassinada para 'artifacts' na linha seguinte) p/ os testes 4582.
- **Verificação:** suíte completa **12.982 pass** (únicas falhas persistentes = 2
  `test_tls_aware_probe` que falham igualmente no upstream puro — ambiente);
  MOD-010 **154/154**; MOD-009 **24/24**; lint clean; smoke ao vivo em fixture com agente
  online (capture→triage→promote-plane→publish-gate→assist→ask todos live); review
  whole-branch (opus): 1 Critical (dispatch, corrigido) + 5 invariantes PASS.
- **Risco futuro de conflito:** a tabela antiga de risco por arquivo fica OBSOLETA para o
  acervo — `routes.py` caiu de +837 para +76 linhas fork-side. Maior superfície restante:
  `static/index.html` (shell/rebrand) e `static/i18n.js` (chaves por locale).
