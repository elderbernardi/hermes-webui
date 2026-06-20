/* Acervo view — human-facing artifact catalog for the right workspace panel.
 * MOD-007 (EXCRTX fork). Reads the Exocortex artifact manifest schema via
 * GET /api/acervo/artifacts and renders friendly names, status lanes, the
 * "this session" band, and Drive export — instead of raw slugs in the file tree.
 * Self-contained: depends only on globals S, api, $, esc, showToast,
 * showConfirmDialog, openFile, switchWorkspacePanelTab, collectSessionArtifacts. */

let _acervoData = null;          // last fetched array, or null = not loaded
let _acervoLoading = false;
let _acervoView = 'pipeline';    // pipeline | microverso | task | gallery
let _acervoDetailId = null;      // when set, the detail drawer is open
let _acervoFetchedFor = null;    // session_id the cache belongs to
let _acervoShowNotes = false;    // loose .md notes hidden by default (declutter)
let _acervoShowArchived = false; // archived artifacts hidden by default

// Bilingual labels — the app default skin (excrtx) ships pt; fall back to en.
function _acL(pt, en){
  const lang = (document.documentElement.lang || 'pt').slice(0,2);
  return lang === 'en' ? en : pt;
}

const _AC_STATUS = {
  draft:             {color:'#8f8a91', label:()=>_acL('Rascunho','Draft')},
  ready:             {color:'#1376ed', label:()=>_acL('Pronto','Ready')},
  approved:          {color:'#0ea5e9', label:()=>_acL('Aprovado','Approved')},
  'ask-publication': {color:'#f59e0b', label:()=>_acL('Aguarda publicação','Awaiting publish')},
  published:         {color:'#22c55e', label:()=>_acL('Publicado','Published')},
  pending:           {color:'#f59e0b', label:()=>_acL('Pendente','Pending')},
  initialized:       {color:'#f59e0b', label:()=>_acL('Iniciado','Initialized')},
  extracted:         {color:'#a855f7', label:()=>_acL('Extraído','Extracted')},
  moved:             {color:'#8f8a91', label:()=>_acL('Movido','Moved')},
  archived:          {color:'#a8a4ad', label:()=>_acL('Arquivado','Archived')},
  failed:            {color:'#ef4444', label:()=>_acL('Falhou','Failed')},
  loose:             {color:'#8f8a91', label:()=>_acL('Nota','Note')},
  unknown:           {color:'#8f8a91', label:()=>_acL('—','—')},
};
function _acStatus(s){ return _AC_STATUS[s] || _AC_STATUS.unknown; }

function _acTypeIcon(type){
  return ({
    document:'📄', report:'📋', slide:'🖼️', slides:'🖼️', spreadsheet:'📊',
    sheet:'📊', image:'🏞️', note:'📝', folder:'📁', html:'🌐', pdf:'📕',
  })[type] || '📄';
}

// Lanes for the Pipeline (Kanban-by-status) view. Anything unmapped → "Outros".
const _AC_LANES = [
  {key:'draft',     statuses:['draft'],                        label:()=>_acL('Rascunho','Draft')},
  {key:'ready',     statuses:['ready','pending','initialized','extracted'], label:()=>_acL('Pronto','Ready')},
  {key:'published', statuses:['published'],                    label:()=>_acL('Publicado','Published')},
  {key:'other',     statuses:null,                             label:()=>_acL('Outros','Other')},
];

/* ---- session cross-reference: which artifacts were touched this turn ---- */
function _acSessionIds(){
  const ids = new Set();
  try{
    const items = (typeof collectSessionArtifacts==='function') ? collectSessionArtifacts() : [];
    for(const it of items){
      const m = String(it && it.path || '').match(/_artifacts\/items\/([^/]+)/);
      if(m) ids.add(m[1]);
    }
  }catch(_){}
  return ids;
}

/* ----------------------------- data ----------------------------- */
async function _acFetch(force){
  if(!S.session){ _acervoData = null; return; }
  const sid = S.session.session_id;
  if(!force && _acervoData && _acervoFetchedFor === sid) return;
  _acervoLoading = true;
  try{
    const data = await api('/api/acervo/artifacts?session_id='+encodeURIComponent(sid));
    _acervoData = Array.isArray(data && data.artifacts) ? data.artifacts : [];
    _acervoFetchedFor = sid;
  }catch(e){
    _acervoData = [];
    if(typeof showToast==='function') showToast(_acL('Falha ao carregar o acervo','Failed to load Acervo'), 4000, 'error');
  }finally{
    _acervoLoading = false;
  }
}

/* ----------------------------- entry ----------------------------- */
async function renderAcervo(force){
  const root = $('workspaceAcervo');
  if(!root) return;
  if(!S.session){
    root.innerHTML = '<div class="acervo-empty">'+esc(_acL('Abra uma conversa para ver o acervo.','Open a conversation to see the Acervo.'))+'</div>';
    return;
  }
  if(_acervoData === null || force){
    root.innerHTML = '<div class="acervo-empty">'+esc(_acL('Carregando acervo…','Loading Acervo…'))+'</div>';
    await _acFetch(force);
  }
  if(_acervoDetailId){ _acRenderDetail(root); return; }
  _acRenderCatalog(root);
}

function _acRenderCatalog(root){
  const data = _acervoData || [];
  const sessionIds = _acSessionIds();
  const views = [
    {k:'pipeline',  l:_acL('Pipeline','Pipeline')},
    {k:'microverso',l:_acL('Microverso','Microverse')},
    {k:'task',      l:_acL('Tarefa','Task')},
    {k:'gallery',   l:_acL('Galeria','Gallery')},
  ];
  const chips = views.map(v =>
    `<button type="button" class="acervo-chip${_acervoView===v.k?' active':''}" onclick="setAcervoView('${v.k}')">${esc(v.l)}</button>`
  ).join('');
  // Declutter filters: loose notes and archived items are hidden by default.
  const noteCount = data.filter(a => a.kind === 'note').length;
  const archivedCount = data.filter(a => a.status === 'archived').length;
  const filtered = data.filter(a =>
    (_acervoShowNotes || a.kind !== 'note') &&
    (_acervoShowArchived || a.status !== 'archived'));
  const toggles =
    (noteCount ? `<button type="button" class="acervo-toggle${_acervoShowNotes?' on':''}" onclick="acervoToggleNotes()">${esc(_acL('Notas','Notes'))} ${noteCount}</button>` : '') +
    (archivedCount ? `<button type="button" class="acervo-toggle${_acervoShowArchived?' on':''}" onclick="acervoToggleArchived()">${esc(_acL('Arquivados','Archived'))} ${archivedCount}</button>` : '');
  let html = `<div class="acervo-toolbar">
    <div class="acervo-views">${chips}</div>
    <div class="acervo-tools">
      ${toggles}
      <span class="acervo-count">${filtered.length}</span>
      <button type="button" class="acervo-icon-btn" title="${esc(_acL('Atualizar','Refresh'))}" onclick="renderAcervo(true)">⟳</button>
    </div>
  </div><div class="acervo-body">`;

  if(!data.length){
    html += '<div class="acervo-empty">'+esc(_acL('Nenhum artefato no acervo ainda. Artefatos produzidos em tarefas aparecem aqui.','No artifacts yet. Artifacts produced in tasks appear here.'))+'</div>';
  }else{
    // "Nesta sessão" band — items being worked on right now (never filtered out).
    const worked = data.filter(a => sessionIds.has(a.id));
    if(worked.length){
      html += `<div class="acervo-band">
        <div class="acervo-band-title">● ${esc(_acL('Nesta sessão','This session'))} <span class="acervo-count">${worked.length}</span></div>
        <div class="acervo-grid">${worked.map(a=>_acCard(a, sessionIds)).join('')}</div>
      </div>`;
    }
    if(!filtered.length){
      html += '<div class="acervo-empty">'+esc(_acL('Nada para mostrar com os filtros atuais.','Nothing to show with the current filters.'))+'</div>';
    }else{
      html += _acViewBody(filtered, sessionIds);
    }
  }
  html += '</div>';
  root.innerHTML = html;
}

function _acViewBody(data, sessionIds){
  if(_acervoView === 'pipeline') return _acRenderPipeline(data, sessionIds);
  if(_acervoView === 'gallery')  return _acRenderGallery(data, sessionIds);
  const keyOf = _acervoView === 'microverso'
    ? (a => a.primary_microverso || _acL('Sem microverso','No microverse'))
    : (a => a.task_id || _acL('Sem tarefa','No task'));
  return _acRenderGroups(data, sessionIds, keyOf);
}

function _acRenderPipeline(data, sessionIds){
  const used = new Set();
  const lanes = _AC_LANES.map(lane => {
    const items = data.filter(a => {
      if(lane.statuses === null) return !used.has(a.id);
      const hit = lane.statuses.includes(a.status);
      if(hit) used.add(a.id);
      return hit;
    });
    return {lane, items};
  });
  return '<div class="acervo-lanes">'+lanes.map(({lane,items}) =>
    `<div class="acervo-lane">
       <div class="acervo-lane-head">${esc(lane.label())} <span class="acervo-count">${items.length}</span></div>
       <div class="acervo-lane-body">${items.length?items.map(a=>_acCard(a,sessionIds)).join(''):'<div class="acervo-lane-empty">—</div>'}</div>
     </div>`
  ).join('')+'</div>';
}

function _acRenderGroups(data, sessionIds, keyOf){
  const groups = {};
  for(const a of data){ const k = keyOf(a); (groups[k] = groups[k] || []).push(a); }
  const keys = Object.keys(groups).sort();
  return keys.map(k =>
    `<div class="acervo-group">
       <div class="acervo-group-head">${esc(k)} <span class="acervo-count">${groups[k].length}</span></div>
       <div class="acervo-grid">${groups[k].map(a=>_acCard(a,sessionIds)).join('')}</div>
     </div>`
  ).join('');
}

function _acRenderGallery(data, sessionIds){
  return '<div class="acervo-grid acervo-grid-wide">'+data.map(a=>_acCard(a,sessionIds)).join('')+'</div>';
}

/* ----------------------------- card ----------------------------- */
function _acCard(a, sessionIds){
  const st = _acStatus(a.status);
  const worked = sessionIds && sessionIds.has(a.id);
  const micro = a.primary_microverso ? `<span class="acervo-micro">${esc(a.primary_microverso)}</span>` : '';
  const evalled = a.evaluation_status && a.evaluation_status !== 'pending'
    ? `<span class="acervo-eval" title="${esc(_acL('Avaliado','Evaluated'))}">✓</span>` : '';
  return `<button type="button" class="acervo-card${worked?' worked':''}" onclick="openAcervoDetail('${esc(a.id)}')">
    <div class="acervo-card-top">
      <span class="acervo-ico">${_acTypeIcon(a.artifact_type)}</span>
      <span class="acervo-name" title="${esc(a.title||a.friendly_name)}">${esc(a.friendly_name)}</span>
      ${worked?'<span class="acervo-dot" title="'+esc(_acL('Trabalhado nesta sessão','Worked this session'))+'"></span>':''}
    </div>
    <div class="acervo-card-meta">
      <span class="acervo-pill" style="--pill:${st.color}">${esc(st.label())}</span>
      ${micro}${evalled}
    </div>
  </button>`;
}

/* ----------------------------- detail ----------------------------- */
function openAcervoDetail(id){ _acervoDetailId = id; renderAcervo(false); }
function closeAcervoDetail(){ _acervoDetailId = null; renderAcervo(false); }
function setAcervoView(v){ _acervoView = v; renderAcervo(false); }
function acervoToggleNotes(){ _acervoShowNotes = !_acervoShowNotes; renderAcervo(false); }
function acervoToggleArchived(){ _acervoShowArchived = !_acervoShowArchived; renderAcervo(false); }

function _acRow(label, value){
  if(value === null || value === undefined || value === '') return '';
  return `<div class="acervo-row"><span class="acervo-k">${esc(label)}</span><span class="acervo-v">${esc(String(value))}</span></div>`;
}

function _acRenderDetail(root){
  const a = (_acervoData||[]).find(x => x.id === _acervoDetailId);
  if(!a){ closeAcervoDetail(); return; }
  const st = _acStatus(a.status);
  const isPackage = a.kind === 'package' && a.has_manifest !== false;
  const published = a.status === 'published' || a.publication_status === 'published';

  let actions = `<button type="button" class="acervo-act" onclick="acervoOpenSource('${esc(a.id)}')">${esc(_acL('Abrir fonte','Open source'))}</button>`;
  if(isPackage){
    actions += `<button type="button" class="acervo-act" onclick="acervoDownload('${esc(a.id)}')">${esc(_acL('Baixar .zip','Download .zip'))}</button>`;
    if(published && a.drive_link){
      actions += `<a class="acervo-act primary" href="${esc(a.drive_link)}" target="_blank" rel="noopener">${esc(_acL('Ver no Drive','View in Drive'))}</a>`;
    }else if(a.status !== 'archived'){
      actions += `<button type="button" class="acervo-act primary" onclick="acervoPublish('${esc(a.id)}')">${esc(_acL('Publicar no Drive','Publish to Drive'))}</button>`;
    }
  }

  // Lifecycle: status transitions edit the manifest's owned `status` field.
  let lifecycle = '';
  if(isPackage){
    if(a.status === 'draft'){
      lifecycle += `<button type="button" class="acervo-act" onclick="acervoSetStatus('${esc(a.id)}','ready')">${esc(_acL('Promover p/ Pronto','Promote to Ready'))}</button>`;
    }else if(a.status === 'ready'){
      lifecycle += `<button type="button" class="acervo-act" onclick="acervoSetStatus('${esc(a.id)}','draft')">${esc(_acL('Voltar p/ Rascunho','Back to Draft'))}</button>`;
    }
    if(a.status === 'archived'){
      lifecycle += `<button type="button" class="acervo-act" onclick="acervoSetStatus('${esc(a.id)}','draft')">${esc(_acL('Restaurar','Restore'))}</button>`;
    }else{
      lifecycle += `<button type="button" class="acervo-act danger" onclick="acervoSetStatus('${esc(a.id)}','archived')">${esc(_acL('Arquivar','Archive'))}</button>`;
    }
  }

  const meta = [
    _acRow(_acL('Status','Status'), st.label()),
    _acRow(_acL('Tipo','Type'), a.artifact_type),
    _acRow(_acL('Microverso','Microverse'), a.primary_microverso),
    _acRow(_acL('Tarefa','Task'), a.task_id),
    _acRow(_acL('Escopo','Scope'), a.scope),
    _acRow(_acL('Avaliação','Evaluation'), a.evaluation_status),
    _acRow(_acL('Publicação','Publication'), a.publication_status),
    _acRow(_acL('Criado em','Created'), a.created_at),
    _acRow(_acL('Origem','Origin'), a.origin),
    _acRow(_acL('Identificador','Identifier'), a.id),
  ].join('');

  root.innerHTML = `<div class="acervo-detail">
    <div class="acervo-detail-head">
      <button type="button" class="acervo-back" onclick="closeAcervoDetail()">‹ ${esc(_acL('Voltar','Back'))}</button>
    </div>
    <div class="acervo-detail-title">
      <span class="acervo-ico-lg">${_acTypeIcon(a.artifact_type)}</span>
      <span>${esc(a.friendly_name)}</span>
    </div>
    <div class="acervo-detail-status"><span class="acervo-pill" style="--pill:${st.color}">${esc(st.label())}</span></div>
    <div class="acervo-actions">${actions}</div>
    ${lifecycle?`<div class="acervo-actions acervo-lifecycle">${lifecycle}</div>`:''}
    <div class="acervo-meta">${meta}</div>
  </div>`;
}

/* ----------------------------- actions ----------------------------- */
async function acervoOpenSource(id){
  const a = (_acervoData||[]).find(x => x.id === id);
  if(!a || !a.rel_path){ if(typeof showToast==='function') showToast(_acL('Sem fonte para abrir','No source to open'),3000); return; }
  switchWorkspacePanelTab('files');
  try{ openFile(a.rel_path.replace(/\/$/,'')); }catch(_){ if(typeof showToast==='function') showToast(_acL('Não foi possível abrir','Could not open'),3000,'error'); }
}

function acervoDownload(id){
  if(!S.session) return;
  window.location.href = '/api/artifact/zip?session_id='+encodeURIComponent(S.session.session_id)+'&id='+encodeURIComponent(id);
}

async function acervoSetStatus(id, status){
  if(!S.session) return;
  if(status === 'archived'){
    const a = (_acervoData||[]).find(x => x.id === id);
    const name = a ? a.friendly_name : id;
    let ok = true;
    const msg = _acL('Arquivar “'+name+'”? Ele sai das vistas padrão (recuperável via "Arquivados").','Archive “'+name+'”? It leaves the default views (recoverable via "Archived").');
    if(typeof showConfirmDialog==='function') ok = await showConfirmDialog({title:_acL('Arquivar','Archive'), message:msg, confirmLabel:_acL('Arquivar','Archive')});
    else ok = window.confirm(msg);
    if(!ok) return;
  }
  try{
    await api('/api/acervo/status',{method:'POST',body:JSON.stringify({session_id:S.session.session_id,artifact_id:id,status:status})});
    if(typeof showToast==='function') showToast(_acL('Status atualizado','Status updated'), 2500, 'success');
    closeAcervoDetail();
    await renderAcervo(true);
  }catch(e){
    if(typeof showToast==='function') showToast(_acL('Falha ao atualizar status','Status update failed')+(e&&e.message?': '+e.message:''), 6000, 'error');
  }
}

async function acervoPublish(id){
  if(!S.session) return;
  const a = (_acervoData||[]).find(x => x.id === id);
  const name = a ? a.friendly_name : id;
  // Draft-First: external publication is explicit and confirmed.
  const msg = _acL('Publicar “'+name+'” no Google Drive? Esta é uma ação externa.','Publish “'+name+'” to Google Drive? This is an external action.');
  let ok = true;
  if(typeof showConfirmDialog==='function'){
    ok = await showConfirmDialog({title:_acL('Publicar no Drive','Publish to Drive'), message:msg, confirmLabel:_acL('Publicar','Publish')});
  }else{
    ok = window.confirm(msg);
  }
  if(!ok) return;
  if(typeof showToast==='function') showToast(_acL('Publicando…','Publishing…'), 3000);
  try{
    const r = await api('/api/artifact/publish',{method:'POST',body:JSON.stringify({session_id:S.session.session_id,artifact_id:id}),timeoutMs:300000});
    if(typeof showToast==='function') showToast(_acL('Publicado no Drive','Published to Drive'), 4000, 'success');
    await renderAcervo(true);
    if(r && r.drive_link){ window.open(r.drive_link,'_blank','noopener'); }
  }catch(e){
    if(typeof showToast==='function') showToast(_acL('Falha ao publicar','Publish failed')+(e&&e.message?': '+e.message:''), 6000, 'error');
  }
}
