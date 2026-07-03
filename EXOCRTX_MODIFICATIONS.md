# EXOCRTX_MODIFICATIONS.md

Catálogo das modificações Exocórtex aplicadas sobre o fork de `nesquena/hermes-webui`.
Cada entrada documenta arquivo, propósito e risco de conflito para guiar o rebase
(`git rebase upstream/master`) e o comando `./ctl.sh update`.

- **Fork:** `elderbernardi/hermes-webui`
- **Branch de produção:** `exocortex/stable` (roda na porta 8787)
- **Base atual (merge-base real):** upstream `v0.51.448` (Release PI, commit `32458c44`) — auditado 2026-06-23. A skin/rebrand (Camada 1) foi originalmente aplicada sobre `v0.51.440`, mas o branch já incorporou merges do upstream até v0.51.448.
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

### MOD-010: Acervo Studio (Phase 0 — read-only)
- **Arquivos:** `api/acervo_explorer.py` (**edit, não novo** — extensão da árvore unificada: helpers `_micro_nodes`/`_inbox_nodes` + os valores `scope=micro`/`scope=inbox` em `handle_tree`, +112/−2 linhas), `static/acervo-studio.js` + `static/acervo-studio.css` (**novos** — surface própria full-screen, 272+83 linhas), `static/index.html` (**3 linhas**: `<link>` do CSS, `<script defer>` do JS, mount `<div id="acervoStudioRoot" hidden>`), `tests/test_mod010_acervo_studio.py` (**novo** — 3 testes herméticos para `_micro_nodes`/`_inbox_nodes`). **`api/routes.py` — 0 linhas**: o Studio reusa o dispatcher de prefixo `/api/acervo/x/` que o MOD-009 já registrou; nenhuma rota nova foi adicionada.
- **Tipo:** backend (read-only, extensão de árvore) + frontend (nova surface) + CSS. **Sucessor da surface**, não do backend: troca o painel docado do MOD-009 por uma view full-screen própria (toggle Chat ⇄ Acervo); Fase 0 é estritamente **read-only** — sem editar/mover/status/tags/stage (isso permanece exclusivo do painel MOD-009 até uma fase futura decidir herdar ou não a escrita).
- **Propósito:** unifica a navegação do acervo — `global`/`shared`/`macro`/`artifacts` (já existentes no MOD-009) mais os dois escopos novos **`micro`** (microversos por slug, com contagem de páginas por natureza, diretórios `_`/`.`-prefixados ocultos) e **`inbox`** (envelopes de `_inbox/incoming/`, título/status lidos do `manifest.json` quando presente, sem extrair nem promover — isso é Fase 2) — numa view full-screen com navegador + leitor + busca por command-bar (`⌘K`-style, `acervoStudioSearch`). Ver spec completa em `docs/rfcs/acervo-studio.md` (esta é a fatia de Fase 0: §4 IA unificada, §5.1 forma, §6 backend, §8 coexistência, §11 Fase 0).
- **Namespaces (distintos do MOD-009):** CSS `.axs-*` (MOD-009 usa `.ax-*`), estado global `AXS` (MOD-009 usa `AX`), funções `acervoStudio*` — `acervoStudioToggle`, `acervoStudioRenderNav`, `acervoStudioSelectScope`, `acervoStudioOpenPage`, `acervoStudioSearch` — expostas em `window.*`; nav emite `data-path`/`data-mv`/`data-scope` consumidos pelos mesmos listeners. Launcher auto-contido próprio (`#axsLauncher`, distinto do `#axLauncher` do MOD-009). IIFE vanilla, `sourceType:"script"` (sem `import`/`export`), reusa globais do app (`S`/`api`/`esc`/`showToast`/`renderMd`/`humanizeFilename`).
- **Tema:** segue o controle de Tema/Skin já existente do app (`System/Dark/Light` + skin) — claro usa a paleta **EXCRTX atual do web-ui** (`#f4f5f8` bg / `#ffffff` surfaces / `#03123f` ink / accent `#1376ed`); escuro usa a paleta nova **"Graphite Neutral"** (`#1b1d21` bg / `#26292e` surfaces / accent `#3b8af0`), desenhada para reduzir a fadiga do navy saturado padrão do EXCRTX em sessões longas. Nenhum controle de tema próprio — reflow automático quando o operador troca em Settings.
- **Rebase-safety:** o novo comportamento vive em **arquivos novos** (`static/acervo-studio.{js,css}`, `tests/test_mod010_acervo_studio.py`) e num edit aditivo ao módulo já fork-owned `api/acervo_explorer.py` (dois `if scope ==` a mais + duas funções privadas). O ponto central: **reuso do dispatch por prefixo `/api/acervo/x/tree`** que o MOD-009 já instalou em `routes.py` — o Studio não precisou tocar `routes.py` em nenhuma linha. `index.html` recebe apenas as mesmas 3 linhas de padrão include/mount que o MOD-009 estabeleceu.
- **Reaplicar se:** upstream reestruturar `handle_tree`/o dispatcher `/api/acervo/x/` (ambos fork-owned, risco baixo) ou a área de includes/mounts do painel direito em `index.html`.
- **Conflito provável:** `api/routes.py` — nulo (zero linhas tocadas). `static/index.html` — baixo (3 linhas de include/mount, mesmo padrão do MOD-009). `api/acervo_explorer.py` — baixo (edit aditivo, fork-owned). `static/acervo-studio.{js,css}`, `tests/test_mod010_acervo_studio.py` — nulo (arquivos novos). Registro COLLAB: `.harness/changes/2026-07-02_collab_hermes-webui-acervo-studio.md` (umbrella). Spec: `docs/rfcs/acervo-studio.md`.

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

