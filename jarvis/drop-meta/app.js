// ============================================================
// DROP-META · App (estado + vistas + IA)
// ============================================================

let state = JSON.parse(localStorage.getItem('dropmeta_state') || 'null');
if (!state) {
  state = { projects: [seedLumbra()], currentId: null, view: 'home' };
  persist();
}
let settings = JSON.parse(localStorage.getItem('dropmeta_settings') || '{"apiKey":"","model":"claude-opus-4-8"}');

function persist() { localStorage.setItem('dropmeta_state', JSON.stringify(state)); }
function persistSettings() { localStorage.setItem('dropmeta_settings', JSON.stringify(settings)); }
function cur() { return state.projects.find(p => p.id === state.currentId) || null; }
function $(id) { return document.getElementById(id); }
function esc(s) { return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
function money(x) { return '$' + (+x || 0).toFixed(2); }
function pct(x) { return isFinite(x) ? (x * 100).toFixed(2) + '%' : '—'; }
function toast(msg) {
  const t = document.createElement('div'); t.className = 'toast'; t.textContent = msg;
  document.body.appendChild(t); setTimeout(() => t.remove(), 2600);
}

// setF('economics.price', v, true) — asigna en el proyecto actual y guarda
function setF(path, value, isNum) {
  const p = cur(); if (!p) return;
  const keys = path.split('.'); let o = p;
  for (let i = 0; i < keys.length - 1; i++) o = o[keys[i]];
  o[keys[keys.length - 1]] = isNum ? (+value || 0) : value;
  persist();
}
function setFR(path, value, isNum) { setF(path, value, isNum); render(); }

// ---------- Navegación ----------
const NAV = [
  { id: 'home', ic: '🏠', t: 'Proyectos', ph: '' },
  { sec: 'Investigación' },
  { id: 'radar', ic: '📡', t: 'Radar de productos', ph: 'F1' },
  { id: 'scoring', ic: '🎯', t: 'Scoring & Ranking', ph: 'F2' },
  { id: 'winner', ic: '🏆', t: 'Ganador & Economía', ph: 'F3' },
  { id: 'comp', ic: '⚔️', t: 'Competencia', ph: 'F4' },
  { sec: 'Construcción' },
  { id: 'brand', ic: '🎨', t: 'Marca', ph: 'F5' },
  { id: 'avatar', ic: '🧠', t: 'Estrategia & Avatar', ph: 'F6' },
  { id: 'hooks', ic: '🪝', t: 'Hooks', ph: 'F7' },
  { id: 'scripts', ic: '🎬', t: 'Conceptos & Guiones', ph: 'F8' },
  { id: 'prompts', ic: '🤖', t: 'Prompts de IA', ph: 'F9' },
  { id: 'landing', ic: '🛬', t: 'Landing', ph: 'F10' },
  { id: 'store', ic: '🛒', t: 'Tienda', ph: 'F11' },
  { sec: 'Operación' },
  { id: 'launch', ic: '🚀', t: 'Lanzamiento', ph: 'F12' },
  { id: 'dash', ic: '📊', t: 'Dashboard', ph: 'F13' },
  { id: 'shopify', ic: '🔗', t: 'Shopify (live)', ph: '' },
  { id: 'ai', ic: '✨', t: 'Analista IA', ph: '' },
];

function nav(view) {
  if (view !== 'home' && view !== 'ai' && !cur()) { toast('Primero abre o crea un proyecto'); view = 'home'; }
  state.view = view; persist(); render();
}

function render() {
  const p = cur();
  const side = NAV.map(n => n.sec
    ? `<div class="nav-sec">${n.sec}</div>`
    : `<button class="nav-item ${state.view === n.id ? 'active' : ''}" onclick="nav('${n.id}')"><span>${n.ic}</span> ${n.t} <span class="ph">${n.ph}</span></button>`
  ).join('');
  $('sidebar').innerHTML = `
    <div class="logo"><b>DROP</b>-META<small>Operador de dropshipping</small></div>
    ${p ? `<div class="proj-pill">Proyecto activo<b>${esc(p.name)}</b></div>` : ''}
    ${side}`;
  const views = { home: vHome, radar: vRadar, scoring: vScoring, winner: vWinner, comp: vComp, brand: vBrand, avatar: vAvatar, hooks: vHooks, scripts: vScripts, prompts: vPrompts, landing: vLanding, store: vStore, launch: vLaunch, dash: vDash, shopify: vShopify, ai: vAI };
  $('main').innerHTML = (views[state.view] || vHome)();
  window.scrollTo(0, 0);
}

function head(t, d, extra) {
  return `<div class="head"><div><h2>${t}</h2><p>${d}</p></div><div class="row">${extra || ''}</div></div>`;
}
function aiBtn(label, fnCall) {
  return `<button class="btn ai small" onclick="${fnCall}">✨ ${label}</button>`;
}

// ============================================================
// HOME · Proyectos
// ============================================================
function vHome() {
  const cards = state.projects.map(p => {
    const w = p.candidates.find(c => c.id === p.winnerId);
    const ec = economics(p.economics);
    return `<div class="proj-card" onclick="openProject('${p.id}')">
      <h3>${esc(p.name)}</h3>
      <div class="sub">${esc(p.producto || (w ? w.name : 'Sin producto definido aún'))}</div>
      <div class="row" style="margin-top:10px">
        ${p.candidates.length ? `<span class="tag dim">${p.candidates.length} candidatos</span>` : ''}
        ${w ? `<span class="tag ok">Ganador: ${esc(w.name)}</span>` : '<span class="tag warn">Sin ganador</span>'}
        ${ec.price ? `<span class="tag ${ec.beRoas <= 1.6 ? 'ok' : ec.beRoas <= 2.3 ? 'warn' : 'bad'}">BE ROAS ${ec.beRoas.toFixed(2)}</span>` : ''}
        ${p.metrics.length ? `<span class="tag info">${p.metrics.length} registros de métricas</span>` : ''}
      </div>
      <div class="row" style="margin-top:12px" onclick="event.stopPropagation()">
        <button class="btn small ghost" onclick="exportProject('${p.id}')">Exportar</button>
        <button class="btn small danger" onclick="deleteProject('${p.id}')">Eliminar</button>
      </div>
    </div>`;
  }).join('');
  return head('Tus marcas', 'Cada proyecto es una marca/producto que pasa por las 13 fases. LUMBRA viene precargado como ejemplo real con toda la metodología aplicada.') + `
  <div class="row" style="margin-bottom:18px">
    <input id="newProjName" placeholder="Nombre del nuevo proyecto…" style="max-width:280px">
    <button class="btn" onclick="createProject()">+ Crear proyecto</button>
    <button class="btn ghost" onclick="$('importFile').click()">Importar JSON</button>
    <input type="file" id="importFile" accept=".json" style="display:none" onchange="importProject(event)">
  </div>
  <div class="grid2">${cards || '<div class="empty">Sin proyectos.</div>'}</div>
  <div class="panel" style="margin-top:20px">
    <h3 style="margin-top:0">⚙️ Motor de IA (opcional)</h3>
    <p style="color:var(--muted);font-size:13px">Drop-Meta funciona 100% local. Si conectas una API key de Anthropic, cada módulo puede generar y analizar con IA usando la metodología del operador. La key se guarda solo en tu navegador.</p>
    <div class="row" style="margin-top:10px">
      <input id="apiKey" type="password" placeholder="sk-ant-…" value="${esc(settings.apiKey)}" style="max-width:320px">
      <select id="aiModel" style="max-width:220px">
        <option value="claude-opus-4-8" ${settings.model === 'claude-opus-4-8' ? 'selected' : ''}>Opus 4.8 (recomendado)</option>
        <option value="claude-sonnet-5" ${settings.model === 'claude-sonnet-5' ? 'selected' : ''}>Sonnet 5 (más barato)</option>
        <option value="claude-haiku-4-5" ${settings.model === 'claude-haiku-4-5' ? 'selected' : ''}>Haiku 4.5 (rápido)</option>
      </select>
      <button class="btn" onclick="saveSettings()">Guardar</button>
      <span class="tag ${settings.apiKey ? 'ok' : 'dim'}">${settings.apiKey ? 'IA conectada' : 'Sin conectar'}</span>
    </div>
  </div>`;
}
function createProject() {
  const name = $('newProjName').value.trim(); if (!name) return toast('Ponle nombre');
  const p = blankProject(name); state.projects.push(p); state.currentId = p.id; state.view = 'radar'; persist(); render();
}
function openProject(id) { state.currentId = id; state.view = 'radar'; persist(); render(); }
function deleteProject(id) {
  const p = state.projects.find(x => x.id === id);
  if (!confirm(`¿Eliminar "${p.name}" y todos sus datos? Exporta antes si quieres respaldo.`)) return;
  state.projects = state.projects.filter(x => x.id !== id);
  if (state.currentId === id) state.currentId = null;
  persist(); render();
}
function exportProject(id) {
  const p = state.projects.find(x => x.id === id);
  const blob = new Blob([JSON.stringify(p, null, 2)], { type: 'application/json' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = `dropmeta-${p.name.toLowerCase().replace(/\s+/g, '-')}.json`; a.click();
}
function importProject(ev) {
  const f = ev.target.files[0]; if (!f) return;
  const r = new FileReader();
  r.onload = () => { try { const p = JSON.parse(r.result); p.id = 'p' + Date.now().toString(36); state.projects.push(p); persist(); render(); toast('Importado'); } catch (e) { toast('JSON inválido'); } };
  r.readAsText(f);
}
function saveSettings() { settings.apiKey = $('apiKey').value.trim(); settings.model = $('aiModel').value; persistSettings(); render(); toast('Guardado'); }

// ============================================================
// F1 · RADAR
// ============================================================
function vRadar() {
  const p = cur();
  const rows = p.candidates.map(c => {
    const passed = FILTER_CRITERIA.filter(f => c.filter[f.k]).length;
    return `<div class="panel tight">
      <div class="row" style="justify-content:space-between">
        <div><b style="font-size:15px">${esc(c.name)}</b>
          <span class="tag ${passed >= 8 ? 'ok' : passed >= 6 ? 'warn' : 'bad'}" style="margin-left:8px">${passed}/9 filtro</span>
          ${c.research.adLibraryCount != null ? `<span class="tag info" style="margin-left:4px">${c.research.adLibraryCount} ads activos</span>` : ''}
        </div>
        <button class="btn small danger" onclick="delCandidate('${c.id}')">Eliminar</button>
      </div>
      <div class="grid2" style="margin-top:8px">
        <div>
          <label>Keyword de investigación</label>
          <input value="${esc(c.keyword)}" onchange="setCand('${c.id}','keyword',this.value);render()">
          <div class="linkchips">${researchLinks(c.keyword).map(l => `<a href="${l.u}" target="_blank">${l.n} ↗</a>`).join('')}</div>
          <label>Ads activos en Meta Ad Library (cuéntalos y anótalo)</label>
          <input type="number" value="${c.research.adLibraryCount ?? ''}" placeholder="ej. 94" onchange="setCandR('${c.id}','adLibraryCount',this.value)">
          ${adInterp(c.research.adLibraryCount)}
          <label>Notas de investigación</label>
          <textarea onchange="setCand('${c.id}','notes',this.value)">${esc(c.notes)}</textarea>
        </div>
        <div>
          <label>Filtro de entrada (9 criterios del operador)</label>
          ${FILTER_CRITERIA.map(f => `<label class="check ${c.filter[f.k] ? 'done' : ''}" style="text-transform:none;letter-spacing:0;color:${c.filter[f.k] ? '' : 'var(--ink)'}">
            <input type="checkbox" ${c.filter[f.k] ? 'checked' : ''} onchange="toggleFilter('${c.id}','${f.k}')"> ${f.t}</label>`).join('')}
        </div>
      </div>
    </div>`;
  }).join('');
  return head('Fase 1 — Radar de productos', 'Agrega candidatos y valídalos contra el filtro de entrada. Los chips abren la investigación EN VIVO (Ad Library, Trends, TikTok, Alibaba) con tu keyword. Anota el conteo de ads activos: alimenta el score de competencia en la Fase 2.',
    aiBtn('Sugerir candidatos', 'aiRadar()')) + `
  <div class="row" style="margin-bottom:16px">
    <input id="candName" placeholder="Nombre del producto candidato…" style="max-width:300px">
    <input id="candKw" placeholder="keyword en inglés (ej. candle warmer lamp)" style="max-width:300px">
    <button class="btn" onclick="addCandidate()">+ Agregar candidato</button>
  </div>
  <div id="aiOut"></div>
  ${rows || '<div class="empty">Sin candidatos. Agrega al menos 5 para que el ranking tenga sentido.</div>'}`;
}
function adInterp(n) {
  const r = compScoreFromAds(n);
  return r ? `<div class="hint">→ Sugerencia de score de competencia: <b style="color:var(--accent)">${r.score}</b>. ${r.nota}</div>` : '';
}
function addCandidate() {
  const p = cur(); const name = $('candName').value.trim(); if (!name) return toast('Nombre requerido');
  p.candidates.push({ id: 'c' + Date.now().toString(36), name, keyword: $('candKw').value.trim() || name.toLowerCase(), notes: '', filter: {}, scores: { tend: 50, comp: 50, viral: 50, creat: 50, cpm: 50, ctr: 50, cpc: 50, conv: 50, aov: 50, ups: 50, cross: 50, marca: 50 }, research: { adLibraryCount: null } });
  persist(); render();
}
function delCandidate(id) { const p = cur(); p.candidates = p.candidates.filter(c => c.id !== id); if (p.winnerId === id) p.winnerId = null; persist(); render(); }
function setCand(id, field, v) { const c = cur().candidates.find(x => x.id === id); c[field] = v; persist(); }
function setCandR(id, field, v) { const c = cur().candidates.find(x => x.id === id); c.research[field] = v === '' ? null : +v; persist(); render(); }
function toggleFilter(id, k) { const c = cur().candidates.find(x => x.id === id); c.filter[k] = !c.filter[k]; persist(); render(); }

// ============================================================
// F2 · SCORING
// ============================================================
function vScoring() {
  const p = cur();
  const ranked = [...p.candidates].map(c => ({ ...c, total: scoreTotal(c.scores) })).sort((a, b) => b.total - a.total);
  const maxT = ranked[0]?.total || 100;
  const ranking = ranked.map((c, i) => `
    <tr><td>${i + 1}</td><td><b>${esc(c.name)}</b>${c.id === p.winnerId ? ' 🏆' : ''}</td>
      <td style="width:40%"><div class="rank-bar" style="width:${(c.total / maxT * 100).toFixed(0)}%"></div></td>
      <td class="num"><span class="score-pill ${scoreClass(c.total)}">${c.total.toFixed(1)}</span></td></tr>`).join('');
  const editors = p.candidates.map(c => {
    const sug = compScoreFromAds(c.research.adLibraryCount);
    return `<details class="panel tight" ${p.candidates.length === 1 ? 'open' : ''}>
    <summary style="cursor:pointer;font-weight:600;font-size:14px">${esc(c.name)} — <span style="color:var(--accent)">${scoreTotal(c.scores).toFixed(1)}</span></summary>
    <div style="margin-top:10px">
    ${Object.keys(WEIGHTS).map(k => `
      <div class="slider-row">
        <span class="nm"><span class="help" title="${esc(SCORE_GUIDES[k])}">${WEIGHTS[k].nombre}</span> <span style="color:var(--dim)">${(WEIGHTS[k].w * 100).toFixed(0)}%</span></span>
        <input type="range" min="0" max="100" value="${c.scores[k] || 0}" oninput="setScore('${c.id}','${k}',this.value,this)">
        <span class="val" id="sv_${c.id}_${k}">${c.scores[k] || 0}</span>
      </div>${k === 'comp' && sug ? `<div class="hint" style="margin-left:160px">Ad Library: ${c.research.adLibraryCount} ads → sugerido ${sug.score} <button class="btn small ghost" onclick="setScore('${c.id}','comp',${sug.score});render()">aplicar</button></div>` : ''}`).join('')}
    </div></details>`;
  }).join('');
  return head('Fase 2 — Scoring 0-100', 'Los pesos son los del operador (pasa el mouse sobre cada criterio para ver CÓMO puntuarlo). El score de competencia se sugiere automáticamente desde tu conteo real de Ad Library.', aiBtn('Puntuar con IA', 'aiScoring()')) + `
  <div id="aiOut"></div>
  <div class="panel"><h3 style="margin-top:0">Ranking</h3>
    <table>${ranking || '<tr><td class="empty">Agrega candidatos en el Radar.</td></tr>'}</table>
  </div>
  ${editors}`;
}
function setScore(id, k, v, el) {
  const c = cur().candidates.find(x => x.id === id); c.scores[k] = +v; persist();
  const sv = $(`sv_${id}_${k}`); if (sv) sv.textContent = v;
  if (!el) return; // aplicado por botón → el caller hace render
}

// ============================================================
// F3 · GANADOR & ECONOMÍA
// ============================================================
function vWinner() {
  const p = cur();
  const ranked = [...p.candidates].map(c => ({ ...c, total: scoreTotal(c.scores) })).sort((a, b) => b.total - a.total);
  const w = p.candidates.find(c => c.id === p.winnerId);
  const ec = economics(p.economics);
  const verdicts = econVerdict(ec).map(v => `<div class="rec ${v.c === 'ok' ? 'scale' : v.c === 'warn' ? 'iterate' : 'kill'}"><b>${v.t}</b></div>`).join('');
  return head('Fase 3 — Ganador & Economía', 'Selecciona UN solo ganador y valida su economía real. El break-even ROAS que calcules aquí gobierna las kill rules del Dashboard.', aiBtn('Validar decisión', 'aiWinner()')) + `
  <div id="aiOut"></div>
  <div class="grid2">
    <div class="panel">
      <h3 style="margin-top:0">🏆 Selección</h3>
      <label>Ganador</label>
      <select onchange="setFR('winnerId', this.value)">
        <option value="">— elegir —</option>
        ${ranked.map(c => `<option value="${c.id}" ${c.id === p.winnerId ? 'selected' : ''}>${esc(c.name)} (${c.total.toFixed(1)})</option>`).join('')}
      </select>
      ${ranked.length && p.winnerId && ranked[0].id !== p.winnerId ? `<div class="rec iterate" style="margin-top:10px"><b>⚠️ No elegiste al #1 del ranking</b><div class="why">El #1 es "${esc(ranked[0].name)}" (${ranked[0].total.toFixed(1)}). Si tienes una razón cualitativa, documenta cuál.</div></div>` : ''}
      <label>Descripción del producto ganador</label>
      <input value="${esc(p.producto)}" onchange="setF('producto', this.value)" placeholder="ej. Lámpara calentadora de velas con dimmer + timer">
      ${w ? `<div class="hint" style="margin-top:8px">Candidato #2 de respaldo (regla de los 30 días): <b>${esc(ranked.filter(c => c.id !== p.winnerId)[0]?.name || '—')}</b></div>` : ''}
    </div>
    <div class="panel">
      <h3 style="margin-top:0">💰 Economía unitaria</h3>
      <div class="grid3">
        <div><label>COGS + envío landed ($)</label><input type="number" step="0.01" value="${p.economics.cogs}" onchange="setFR('economics.cogs', this.value, true)"></div>
        <div><label>Envío extra ($)</label><input type="number" step="0.01" value="${p.economics.ship}" onchange="setFR('economics.ship', this.value, true)"></div>
        <div><label>Fees de pago (%)</label><input type="number" step="0.1" value="${p.economics.fees}" onchange="setFR('economics.fees', this.value, true)"></div>
        <div><label>Precio de venta ($)</label><input type="number" step="0.01" value="${p.economics.price}" onchange="setFR('economics.price', this.value, true)"></div>
        <div><label>Precio ancla ($)</label><input type="number" step="0.01" value="${p.economics.anchor}" onchange="setFR('economics.anchor', this.value, true)"></div>
        <div><label>AOV objetivo ($)</label><input type="number" step="0.01" value="${p.economics.aovTarget}" onchange="setFR('economics.aovTarget', this.value, true)"></div>
      </div>
    </div>
  </div>
  <div class="kpis">
    <div class="kpi"><div class="l">Utilidad bruta/unidad</div><div class="v">${money(ec.profit)}</div><div class="s">antes de ads</div></div>
    <div class="kpi ${ec.marginPct >= .7 ? 'good' : ec.marginPct >= .55 ? 'warn' : 'bad'}"><div class="l">Margen</div><div class="v">${ec.price ? (ec.marginPct * 100).toFixed(0) + '%' : '—'}</div><div class="s">objetivo ≥70%</div></div>
    <div class="kpi ${ec.beRoas <= 1.6 ? 'good' : ec.beRoas <= 2.3 ? 'warn' : 'bad'}"><div class="l">Break-even ROAS</div><div class="v">${isFinite(ec.beRoas) ? ec.beRoas.toFixed(2) : '—'}</div><div class="s">gobierna las kill rules</div></div>
    <div class="kpi"><div class="l">ROAS objetivo</div><div class="v">${ec.price ? ec.targetRoas.toFixed(2) : '—'}</div><div class="s">para escalar</div></div>
    <div class="kpi"><div class="l">CPA máximo (BE)</div><div class="v">${money(ec.cpaBE)}</div><div class="s">gasto/compra tope</div></div>
    <div class="kpi"><div class="l">Utilidad en objetivo</div><div class="v">${ec.price ? money(ec.utilTarget) : '—'}</div><div class="s">por unidad, ads pagados</div></div>
  </div>
  ${verdicts}`;
}

// ============================================================
// F4 · COMPETENCIA
// ============================================================
function vComp() {
  const p = cur();
  const rows = p.competitors.map((c, i) => `<tr>
    <td><input value="${esc(c.name)}" onchange="setComp(${i},'name',this.value)"></td>
    <td><input value="${esc(c.tier)}" onchange="setComp(${i},'tier',this.value)" style="width:90px"></td>
    <td><input value="${esc(c.price)}" onchange="setComp(${i},'price',this.value)" style="width:70px"></td>
    <td><input value="${esc(c.offer)}" onchange="setComp(${i},'offer',this.value)"></td>
    <td><input value="${esc(c.garantia)}" onchange="setComp(${i},'garantia',this.value)" style="width:90px"></td>
    <td><input value="${esc(c.hooks)}" onchange="setComp(${i},'hooks',this.value)"></td>
    <td><input value="${esc(c.fortalezas)}" onchange="setComp(${i},'fortalezas',this.value)"></td>
    <td><input value="${esc(c.debilidades)}" onchange="setComp(${i},'debilidades',this.value)"></td>
    <td><button class="btn small danger" onclick="delComp(${i})">✕</button></td></tr>`).join('');
  const w = p.candidates.find(c => c.id === p.winnerId);
  const opps = p.oportunidades.map((o, i) => `
    <label class="check ${o.done ? 'done' : ''}"><input type="checkbox" ${o.done ? 'checked' : ''} onchange="toggleOpp(${i})">
    <span>${esc(o.text)}${o.nota ? ` <span style="color:var(--dim)">· ${esc(o.nota)}</span>` : ''}</span></label>`).join('');
  return head('Fase 4 — Análisis de competencia', 'Mapea quién vende, a cuánto y con qué ángulos. Después marca las oportunidades que NADIE explota: ahí vive tu moat. Usa los links del Radar para investigar en vivo.', aiBtn('Analizar competencia', 'aiComp()')) + `
  <div id="aiOut"></div>
  ${w ? `<div class="linkchips" style="margin-bottom:14px">${researchLinks(w.keyword).slice(0, 5).map(l => `<a href="${l.u}" target="_blank">${l.n} ↗</a>`).join('')}</div>` : ''}
  <div class="panel"><h3 style="margin-top:0">Mapa competitivo</h3>
    <div class="scrollx"><table>
      <tr><th>Competidor</th><th>Tier</th><th>Precio $</th><th>Oferta</th><th>Garantía</th><th>Hooks que usan</th><th>Fortalezas</th><th>Debilidades</th><th></th></tr>
      ${rows || ''}</table></div>
    <button class="btn small ghost" style="margin-top:10px" onclick="addComp()">+ Competidor</button>
  </div>
  <div class="panel"><h3 style="margin-top:0">Oportunidades no explotadas (marca las que vas a atacar)</h3>${opps}
    <div class="row" style="margin-top:8px"><input id="newOpp" placeholder="Otra oportunidad detectada…" style="max-width:420px"><button class="btn small" onclick="addOpp()">+ Agregar</button></div>
  </div>`;
}
function addComp() { cur().competitors.push({ name: '', tier: '', price: '', offer: '', garantia: '', hooks: '', publico: '', fortalezas: '', debilidades: '' }); persist(); render(); }
function delComp(i) { cur().competitors.splice(i, 1); persist(); render(); }
function setComp(i, f, v) { cur().competitors[i][f] = v; persist(); }
function toggleOpp(i) { const o = cur().oportunidades[i]; o.done = !o.done; persist(); render(); }
function addOpp() { const v = $('newOpp').value.trim(); if (!v) return; cur().oportunidades.push({ text: v, done: false, nota: '' }); persist(); render(); }

// ============================================================
// F5 · MARCA
// ============================================================
function vBrand() {
  const p = cur(); const b = p.brand;
  const colorField = (k, label) => `<div><label>${label}</label><div class="row"><input type="color" value="${b.colors[k]}" style="max-width:52px" onchange="setFR('brand.colors.${k}', this.value)"><input value="${b.colors[k]}" style="max-width:90px" onchange="setFR('brand.colors.${k}', this.value)"></div></div>`;
  return head('Fase 5 — Marca', 'Nombre, identidad visual y voz. Verifica el dominio ANTES de enamorarte del nombre. Estos tokens alimentan el generador de landing (F10) y los prompts de IA (F9).', aiBtn('Generar identidad', 'aiBrand()')) + `
  <div id="aiOut"></div>
  <div class="grid2">
    <div class="panel">
      <h3 style="margin-top:0">Identidad</h3>
      <label>Nombre de marca</label><input value="${esc(b.name)}" onchange="setF('brand.name', this.value)">
      <label>Dominio</label>
      <div class="row"><input value="${esc(b.domain)}" onchange="setF('brand.domain', this.value)" placeholder="mimarca.com" style="max-width:240px">
        <a class="btn small ghost" style="text-decoration:none" href="https://vercel.com/domains" target="_blank">Verificar disponibilidad ↗</a></div>
      <label>Eslogan principal</label><input value="${esc(b.slogan)}" onchange="setF('brand.slogan', this.value)">
      <label>Eslogan secundario (gifting/Q4)</label><input value="${esc(b.sloganAlt)}" onchange="setF('brand.sloganAlt', this.value)">
      <label>Concepto de logo</label><textarea onchange="setF('brand.logo', this.value)">${esc(b.logo)}</textarea>
      <label>Packaging</label><textarea onchange="setF('brand.packaging', this.value)">${esc(b.packaging)}</textarea>
    </div>
    <div class="panel">
      <h3 style="margin-top:0">Sistema visual</h3>
      <div class="grid3">
        ${colorField('primary', 'Primario')}${colorField('dark', 'Oscuro')}${colorField('light', 'Claro')}
        ${colorField('accent', 'Acento')}${colorField('cta', 'CTA')}
      </div>
      <div style="margin-top:14px;border-radius:12px;overflow:hidden;border:1px solid var(--line)">
        <div style="background:${b.colors.dark};padding:22px;text-align:center">
          <div style="font-family:'${b.fontDisplay}',serif;font-size:26px;letter-spacing:.08em;color:${b.colors.light}">${esc(b.name || 'TU MARCA')}</div>
          <div style="color:${b.colors.primary};font-size:13px;margin-top:4px">${esc(b.slogan || 'Tu eslogan aquí')}</div>
          <button class="btn" style="background:${b.colors.cta};margin-top:12px;pointer-events:none">Add to Cart</button>
        </div>
        <div style="background:${b.colors.light};padding:10px;text-align:center;color:${b.colors.dark};font-size:12px">Sección clara · texto ${b.colors.dark}</div>
      </div>
      <div class="grid2" style="margin-top:8px">
        <div><label>Tipografía display</label><input value="${esc(b.fontDisplay)}" onchange="setFR('brand.fontDisplay', this.value)"></div>
        <div><label>Tipografía cuerpo</label><input value="${esc(b.fontBody)}" onchange="setF('brand.fontBody', this.value)"></div>
      </div>
      <label>Voz de marca (personalidad, de qué hablamos)</label><textarea onchange="setF('brand.voz', this.value)">${esc(b.voz)}</textarea>
      <label>Lo que NUNCA decimos</label><textarea onchange="setF('brand.nunca', this.value)">${esc(b.nunca)}</textarea>
    </div>
  </div>`;
}

// ============================================================
// F6 · AVATAR
// ============================================================
function listEditor(title, path, arr, placeholder) {
  const items = arr.map((x, i) => `<div class="icard">${esc(x)}<button class="del" onclick="delListItem('${path}',${i})">✕</button></div>`).join('');
  return `<div class="panel"><h3 style="margin-top:0">${title}</h3><div class="card-list">${items || '<div class="empty">Vacío</div>'}</div>
  <div class="row" style="margin-top:10px"><input id="in_${path.replace(/\./g, '_')}" placeholder="${placeholder}" style="max-width:480px"><button class="btn small" onclick="addListItem('${path}')">+ Agregar</button></div></div>`;
}
function addListItem(path) {
  const el = $('in_' + path.replace(/\./g, '_')); const v = el.value.trim(); if (!v) return;
  const keys = path.split('.'); let o = cur(); for (let i = 0; i < keys.length - 1; i++) o = o[keys[i]];
  o[keys[keys.length - 1]].push(v); persist(); render();
}
function delListItem(path, i) {
  const keys = path.split('.'); let o = cur(); for (let k = 0; k < keys.length - 1; k++) o = o[keys[k]];
  o[keys[keys.length - 1]].splice(i, 1); persist(); render();
}
function vAvatar() {
  const p = cur(); const a = p.avatar;
  const objs = a.objeciones.map((o, i) => `<div class="icard"><b>${esc(o.o)}</b><div style="color:var(--muted);margin-top:3px">↳ ${esc(o.r)}</div><button class="del" onclick="delObj(${i})">✕</button></div>`).join('');
  return head('Fase 6 — Estrategia & Avatar', 'El avatar es la persona; los dolores y deseos son los ángulos; las objeciones se convierten en FAQs de la landing; la transformación es el hero.', aiBtn('Construir estrategia', 'aiAvatar()')) + `
  <div id="aiOut"></div>
  <div class="panel">
    <div class="grid2">
      <div><label>Nombre del avatar</label><input value="${esc(a.nombre)}" onchange="setF('avatar.nombre', this.value)" placeholder='ej. "Maya"'></div>
      <div><label>Demografía + contexto</label><input value="${esc(a.demo)}" onchange="setF('avatar.demo', this.value)"></div>
    </div>
    <div class="grid2" style="margin-top:6px">
      <div><label>Transformación — DE:</label><textarea onchange="setF('avatar.transDe', this.value)">${esc(a.transDe)}</textarea></div>
      <div><label>Transformación — A:</label><textarea onchange="setF('avatar.transA', this.value)">${esc(a.transA)}</textarea></div>
    </div>
    <label>Storytelling maestro (base de todos los creativos)</label><textarea style="min-height:90px" onchange="setF('avatar.story', this.value)">${esc(a.story)}</textarea>
  </div>
  <div class="grid2">
    ${listEditor('😖 Dolores', 'avatar.dolores', a.dolores, 'Nuevo dolor…')}
    ${listEditor('✨ Deseos', 'avatar.deseos', a.deseos, 'Nuevo deseo…')}
  </div>
  <div class="grid2">
    ${listEditor('💎 Beneficios (jerarquía)', 'avatar.beneficios', a.beneficios, 'Nuevo beneficio…')}
    ${listEditor('📚 Pilares de contenido', 'avatar.pilares', a.pilares, 'Pilar + % del mix…')}
  </div>
  <div class="panel"><h3 style="margin-top:0">🛡️ Objeciones → Respuestas (se vuelven tus FAQs)</h3>
    <div class="card-list">${objs || '<div class="empty">Vacío</div>'}</div>
    <div class="grid2" style="margin-top:10px">
      <input id="objO" placeholder="Objeción…"><input id="objR" placeholder="Respuesta en copy…">
    </div>
    <button class="btn small" style="margin-top:8px" onclick="addObj()">+ Agregar objeción</button>
  </div>`;
}
function addObj() { const o = $('objO').value.trim(), r = $('objR').value.trim(); if (!o) return; cur().avatar.objeciones.push({ o, r }); persist(); render(); }
function delObj(i) { cur().avatar.objeciones.splice(i, 1); persist(); render(); }

// ============================================================
// F7 · HOOKS
// ============================================================
function vHooks() {
  const p = cur();
  const byCat = {};
  p.hooks.forEach(h => { (byCat[h.cat] = byCat[h.cat] || []).push(h); });
  const list = Object.entries(byCat).map(([cat, hs]) => `
    <div class="panel tight"><h3 style="margin-top:2px">${esc(cat)} <span class="tag dim">${hs.length}</span></h3>
    ${hs.map(h => `<div class="icard"><span class="fav ${h.fav ? 'on' : ''}" onclick="togHookFav('${h.id}')">⭐</span> ${esc(h.text)}
      <button class="del" onclick="delHook('${h.id}')">✕</button></div>`).join('')}</div>`).join('');
  const tpls = HOOK_ANGLES.map(a => `<details style="margin-bottom:8px"><summary style="cursor:pointer;font-size:13px;font-weight:600">${a.k}</summary>
    ${a.tpl.map(t => `<div class="icard" style="margin-top:6px">${esc(t)} <button class="btn small ghost" style="margin-left:8px" onclick="useTpl('${a.k}', this)">usar</button></div>`).join('')}</details>`).join('');
  return head('Fase 7 — Hooks', `${p.hooks.length} hooks (objetivo: 100). ⭐ = va al batch de lanzamiento. Los primeros 3 segundos son el 80% del resultado del ad.`, aiBtn('Generar 30 hooks', 'aiHooks()')) + `
  <div id="aiOut"></div>
  <div class="grid2">
    <div>
      <div class="panel tight">
        <div class="row"><select id="hookCat" style="max-width:190px">${HOOK_ANGLES.map(a => `<option>${a.k}</option>`).join('')}</select>
        <input id="hookText" placeholder="Escribe el hook (en el idioma de tus ads)…"><button class="btn" onclick="addHook()">+ </button></div>
      </div>
      ${list || '<div class="empty">Sin hooks aún. Genera con IA o usa las plantillas →</div>'}
    </div>
    <div class="panel"><h3 style="margin-top:0">Plantillas del operador (rellena las {variables})</h3>${tpls}</div>
  </div>`;
}
function addHook(txt, cat) {
  const p = cur();
  const text = txt || $('hookText').value.trim(); if (!text) return;
  p.hooks.push({ id: 'h' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5), cat: cat || $('hookCat').value, text, fav: false });
  persist(); render();
}
function useTpl(cat, btn) { $('hookCat').value = cat; $('hookText').value = btn.parentElement.textContent.replace('usar', '').trim(); $('hookText').focus(); }
function delHook(id) { const p = cur(); p.hooks = p.hooks.filter(h => h.id !== id); persist(); render(); }
function togHookFav(id) { const h = cur().hooks.find(x => x.id === id); h.fav = !h.fav; persist(); render(); }

// ============================================================
// F8 · CONCEPTOS & GUIONES
// ============================================================
function vScripts() {
  const p = cur();
  const counts = CONCEPT_FORMATS.map(f => {
    const n = p.concepts.filter(c => c.formato === f.k).length;
    return `<div class="kpi ${n >= f.meta ? 'good' : ''}"><div class="l">${f.k}</div><div class="v">${n}<span style="font-size:13px;color:var(--dim)">/${f.meta}</span></div></div>`;
  }).join('');
  const concepts = p.concepts.map(c => `<div class="icard"><span class="tag dim">${esc(c.formato)}</span> ${esc(c.text)}
    <button class="btn small ghost" style="margin-left:6px" onclick="conceptToScript('${c.id}')">→ guion</button>
    <button class="del" onclick="delConcept('${c.id}')">✕</button></div>`).join('');
  const scripts = p.scripts.map(s => `<details class="panel tight"><summary style="cursor:pointer;font-weight:600">${esc(s.titulo)} <span class="tag dim">${esc(s.formato)} · ${esc(s.dur)}</span> <span class="tag ${s.estado === 'listo' ? 'ok' : 'warn'}">${esc(s.estado)}</span></summary>
    <div class="grid2" style="margin-top:10px">
      <div><label>Título</label><input value="${esc(s.titulo)}" onchange="setScript('${s.id}','titulo',this.value)">
      <div class="grid2"><div><label>Formato</label><select onchange="setScript('${s.id}','formato',this.value)">${CONCEPT_FORMATS.map(f => `<option ${s.formato === f.k ? 'selected' : ''}>${f.k}</option>`).join('')}</select></div>
      <div><label>Duración</label><input value="${esc(s.dur)}" onchange="setScript('${s.id}','dur',this.value)"></div></div>
      <label>Hook (0-3s) — ${SCRIPT_TEMPLATE.hook}</label><textarea onchange="setScript('${s.id}','hook',this.value)">${esc(s.hook)}</textarea>
      <label>Desarrollo — ${SCRIPT_TEMPLATE.desarrollo}</label><textarea onchange="setScript('${s.id}','desarrollo',this.value)">${esc(s.desarrollo)}</textarea></div>
      <div><label>Prueba (opcional)</label><textarea onchange="setScript('${s.id}','prueba',this.value)">${esc(s.prueba)}</textarea>
      <label>CTA — ${SCRIPT_TEMPLATE.cta}</label><textarea onchange="setScript('${s.id}','cta',this.value)">${esc(s.cta)}</textarea>
      <label>Texto en pantalla</label><textarea onchange="setScript('${s.id}','texto',this.value)">${esc(s.texto)}</textarea>
      <label>Música</label><input value="${esc(s.musica)}" onchange="setScript('${s.id}','musica',this.value)">
      <label>Estado</label><select onchange="setScript('${s.id}','estado',this.value)"><option ${s.estado === 'borrador' ? 'selected' : ''}>borrador</option><option ${s.estado === 'listo' ? 'selected' : ''}>listo</option><option ${s.estado === 'grabado' ? 'selected' : ''}>grabado</option><option ${s.estado === 'publicado' ? 'selected' : ''}>publicado</option></select>
      <button class="btn small danger" style="margin-top:10px" onclick="delScript('${s.id}')">Eliminar guion</button></div>
    </div></details>`).join('');
  return head('Fase 8 — Conceptos & Guiones', 'Metodología: banco de conceptos por formato → conviertes en guiones completos SOLO los del batch de lanzamiento (12-24). El dashboard te dirá qué formato gana; produce los siguientes lotes solo de ese formato.', aiBtn('Generar conceptos', 'aiConcepts()')) + `
  <div id="aiOut"></div>
  <div class="kpis">${counts}</div>
  <div class="grid2">
    <div class="panel"><h3 style="margin-top:0">Banco de conceptos</h3>
      <div class="row"><select id="conFmt" style="max-width:160px">${CONCEPT_FORMATS.map(f => `<option>${f.k}</option>`).join('')}</select>
      <input id="conText" placeholder="Idea de video en una línea…"><button class="btn" onclick="addConcept()">+</button></div>
      <div class="card-list" style="margin-top:12px">${concepts || '<div class="empty">Vacío</div>'}</div>
    </div>
    <div><h3 style="margin-top:0">Guiones completos (${p.scripts.length})</h3>${scripts || '<div class="empty">Convierte un concepto en guion con "→ guion".</div>'}</div>
  </div>`;
}
function addConcept() { const t = $('conText').value.trim(); if (!t) return; cur().concepts.push({ id: 'k' + Date.now().toString(36), formato: $('conFmt').value, text: t }); persist(); render(); }
function delConcept(id) { const p = cur(); p.concepts = p.concepts.filter(c => c.id !== id); persist(); render(); }
function conceptToScript(id) {
  const p = cur(); const c = p.concepts.find(x => x.id === id);
  p.scripts.push({ id: 's' + Date.now().toString(36), titulo: c.text.slice(0, 60), formato: c.formato, dur: c.formato === 'Demo' ? '10-15s' : c.formato === 'POV' ? '15-20s' : '25-40s', hook: '', desarrollo: c.text, prueba: '', cta: '', texto: '', musica: '', estado: 'borrador' });
  persist(); render(); toast('Guion creado — complétalo con la plantilla maestra');
}
function setScript(id, f, v) { const s = cur().scripts.find(x => x.id === id); s[f] = v; persist(); }
function delScript(id) { const p = cur(); p.scripts = p.scripts.filter(s => s.id !== id); persist(); render(); }

// ============================================================
// F9 · PROMPTS IA
// ============================================================
function vPrompts() {
  const p = cur(); const b = p.brand;
  const vars = { producto: p.producto || '[producto]', color_primario: b.colors.primary, color_oscuro: b.colors.dark, color_claro: b.colors.light, avatar: p.avatar.nombre || '[avatar]' };
  const cards = AI_PROMPT_TEMPLATES.map((t, i) => {
    let filled = t.tpl;
    for (const k in vars) filled = filled.replaceAll(`{${k}}`, vars[k]);
    return `<div class="panel tight"><b>${t.k}</b> <span class="tag dim">${t.tool}</span>
      <div class="pre" style="margin-top:8px">${esc(filled)}<button class="copybtn" onclick="copyText(this)">copiar</button></div>
      <div class="hint">Las {variables} restantes se rellenan con tu producto específico.</div></div>`;
  }).join('');
  return head('Fase 9 — Prompts de IA', 'Plantillas de producción con tus tokens de marca ya inyectados (colores, producto, avatar). Regla de oro: la IA genera ambiente y b-roll; los primeros planos REALES del producto se intercalan para credibilidad.', aiBtn('Prompts a medida', 'aiPrompts()')) + `
  <div id="aiOut"></div>
  <div class="rec info"><b>Pipeline recomendado</b><div class="why">1) Genera 12 clips b-roll + 6 imágenes base → banco de assets. 2) Graba 10 clips reales con la muestra física. 3) Edita en CapCut con subtítulos auto. 4) VO en ElevenLabs a -6dB bajo la música. 5) Exporta 9:16 1080×1920.</div></div>
  ${cards}`;
}
function copyText(btn) { navigator.clipboard.writeText(btn.parentElement.textContent.replace('copiar', '').trim()); toast('Copiado'); }

// ============================================================
// F10 · LANDING
// ============================================================
function vLanding() {
  const p = cur();
  const done = LANDING_CHECKLIST.filter(c => p.checks.landing[c.k]).length;
  const items = LANDING_CHECKLIST.map(c => `<label class="check ${p.checks.landing[c.k] ? 'done' : ''}"><input type="checkbox" ${p.checks.landing[c.k] ? 'checked' : ''} onchange="togCheck('landing','${c.k}')"> ${c.t}</label>`).join('');
  return head('Fase 10 — Landing', 'Genera el esqueleto HTML premium con tus tokens de marca (colores, precio, beneficios del avatar como cards, objeciones como FAQs) y complétalo con assets reales. El checklist es el estándar CRO del operador.', aiBtn('Copy de landing', 'aiLanding()')) + `
  <div id="aiOut"></div>
  <div class="grid2">
    <div class="panel">
      <h3 style="margin-top:0">Generador</h3>
      <p style="color:var(--muted);font-size:13px">Usa: marca "${esc(p.brand.name) || '—'}", precio ${money(p.economics.price)}, ancla ${money(p.economics.anchor)}, ${p.avatar.beneficios.length} beneficios, ${p.avatar.objeciones.length} FAQs.</p>
      <div class="row" style="margin-top:12px">
        <button class="btn" onclick="downloadLanding()">⬇ Descargar landing.html</button>
        <button class="btn ghost" onclick="previewLanding()">Ver preview</button>
      </div>
      <div class="hint" style="margin-top:8px">Para Shopify: pega las secciones en una página con editor de código, o úsala como referencia visual para armar el tema.</div>
    </div>
    <div class="panel">
      <h3 style="margin-top:0">Checklist CRO (${done}/${LANDING_CHECKLIST.length})</h3>
      <div class="progressbar"><i style="width:${done / LANDING_CHECKLIST.length * 100}%"></i></div>
      ${items}
    </div>
  </div>`;
}
function togCheck(group, k) { const c = cur().checks[group]; c[k] = !c[k]; persist(); render(); }
function downloadLanding() {
  const html = landingTemplate(cur());
  const blob = new Blob([html], { type: 'text/html' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `landing-${(cur().brand.name || 'marca').toLowerCase()}.html`; a.click();
}
function previewLanding() {
  const w = window.open('', '_blank'); w.document.write(landingTemplate(cur())); w.document.close();
}

// ============================================================
// F11 · TIENDA
// ============================================================
function vStore() {
  const p = cur();
  const done = STORE_CHECKLIST.filter(c => p.checks.tienda[c.k]).length;
  const items = STORE_CHECKLIST.map(c => `<label class="check ${p.checks.tienda[c.k] ? 'done' : ''}"><input type="checkbox" ${p.checks.tienda[c.k] ? 'checked' : ''} onchange="togCheck('tienda','${c.k}')"> ${c.t}</label>`).join('');
  return head('Fase 11 — Tienda Shopify', 'El checklist completo de conversión del operador: PDP, checkout, urgencia honesta, email flows y operación. Nada de esto es opcional si vas a pagar tráfico.') + `
  <div class="kpis">
    <div class="kpi ${done === STORE_CHECKLIST.length ? 'good' : ''}"><div class="l">Progreso</div><div class="v">${done}/${STORE_CHECKLIST.length}</div></div>
    <div class="kpi ${p.checks.tienda.muestra ? 'good' : 'bad'}"><div class="l">Muestra física</div><div class="v">${p.checks.tienda.muestra ? '✓' : '✗'}</div><div class="s">bloqueante para ads</div></div>
    <div class="kpi ${p.checks.tienda.pixels ? 'good' : 'bad'}"><div class="l">Pixels + CAPI</div><div class="v">${p.checks.tienda.pixels ? '✓' : '✗'}</div><div class="s">bloqueante para ads</div></div>
  </div>
  <div class="panel"><div class="progressbar"><i style="width:${done / STORE_CHECKLIST.length * 100}%"></i></div>${items}</div>`;
}

// ============================================================
// F12 · LANZAMIENTO
// ============================================================
function vLaunch() {
  const p = cur(); const ec = economics(p.economics);
  const be = isFinite(ec.beRoas) ? ec.beRoas : null;
  const daily = (p.launch.budget / p.launch.days).toFixed(0);
  const weeks = LAUNCH_PLAN.semanas.map(s => `<div class="panel tight"><h3 style="margin-top:2px">${s.t}</h3>${s.items.map(i => `<div class="check" style="cursor:default">· ${i}</div>`).join('')}</div>`).join('');
  const hitos = LAUNCH_PLAN.hitos30.map(h => `<div class="rec ${h.accion.startsWith('ESCALAR') ? 'scale' : h.accion.startsWith('MATAR') ? 'kill' : 'iterate'}"><b>${h.cond}</b><div class="why">${h.accion}</div></div>`).join('');
  return head('Fase 12 — Lanzamiento', 'Presupuesto, estructura de campañas y las kill rules calculadas con TU economía real (no números genéricos).') + `
  <div class="grid3">
    <div class="panel tight"><label>Presupuesto total de validación ($)</label><input type="number" value="${p.launch.budget}" onchange="setFR('launch.budget', this.value, true)"></div>
    <div class="panel tight"><label>Días de test</label><input type="number" value="${p.launch.days}" onchange="setFR('launch.days', this.value, true)"></div>
    <div class="panel tight"><label>% Meta (resto TikTok)</label><input type="number" value="${p.launch.metaPct}" onchange="setFR('launch.metaPct', this.value, true)"></div>
  </div>
  <div class="kpis">
    <div class="kpi"><div class="l">Gasto diario</div><div class="v">$${daily}</div></div>
    <div class="kpi"><div class="l">Meta / TikTok</div><div class="v">$${(daily * p.launch.metaPct / 100).toFixed(0)} / $${(daily * (100 - p.launch.metaPct) / 100).toFixed(0)}</div></div>
    <div class="kpi ${be ? (be <= 1.6 ? 'good' : be <= 2.3 ? 'warn' : 'bad') : ''}"><div class="l">Tu break-even ROAS</div><div class="v">${be ? be.toFixed(2) : '—'}</div><div class="s">de la Fase 3</div></div>
    <div class="kpi"><div class="l">ROAS de escalado</div><div class="v">${be ? Math.max(2, be * 1.3).toFixed(2) : '—'}</div></div>
    <div class="kpi"><div class="l">CPA máximo</div><div class="v">${money(ec.cpaBE)}</div><div class="s">arriba de esto pierdes</div></div>
  </div>
  <div class="panel"><h3 style="margin-top:0">Estructura de testing (ABO)</h3>
    <div class="pre">Campaña TEST-1 (ABO) · Optimización: PURCHASE desde el día 1
├── AdSet 1 — Broad ${p.avatar.demo ? '(' + esc(p.avatar.demo.split(',')[0]) + ')' : ''} · $10-15/día · 3 ads
├── AdSet 2 — Broad total (sin género/edad) · $10-15/día · 3 ads
├── AdSet 3 — Interés principal del nicho · $10-15/día · 3 ads
└── AdSet 4 — Advantage+ audience · $10-15/día · 3 ads (rotación)
TikTok: 1 campaña · 2 ad groups broad · $15/día · mejores 6 verticales<button class="copybtn" onclick="copyText(this)">copiar</button></div>
    <h3>Kill rules (con tu economía)</h3>
    <div class="rec kill"><b>Matar ad</b><div class="why">Gasto ≥ ${money(ec.price ? Math.max(ec.price, 50) : 70)} (≈1× AOV) sin compra · o CTR &lt;0.8% tras $20 · o CPC &gt;$2.50 tras $20</div></div>
    <div class="rec iterate"><b>Iterar (solo el hook)</b><div class="why">ROAS entre ${be ? (be * 0.7).toFixed(2) : '1.0'} y ${be ? be.toFixed(2) : 'break-even'} con compras: 2 días más, cambia solo los primeros 3 segundos</div></div>
    <div class="rec scale"><b>Escalar</b><div class="why">ROAS ≥ ${be ? Math.max(2, be * 1.3).toFixed(2) : '2.0'} con 3+ compras: duplicar a 2×, +20-30% cada 48h, variantes del mismo formato</div></div>
    <h3>Roadmap</h3>${weeks}
    <h3>Decisión a los ${p.launch.days} días</h3>${hitos}
  </div>`;
}

// ============================================================
// F13 · DASHBOARD
// ============================================================
function vDash() {
  const p = cur(); const ec = economics(p.economics);
  const g = aggMetrics(p.metrics);
  const be = isFinite(ec.beRoas) ? ec.beRoas : 1.5;
  const ads = {};
  p.metrics.forEach(r => { (ads[r.ad] = ads[r.ad] || []).push(r); });
  const adRows = Object.entries(ads).map(([name, rows]) => ({ name, platform: rows[rows.length - 1].platform, ...aggMetrics(rows) })).sort((a, b) => b.spend - a.spend);
  const recs = buildRecs(g, adRows, ec, p.metrics.length > 0);
  const roasClass = !isFinite(g.roas) ? '' : (g.roas >= be * 1.25 ? 'good' : g.roas >= be ? 'warn' : 'bad');
  const kpis = [
    ['Gasto', money(g.spend), ''], ['Ingresos', money(g.rev), ''],
    ['ROAS blended', isFinite(g.roas) ? g.roas.toFixed(2) : '—', roasClass],
    ['Break-even', be.toFixed(2), ''],
    ['CTR', pct(g.ctr), isFinite(g.ctr) ? (g.ctr >= .015 ? 'good' : g.ctr >= .008 ? 'warn' : 'bad') : ''],
    ['CPC', isFinite(g.cpc) ? money(g.cpc) : '—', isFinite(g.cpc) && g.cpc > 2.5 ? 'bad' : ''],
    ['Conversión', pct(g.cr), isFinite(g.cr) ? (g.cr >= .02 ? 'good' : g.cr >= .012 ? 'warn' : 'bad') : ''],
    ['CPA', isFinite(g.cpa) ? money(g.cpa) : '—', isFinite(g.cpa) && ec.profit && g.cpa > ec.profit ? 'bad' : ''],
    ['AOV', isFinite(g.aov) ? money(g.aov) : '—', ''], ['Compras', g.purch, ''],
  ].map(([l, v, c]) => `<div class="kpi ${c}"><div class="l">${l}</div><div class="v">${v}</div></div>`).join('');
  const table = adRows.map(a => {
    const st = adStatus(a, be, ec.price ? Math.max(ec.price, 50) : 70);
    return `<tr><td>${esc(a.name)}</td><td>${esc(a.platform)}</td><td class="num">${money(a.spend)}</td><td class="num">${pct(a.ctr)}</td>
    <td class="num">${isFinite(a.cpc) ? money(a.cpc) : '—'}</td><td class="num">${a.purch}</td><td class="num">${isFinite(a.roas) ? a.roas.toFixed(2) : '—'}</td>
    <td><span class="tag ${st.c}">${st.t}</span></td></tr>`;
  }).join('');
  const log = [...p.metrics].reverse().slice(0, 60).map((r, idx) => {
    const i = p.metrics.length - 1 - idx;
    return `<tr><td>${r.date}</td><td>${esc(r.ad)}</td><td class="num">${money(r.spend)}</td><td class="num">${r.impr}</td><td class="num">${r.clicks}</td><td class="num">${r.atc}</td><td class="num">${r.purch}</td><td class="num">${money(r.rev)}</td><td><button class="btn small danger" onclick="delMetric(${i})">✕</button></td></tr>`;
  }).join('');
  return head('Fase 13 — Dashboard del operador', `Las recomendaciones usan TU break-even real (${be.toFixed(2)}) de la Fase 3, no umbrales genéricos. Registra cada día por anuncio.`, aiBtn('Analizar métricas', 'aiDash()')) + `
  <div id="aiOut"></div>
  <div class="kpis">${kpis}</div>
  <div class="grid2" style="grid-template-columns:1.15fr .85fr">
    <div>
      <div class="panel"><h3 style="margin-top:0">📥 Registrar día / anuncio</h3>
        <div class="grid3">
          <div><label>Fecha</label><input type="date" id="m_date"></div>
          <div><label>Plataforma</label><select id="m_platform"><option>Meta</option><option>TikTok</option><option>Otro</option></select></div>
          <div><label>Anuncio / Ad set</label><input id="m_ad" placeholder="UGC-1"></div>
          <div><label>Gasto ($)</label><input type="number" step="0.01" id="m_spend"></div>
          <div><label>Impresiones</label><input type="number" id="m_impr"></div>
          <div><label>Clicks</label><input type="number" id="m_clicks"></div>
          <div><label>Add to Cart</label><input type="number" id="m_atc" value="0"></div>
          <div><label>Compras</label><input type="number" id="m_purch"></div>
          <div><label>Ingresos ($)</label><input type="number" step="0.01" id="m_rev"></div>
        </div>
        <button class="btn" style="margin-top:12px" onclick="addMetric()">Guardar registro</button>
      </div>
      <div class="panel"><h3 style="margin-top:0">Rendimiento por anuncio</h3>
        <div class="scrollx"><table><tr><th>Anuncio</th><th>Plat.</th><th>Gasto</th><th>CTR</th><th>CPC</th><th>Compras</th><th>ROAS</th><th>Estado</th></tr>${table || '<tr><td colspan="8" class="empty">Sin datos.</td></tr>'}</table></div>
      </div>
      <div class="panel"><h3 style="margin-top:0">Registros</h3>
        <div class="scrollx"><table><tr><th>Fecha</th><th>Anuncio</th><th>Gasto</th><th>Impr</th><th>Clicks</th><th>ATC</th><th>Compras</th><th>Ingresos</th><th></th></tr>${log || '<tr><td colspan="9" class="empty">Vacío.</td></tr>'}</table></div>
      </div>
    </div>
    <div class="panel"><h3 style="margin-top:0">🧠 Recomendaciones</h3>
      ${recs.map(r => `<div class="rec ${r.type}"><b>${r.t}</b><div class="why">${r.why}</div>${r.act ? `<div style="margin-top:5px">${r.act}</div>` : ''}</div>`).join('') || '<div class="empty">Todo en rango.</div>'}
    </div>
  </div>`;
}
function addMetric() {
  const p = cur();
  const row = { date: $('m_date').value || new Date().toISOString().slice(0, 10), platform: $('m_platform').value, ad: $('m_ad').value.trim() || 'sin-nombre', spend: +$('m_spend').value || 0, impr: +$('m_impr').value || 0, clicks: +$('m_clicks').value || 0, atc: +$('m_atc').value || 0, purch: +$('m_purch').value || 0, rev: +$('m_rev').value || 0 };
  p.metrics.push(row); persist(); render();
}
function delMetric(i) { cur().metrics.splice(i, 1); persist(); render(); }

// ============================================================
// SHOPIFY (live) — snapshot sincronizado por Claude vía MCP
// ============================================================
function vShopify() {
  const p = cur();
  const s = (typeof SHOPIFY_SNAPSHOT !== 'undefined') ? SHOPIFY_SNAPSHOT : null;
  if (!s) return head('Shopify (live)', 'Sin snapshot cargado.') + '<div class="empty">No se encontró shopify-sync.js.</div>';
  const applied = p && p.shopify;
  const f = s.funnel30d;
  const funnelPct = (num) => f.sessions ? (num / f.sessions * 100).toFixed(1) + '%' : '—';
  const prods = s.products.map(pr => `<tr>
    <td><b>${esc(pr.title)}</b><div class="hint">${esc(pr.handle)}${pr.sku ? ' · ' + esc(pr.sku) : ''}</div></td>
    <td><span class="tag ${pr.status === 'ACTIVE' ? 'ok' : 'dim'}">${pr.status}</span></td>
    <td class="num">${money(pr.price)}</td>
    <td class="num">${pr.inventory}</td></tr>`).join('');
  const flags = s.flags.map(fl => `<div class="rec ${fl.sev === 'bad' ? 'kill' : fl.sev === 'warn' ? 'iterate' : 'info'}"><b>${esc(fl.t)}</b><div class="why">${esc(fl.d)}</div></div>`).join('');
  const totalInv = s.products.reduce((a, pr) => a + pr.inventory, 0);
  return head('🔗 Shopify (live)', `Snapshot real de <b>${esc(s.shop.domain)}</b> sincronizado el ${s.syncedAt}. Para refrescar, pídele a Claude "re-sincroniza mi tienda".`,
    (applied ? '<span class="tag ok">Aplicado a este proyecto</span>' : '') + `<button class="btn" onclick="applyShopifySync()">${applied ? 'Re-aplicar' : 'Aplicar a este proyecto'}</button>`) + `
  <div class="kpis">
    <div class="kpi"><div class="l">Sesiones (30d)</div><div class="v">${f.sessions}</div></div>
    <div class="kpi ${f.cartAdditions <= 1 ? 'bad' : ''}"><div class="l">Add to cart</div><div class="v">${f.cartAdditions}</div><div class="s">${funnelPct(f.cartAdditions)} de sesiones</div></div>
    <div class="kpi ${f.completedCheckout === 0 ? 'bad' : 'good'}"><div class="l">Conversión</div><div class="v">${f.conversionRate}%</div><div class="s">${s.orders.count} pedidos</div></div>
    <div class="kpi"><div class="l">Ingresos</div><div class="v">${money(s.orders.revenue)}</div></div>
    <div class="kpi"><div class="l">Inventario total</div><div class="v">${totalInv}</div><div class="s">unidades</div></div>
    <div class="kpi ${p && p.shopify ? 'good' : 'warn'}"><div class="l">Break-even ROAS</div><div class="v">${applied ? economics(p.economics).beRoas.toFixed(2) : '—'}</div><div class="s">tras aplicar</div></div>
  </div>
  <div class="grid2" style="grid-template-columns:1.1fr .9fr">
    <div>
      <div class="panel"><h3 style="margin-top:0">Embudo real (últimos 30 días)</h3>
        <div class="scrollx"><table>
          <tr><th>Etapa</th><th class="num">Sesiones</th><th class="num">% del total</th></tr>
          <tr><td>Visitaron</td><td class="num">${f.sessions}</td><td class="num">100%</td></tr>
          <tr><td>Agregaron al carrito</td><td class="num">${f.cartAdditions}</td><td class="num">${funnelPct(f.cartAdditions)}</td></tr>
          <tr><td>Llegaron a checkout</td><td class="num">${f.reachedCheckout}</td><td class="num">${funnelPct(f.reachedCheckout)}</td></tr>
          <tr><td>Completaron compra</td><td class="num">${f.completedCheckout}</td><td class="num">${funnelPct(f.completedCheckout)}</td></tr>
        </table></div>
        <div class="hint" style="margin-top:8px">La fuga está en el primer escalón: casi nadie agrega al carrito. El problema es la oferta/PDP/confianza, no el checkout.</div>
      </div>
      <div class="panel"><h3 style="margin-top:0">Catálogo</h3>
        <div class="scrollx"><table><tr><th>Producto</th><th>Estado</th><th class="num">Precio</th><th class="num">Inv.</th></tr>${prods}</table></div>
      </div>
    </div>
    <div class="panel"><h3 style="margin-top:0">🧠 Diagnóstico del operador</h3>${flags}
      ${settings.apiKey ? '<button class="btn ai small" style="margin-top:8px" onclick="aiShopify()">✨ Plan de acción con IA</button>' : '<div class="hint">Conecta tu API key en Proyectos para un plan de acción con IA.</div>'}
    </div>
  </div>`;
}
function aiShopify() {
  const s = SHOPIFY_SNAPSHOT;
  askAI(`Estos son los datos REALES de mi tienda Shopify (${s.shop.domain}): ${s.funnel30d.sessions} sesiones en 30 días, ${s.funnel30d.cartAdditions} add-to-cart, ${s.orders.count} pedidos, conversión ${s.funnel30d.conversionRate}%. Catálogo: ${s.products.map(x => x.title + ' $' + x.price + ' (' + x.status + ')').join('; ')}. COGS landed $${s.cogsLanded}. Tengo tráfico pero cero ventas. Dame un plan de acción priorizado (máximo 5 acciones) para conseguir mis primeras ventas ESTA semana, del más al menos impactante, con el porqué de cada uno.`, 'Plan de acción Shopify');
}

// ============================================================
// ANALISTA IA (módulo libre) + llamadas por módulo
// ============================================================
function vAI() {
  return head('Analista IA', 'Chat libre con el operador. Tiene tu proyecto completo como contexto y analiza con la metodología de las 13 fases. Requiere API key (configúrala en Proyectos).') + `
  <div class="ai-box">
    <h3>✨ Pregunta lo que sea</h3>
    <textarea id="aiQ" style="min-height:90px" placeholder="Ej: 'Pega aquí los datos de tu campaña y pídeme el diagnóstico' · '¿Subo el precio a $54.95?' · 'Critica mi oferta actual'"></textarea>
    <div class="row" style="margin-top:10px">
      <button class="btn ai" onclick="aiFree()">Analizar</button>
      <span class="tag ${settings.apiKey ? 'ok' : 'bad'}">${settings.apiKey ? 'IA conectada · ' + settings.model : 'Sin API key'}</span>
    </div>
    <div id="aiOut"></div>
  </div>`;
}

function projectContext() {
  const p = cur(); if (!p) return 'Sin proyecto activo.';
  const ec = economics(p.economics);
  const w = p.candidates.find(c => c.id === p.winnerId);
  return `PROYECTO: ${p.name}
Producto ganador: ${p.producto || (w ? w.name : 'sin definir')}
Candidatos y scores: ${p.candidates.map(c => `${c.name}=${scoreTotal(c.scores)}${c.research.adLibraryCount != null ? ` (${c.research.adLibraryCount} ads activos)` : ''}`).join('; ') || 'ninguno'}
Economía: precio $${ec.price}, COGS+envío $${(ec.cogs + ec.ship).toFixed(2)}, margen ${(ec.marginPct * 100).toFixed(0)}%, break-even ROAS ${isFinite(ec.beRoas) ? ec.beRoas.toFixed(2) : 'n/a'}
Marca: ${p.brand.name} · "${p.brand.slogan}" · voz: ${p.brand.voz.slice(0, 140)}
Avatar: ${p.avatar.nombre} — ${p.avatar.demo}
Dolores: ${p.avatar.dolores.join(' | ')}
Beneficios: ${p.avatar.beneficios.join(' | ')}
Competidores: ${p.competitors.map(c => `${c.name} ($${c.price})`).join('; ')}
Hooks existentes (${p.hooks.length}): ${p.hooks.slice(0, 12).map(h => h.text).join(' | ')}
Métricas agregadas: ${p.metrics.length ? JSON.stringify(aggMetrics(p.metrics)) : 'sin datos aún'}`;
}

async function askAI(userPrompt, btnLabel) {
  if (!settings.apiKey) { toast('Configura tu API key en Proyectos'); nav('home'); return; }
  const out = $('aiOut');
  out.innerHTML = `<div class="ai-box"><span class="spin"></span> El operador está analizando… (puede tardar un poco, está pensando)</div>`;
  try {
    const res = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'x-api-key': settings.apiKey,
        'anthropic-version': '2023-06-01',
        'anthropic-dangerous-direct-browser-access': 'true',
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        model: settings.model,
        max_tokens: 8192,
        thinking: { type: 'adaptive' },
        system: AI_SYSTEM,
        messages: [{ role: 'user', content: `CONTEXTO DEL PROYECTO:\n${projectContext()}\n\n---\nTAREA:\n${userPrompt}` }],
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      const msg = data?.error?.message || res.status;
      out.innerHTML = `<div class="ai-box"><b style="color:var(--bad)">Error de API:</b> ${esc(msg)}${res.status === 401 ? ' — revisa tu API key.' : res.status === 429 ? ' — rate limit, espera un momento.' : ''}</div>`;
      return null;
    }
    const text = (data.content || []).filter(b => b.type === 'text').map(b => b.text).join('\n');
    out.innerHTML = `<div class="ai-box"><h3>✨ ${btnLabel}</h3><div class="ai-out">${esc(text)}</div>
      <div class="row" style="margin-top:10px"><button class="btn small ghost" onclick="navigator.clipboard.writeText(this.closest('.ai-box').querySelector('.ai-out').textContent);toast('Copiado')">Copiar</button></div></div>`;
    return text;
  } catch (e) {
    out.innerHTML = `<div class="ai-box"><b style="color:var(--bad)">Error de red:</b> ${esc(e.message)}</div>`;
    return null;
  }
}

function aiFree() { const q = $('aiQ').value.trim(); if (!q) return; askAI(q, 'Análisis'); }
function aiRadar() { askAI('Sugiere 8 productos candidatos NUEVOS (que no estén ya en mi lista) que pasarían el filtro de las 9 condiciones hoy. Para cada uno: nombre, keyword de búsqueda en inglés, por qué pasa el filtro, y riesgo principal. Prioriza categorías sin marca DTC dominante.', 'Candidatos sugeridos'); }
function aiScoring() { askAI('Puntúa cada candidato de mi lista en los 12 criterios (0-100) usando las guías del operador. Devuelve una tabla simple: candidato → los 12 scores → total ponderado. Después explica en 2 líneas por candidato tu razonamiento y señala dónde mis datos de Ad Library cambian el score.', 'Scoring del operador'); }
function aiWinner() { askAI('Evalúa mi elección de ganador y mi economía unitaria: ¿la elección es correcta vs el ranking? ¿El break-even ROAS es viable para paid frío? Dame 3 acciones concretas para mejorar la economía (precio, bundle, COGS) con números.', 'Validación del ganador'); }
function aiComp() { askAI('Con mis competidores mapeados: 1) ¿qué patrón común tienen sus ofertas?, 2) ¿cuáles de las 7 oportunidades clásicas están realmente abiertas aquí?, 3) diseña mi oferta anti-competencia (precio, ancla, garantía, bundle, ángulo) en formato listo para ejecutar.', 'Análisis competitivo'); }
function aiBrand() { askAI('Genera identidad de marca completa: 6 opciones de nombre (cortos, pronunciables, con .com probablemente libre — dilo como hipótesis a verificar), eslogan para cada uno, y para el mejor: paleta de 5 colores (hex), par tipográfico de Google Fonts, voz de marca (3 líneas), lo que nunca decimos, y concepto de logo.', 'Identidad generada'); }
function aiAvatar() { askAI('Construye la estrategia completa de marketing: avatar con nombre y contexto, 6 dolores, 5 deseos, 6 objeciones CON respuesta en copy, 5 beneficios en jerarquía, transformación DE→A, storytelling maestro de 4 líneas, y 5 pilares de contenido con % del mix.', 'Estrategia generada'); }
async function aiHooks() {
  const text = await askAI('Genera 30 hooks NUEVOS en inglés para mis ads (no repitas los existentes). Distribuye: 6 miedo/seguridad, 5 ahorro, 5 curiosidad/demo, 5 ritual/identidad, 4 regalo, 3 comparación, 2 humor. Formato ESTRICTO: una línea por hook, empezando con la categoría entre corchetes. Ej: [Miedo/Seguridad] I fell asleep with...', 'Hooks generados');
  if (!text) return;
  const lines = text.split('\n').map(l => l.trim()).filter(l => /^\[.+\]/.test(l));
  if (!lines.length) return;
  const p = cur();
  lines.forEach(l => {
    const m = l.match(/^\[(.+?)\]\s*(.+)$/); if (!m) return;
    p.hooks.push({ id: 'h' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5), cat: m[1], text: m[2], fav: false });
  });
  persist(); toast(`${lines.length} hooks agregados a tu librería`);
}
function aiConcepts() { askAI('Genera 24 conceptos de video nuevos (3 por cada uno de los 8 formatos), una línea cada uno, específicos para mi producto y avatar. Después elige los 3 con mayor probabilidad de ganar el testing y escribe su guion completo con la plantilla: Hook (0-3s) / Desarrollo / Prueba / CTA / Texto en pantalla / Música / Duración.', 'Conceptos y guiones'); }
function aiPrompts() { askAI('Genera prompts de producción listos para copiar: 3 de imagen (Midjourney), 3 de video (Kling/Runway, 8s, 9:16), 1 guion de voice over de 30s (ElevenLabs) y 2 estáticos para Meta. Usa mis colores de marca, producto y avatar reales. En inglés los prompts, con acotaciones en español.', 'Prompts a medida'); }
function aiLanding() { askAI('Escribe TODO el copy de mi landing en inglés: announcement bar, hero (eyebrow + H1 con quiebre emocional + subhead), 6 benefit cards (título + 2 líneas), sección de matemáticas del ahorro, tabla comparativa (3 columnas), oferta (nombre del bundle + qué incluye), garantía con nombre propio, 6 reviews sintéticas MARCADAS como placeholder a reemplazar con reales, y CTA final. Usa mi voz de marca.', 'Copy de landing'); }
function aiDash() { askAI('Analiza mis métricas como operador: diagnóstico del funnel completo (¿dónde está la fuga: hook, landing, checkout, oferta?), qué anuncios matar/escalar/iterar HOY con razones numéricas, y las 3 acciones de mayor impacto esta semana. Sé brutal y específico.', 'Diagnóstico de métricas'); }

// ---------- Init ----------
document.addEventListener('DOMContentLoaded', () => {
  render();
  const d = $('m_date'); if (d) d.valueAsDate = new Date();
});
