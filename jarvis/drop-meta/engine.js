// ============================================================
// DROP-META · Motores de cálculo y recomendación
// ============================================================

// ---------- Scoring (Fase 2) ----------
function scoreTotal(scores) {
  let t = 0;
  for (const k in WEIGHTS) t += (scores[k] || 0) * WEIGHTS[k].w;
  return Math.round(t * 10) / 10;
}

function scoreClass(total) { return total >= 75 ? 's1' : total >= 60 ? 's2' : 's3'; }

// Sugerencia de score de competencia a partir del conteo real de Ad Library
function compScoreFromAds(n) {
  if (n === null || n === undefined || n === '' || isNaN(n)) return null;
  n = +n;
  if (n < 15)  return { score: 50, nota: 'Muy pocos anunciantes: valida que exista demanda real antes de asumir "hueco".' };
  if (n <= 80) return { score: 78, nota: 'Sweet spot: demanda probada sin saturación. Verifica que no haya una marca DTC dominante.' };
  if (n <= 300) return { score: 60, nota: 'Competencia media: necesitas un ángulo o marca claramente diferenciados.' };
  if (n <= 800) return { score: 40, nota: 'Saturado: solo entra con un moat fuerte (marca, oferta, consumibles).' };
  return { score: 25, nota: 'Muy saturado: probablemente ya hay marcas dueñas de la categoría. Busca otro producto.' };
}

// ---------- Economía (Fase 3) ----------
function economics(e) {
  const price = +e.price || 0, cogs = +e.cogs || 0, ship = +e.ship || 0, feesPct = (+e.fees || 0) / 100;
  const fees = price * feesPct + 0.30;
  const profit = price - cogs - ship - fees;              // margen bruto por unidad antes de ads
  const marginPct = price ? profit / price : 0;
  const beRoas = profit > 0 ? price / profit : Infinity;  // ROAS para no perder dinero
  const targetRoas = Math.max(2.0, Math.round(beRoas * 1.4 * 100) / 100);
  const cpaBE = profit;                                    // CPA máximo en break-even
  const cpaTarget = profit > 0 ? price / targetRoas - 0 : 0; // gasto/compra en ROAS objetivo → utilidad = profit - price/targetRoas
  const utilTarget = profit - price / targetRoas;
  return { price, cogs, ship, fees, profit, marginPct, beRoas, targetRoas, cpaBE, utilTarget };
}

function econVerdict(ec) {
  const out = [];
  if (ec.marginPct >= 0.70) out.push({ c: 'ok', t: `Margen ${(ec.marginPct * 100).toFixed(0)}% ✓ (cumple el filtro ≥70%)` });
  else if (ec.marginPct >= 0.55) out.push({ c: 'warn', t: `Margen ${(ec.marginPct * 100).toFixed(0)}% — por debajo del 70% ideal; funciona pero deja menos aire para testear` });
  else if (ec.price) out.push({ c: 'bad', t: `Margen ${(ec.marginPct * 100).toFixed(0)}% — MUY apretado para paid ads. Sube precio, baja COGS o cambia de producto` });
  if (ec.price) {
    if (ec.beRoas <= 1.6) out.push({ c: 'ok', t: `Break-even ROAS ${ec.beRoas.toFixed(2)} — cómodo, casi cualquier campaña decente es rentable` });
    else if (ec.beRoas <= 2.3) out.push({ c: 'warn', t: `Break-even ROAS ${ec.beRoas.toFixed(2)} — exigente: necesitas creativos por encima del promedio` });
    else out.push({ c: 'bad', t: `Break-even ROAS ${ec.beRoas.toFixed(2)} — casi imposible con paid frío. Prioriza orgánico o arregla la economía` });
  }
  return out;
}

// ---------- Links de investigación en vivo (Fase 1/4) ----------
function researchLinks(keyword) {
  const q = encodeURIComponent(keyword || '');
  return [
    { n: 'Meta Ad Library', u: `https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&q=${q}&media_type=all` },
    { n: 'TikTok búsqueda', u: `https://www.tiktok.com/search?q=${q}` },
    { n: 'TikTok Creative Center', u: `https://ads.tiktok.com/business/creativecenter/inspiration/topads/pc/en?region=US&keyword=${q}` },
    { n: 'Google Trends', u: `https://trends.google.com/trends/explore?geo=US&q=${q}` },
    { n: 'Amazon', u: `https://www.amazon.com/s?k=${q}` },
    { n: 'AliExpress', u: `https://www.aliexpress.com/w/wholesale-${q.replace(/%20/g, '-')}.html` },
    { n: 'Alibaba', u: `https://www.alibaba.com/trade/search?SearchText=${q}` },
    { n: 'CJ Dropshipping', u: `https://www.cjdropshipping.com/search?keyword=${q}` },
    { n: 'Reddit', u: `https://www.reddit.com/search/?q=${q}` },
    { n: 'Etsy', u: `https://www.etsy.com/search?q=${q}` },
  ];
}

// ---------- Dashboard: agregación y motor de recomendaciones (Fase 13) ----------
function aggMetrics(rows) {
  const s = rows.reduce((a, r) => ({ spend: a.spend + (+r.spend || 0), impr: a.impr + (+r.impr || 0), clicks: a.clicks + (+r.clicks || 0), atc: a.atc + (+r.atc || 0), purch: a.purch + (+r.purch || 0), rev: a.rev + (+r.rev || 0) }), { spend: 0, impr: 0, clicks: 0, atc: 0, purch: 0, rev: 0 });
  s.cpm = s.impr ? s.spend / s.impr * 1000 : NaN;
  s.ctr = s.impr ? s.clicks / s.impr : NaN;
  s.cpc = s.clicks ? s.spend / s.clicks : NaN;
  s.cr = s.clicks ? s.purch / s.clicks : NaN;
  s.cpa = s.purch ? s.spend / s.purch : NaN;
  s.roas = s.spend ? s.rev / s.spend : NaN;
  s.aov = s.purch ? s.rev / s.purch : NaN;
  s.atcRate = s.clicks ? s.atc / s.clicks : NaN;
  s.atcToPurch = s.atc ? s.purch / s.atc : NaN;
  return s;
}

function adStatus(a, be, aovT) {
  const T = DEFAULT_THRESHOLDS;
  if (a.spend >= aovT && a.purch === 0) return { t: 'MATAR', c: 'bad' };
  if (a.spend >= T.minSpendRead && a.ctr < T.ctrMin) return { t: 'HOOK MUERTO', c: 'bad' };
  if (a.spend >= T.minSpendRead && a.cpc > T.cpcMax) return { t: 'CPC ALTO', c: 'bad' };
  if (a.roas >= Math.max(T.scaleRoas, be * 1.3) && a.purch >= 3) return { t: 'GANADOR', c: 'ok' };
  if (a.roas >= be) return { t: 'RENTABLE', c: 'ok' };
  if (a.purch > 0 && a.roas >= be * 0.7) return { t: 'OBSERVAR', c: 'warn' };
  if (a.spend < T.minSpendRead) return { t: 'APRENDIENDO', c: 'dim' };
  return { t: 'DÉBIL', c: 'warn' };
}

function buildRecs(g, adRows, ec, hasData) {
  const T = DEFAULT_THRESHOLDS, recs = [];
  const be = isFinite(ec.beRoas) ? ec.beRoas : 1.5;
  const scaleAt = Math.max(T.scaleRoas, Math.round(be * 1.3 * 100) / 100);
  const aovT = ec.price ? Math.max(ec.price, 50) : 70;
  const money = x => '$' + (+x).toFixed(2);
  const pct = x => isFinite(x) ? (x * 100).toFixed(2) + '%' : '—';

  if (!hasData) {
    recs.push({ type: 'info', t: 'Sin datos aún', why: 'Registra el primer día de cada anuncio. El motor recomienda a partir de ~$20 de gasto por anuncio.', act: '' });
    if (ec.price && ec.beRoas > 2.3) recs.push({ type: 'kill', t: '⚠️ Tu economía actual es frágil ANTES de gastar', why: `Break-even ROAS ${ec.beRoas.toFixed(2)}: con paid frío casi ninguna campaña promedio sobrevive esto.`, act: 'Antes de prender ads: sube el precio, arma un bundle que suba el AOV, o negocia el COGS. Cada dólar de COGS que bajes vale más que cualquier truco de campaña.' });
    return recs;
  }

  const winners = adRows.filter(a => a.roas >= scaleAt && a.purch >= 3);
  const dead = adRows.filter(a => a.spend >= aovT && a.purch === 0);
  const weakHooks = adRows.filter(a => a.spend >= T.minSpendRead && a.ctr < T.ctrMin);
  const nearBE = adRows.filter(a => a.purch > 0 && a.roas >= be * 0.7 && a.roas < be);

  dead.forEach(a => recs.push({ type: 'kill', t: `🔪 Apagar "${a.name}"`, why: `Gastó ${money(a.spend)} (≥ 1× AOV objetivo) sin una sola compra. Se corta hoy, sin negociar.`, act: 'Reemplázalo con un concepto de OTRO formato (módulo Conceptos & Guiones).' }));
  weakHooks.forEach(a => { if (!dead.includes(a)) recs.push({ type: 'kill', t: `🪝 Hook muerto en "${a.name}"`, why: `CTR ${pct(a.ctr)} con ${money(a.spend)} gastados (umbral 0.8%). La gente ni se detiene.`, act: 'Mantén el cuerpo del video y cambia SOLO los primeros 3 segundos: prueba 3 hooks nuevos del módulo Hooks (miedo/seguridad y curiosidad suelen tener el CTR más alto).' }); });

  winners.forEach(a => recs.push({ type: 'scale', t: `🚀 Escalar "${a.name}"`, why: `ROAS ${a.roas.toFixed(2)} (tu break-even es ${be.toFixed(2)}) con ${a.purch} compras — ganador confirmado.`, act: 'Duplica el ad set a 2× presupuesto (no edites el original). +20-30% cada 48h mientras aguante. Produce 3 variantes del MISMO formato cambiando solo el hook.' }));
  if (winners.length >= 3 && g.purch >= 30) recs.push({ type: 'scale', t: '🏗️ Momento de pasar a CBO', why: `${winners.length} ganadores y ${g.purch} compras: suficiente señal para consolidar.`, act: `Campaña CBO $100/día con los ganadores + 2 variantes frescas. +20% cada 2 días si ROAS ≥ ${scaleAt}; -20% si baja del break-even 2 días seguidos.` });

  if (isFinite(g.ctr) && g.ctr >= 0.012 && isFinite(g.cr) && g.cr < T.crMin && g.clicks >= 300)
    recs.push({ type: 'iterate', t: '🛠️ El problema es la LANDING, no los ads', why: `CTR sano (${pct(g.ctr)}) pero conversión ${pct(g.cr)} (objetivo ≥2%). El ad promete y la página no cierra.`, act: 'En orden: 1) carga <2.5s móvil, 2) el hero debe repetir la promesa del ad ganador, 3) reviews con foto arriba del fold, 4) garantía pegada al botón ATC. Checklist completo en el módulo Landing.' });
  if (isFinite(g.atcRate) && g.atcRate >= T.atcRateSano && isFinite(g.atcToPurch) && g.atcToPurch < 0.25 && g.atc >= 30)
    recs.push({ type: 'iterate', t: '💳 Fuga en el CHECKOUT / precio', why: `${pct(g.atcRate)} agrega al carrito pero solo ${pct(g.atcToPurch)} de ellos compra (sano: ≥30%). Quieren el producto; el precio o la fricción los frena.`, act: 'Prueba en orden: 1) Shop Pay en 4 pagos visible, 2) ¿free shipping visible o hay costo sorpresa?, 3) test A/B de precio una semana, 4) mover el upsell a post-purchase.' });
  if (isFinite(g.aov) && ec.price && g.aov < ec.price * 1.15 && g.purch >= 10)
    recs.push({ type: 'iterate', t: '📦 AOV plano — nadie toma el bundle', why: `AOV ${money(g.aov)} ≈ precio base: casi todos compran la unidad sola.`, act: 'Haz el bundle irresistible: preselecciónalo, baja su ancla, agrega regalo "solo esta semana", y mete un bump barato in-cart.' });
  if (isFinite(g.cpm) && g.cpm > T.cpmAlto && g.impr > 20000)
    recs.push({ type: 'iterate', t: '📡 CPM alto', why: `CPM ${money(g.cpm)} — público muy estrecho, cuenta fría o creativos fatigados.`, act: 'Amplía a broad/Advantage+, revisa ads rechazados o texto policy-sensitive, y sube creativos nuevos.' });
  if (nearBE.length)
    recs.push({ type: 'iterate', t: `⏳ En observación: ${nearBE.map(a => '"' + a.name + '"').join(', ')}`, why: `ROAS entre ${(be * 0.7).toFixed(2)} y tu break-even (${be.toFixed(2)}). Ni matar ni escalar todavía.`, act: 'Dales 2 días más. Si no cruzan break-even: cambia SOLO el hook y thumbnail, nunca todo a la vez (pierdes la lectura).' });

  if (isFinite(g.roas) && g.spend >= 200) {
    if (g.roas >= be * 1.25 && g.cr >= T.crObjetivo)
      recs.push({ type: 'scale', t: '✅ Estado general: ESCALAR', why: `ROAS blended ${g.roas.toFixed(2)} ≥ 1.25× tu break-even con conversión sana.`, act: 'Sube presupuesto total a $150-300/día, encarga packaging custom y negocia COGS con volumen. Si Q4 está a <60 días, prepara el ángulo de regalo.' });
    else if (g.roas < be)
      recs.push({ type: 'kill', t: '🛑 Estado general: PERDIENDO DINERO', why: `ROAS blended ${g.roas.toFixed(2)} < break-even ${be.toFixed(2)} con gasto significativo.`, act: 'Si ya iteraste 2 batches de creativos Y la landing: regla de los 30 días — mata el producto y pasa al candidato #2 del ranking. Las pérdidas se cortan, no se negocian.' });
  }
  return recs;
}

// ---------- Proyecto en blanco ----------
function blankProject(name) {
  return {
    id: 'p' + Date.now().toString(36), name, producto: '', createdAt: new Date().toISOString(),
    candidates: [], winnerId: null,
    economics: { cogs: 0, ship: 0, fees: 2.9, price: 0, anchor: 0, aovTarget: 0 },
    competitors: [], oportunidades: OPPORTUNITY_PATTERNS.map(t => ({ text: t, done: false, nota: '' })),
    brand: { name: '', domain: '', slogan: '', sloganAlt: '', colors: { primary: '#E8A855', dark: '#2B2622', light: '#F7F1E8', accent: '#6E4B2A', cta: '#D97B29' }, fontDisplay: 'Fraunces', fontBody: 'Inter', voz: '', nunca: '', logo: '', packaging: '' },
    avatar: { nombre: '', demo: '', dolores: [], deseos: [], objeciones: [], beneficios: [], transDe: '', transA: '', story: '', pilares: [] },
    hooks: [], concepts: [], scripts: [],
    checks: { landing: {}, tienda: {} },
    launch: { budget: 1500, days: 30, metaPct: 70 },
    metrics: [],
  };
}

// ---------- Seed: LUMBRA (proyecto real de ejemplo) ----------
function seedLumbra() {
  const p = blankProject('LUMBRA');
  p.id = 'lumbra-seed';
  p.producto = 'Candle warmer lamp premium (dimmer + timer + base de nogal)';
  const F = (v) => Object.fromEntries(FILTER_CRITERIA.map((c, i) => [c.k, v[i] === 1]));
  const mk = (name, keyword, sc, ads, f) => ({ id: 'c' + Math.random().toString(36).slice(2, 8), name, keyword, notes: '', filter: F(f || [1,1,1,1,1,1,1,1,1]), scores: sc, research: { adLibraryCount: ads, cogs: null, price: null } });
  p.candidates = [
    mk('Candle warmer lamp premium', 'candle warmer lamp', { tend: 90, comp: 72, viral: 88, creat: 92, cpm: 85, ctr: 85, cpc: 80, conv: 85, aov: 78, ups: 95, cross: 95, marca: 90 }, 94),
    mk('Rodillo facial EMS', 'ems face roller', { tend: 92, comp: 45, viral: 85, creat: 80, cpm: 55, ctr: 75, cpc: 60, conv: 65, aov: 85, ups: 70, cross: 60, marca: 75 }, 13, [1,0,1,1,1,0,1,0,1]),
    mk('Sleep earbuds', 'sleep earbuds', { tend: 85, comp: 40, viral: 70, creat: 65, cpm: 60, ctr: 65, cpc: 60, conv: 55, aov: 80, ups: 50, cross: 55, marca: 70 }, 1700, [1,0,1,0,1,1,1,1,0]),
    mk('Lámpara desk + carga inalámbrica', 'wireless charging desk lamp', { tend: 75, comp: 65, viral: 60, creat: 70, cpm: 75, ctr: 65, cpc: 70, conv: 70, aov: 70, ups: 55, cross: 50, marca: 60 }, null),
    mk('Manta sauna infrarroja', 'sauna blanket', { tend: 82, comp: 35, viral: 65, creat: 60, cpm: 50, ctr: 60, cpc: 50, conv: 50, aov: 90, ups: 60, cross: 55, marca: 70 }, 220, [1,0,0,0,0,1,0,1,1]),
  ];
  p.winnerId = p.candidates[0].id;
  // Economía REAL de la tienda (CJ bodega US): COGS+envío 32.30, venta 49.95
  p.economics = { cogs: 32.30, ship: 0, fees: 2.9, price: 49.95, anchor: 74.95, aovTarget: 60 };
  p.competitors = [
    { name: 'Amazon genéricos (GODONLIF, Engpure…)', tier: 'Masivo', price: '26-46', offer: 'Producto solo, Prime', garantia: '30-90 días', hooks: '"lasts longer", "no flame"', publico: 'Mujer 25-45 decor', fortalezas: 'Precio + Prime + reviews', debilidades: 'Cero marca, fotos catálogo chino' },
    { name: 'Target (Threshold)', tier: 'Retail', price: '25-35', offer: 'Disponibilidad física', garantia: 'Return estándar', hooks: 'Diseño mid-century', publico: 'Compradora Target', fortalezas: 'Confianza + tiendas', debilidades: 'Sin juego social/DTC' },
    { name: 'Docos Celeste', tier: 'Boutique', price: '60-90', offer: 'Mármol/nogal real', garantia: 'Estándar', hooks: 'Materiales premium', publico: 'Decor lover $$$', fortalezas: 'Calidad real', debilidades: '1 producto, sin comunidad ni consumibles' },
    { name: 'Candle Warmers Etc.', tier: 'OEM veterana', price: '30-50', offer: 'Catálogo amplio', garantia: 'Estándar', hooks: 'Funcional', publico: 'Compradora de velas', fortalezas: 'Distribución', debilidades: 'Web anticuada, cero social' },
  ];
  p.oportunidades = [
    { text: 'Nadie tiene marca real → LUMBRA como "la marca" de la categoría', done: true, nota: 'Core de la estrategia' },
    { text: 'Nadie vende el ritual (todos venden el aparato) → "Light the calm"', done: true, nota: '' },
    { text: 'Ecosistema consumible: velas propias (Lumbra Wicks) en fase 2', done: false, nota: 'Mes 2-3 si ROAS ≥ 2' },
    { text: 'Garantía 2 años vs 30-90 días de todos', done: true, nota: '' },
    { text: 'Ángulo gifting Q4 virgen ("el regalo que enciende cada noche")', done: false, nota: 'Activar octubre' },
    { text: 'Packaging premium → unboxing UGC gratis', done: false, nota: 'Custom al llegar a 20 pedidos/día' },
  ];
  p.brand = { name: 'LUMBRA', domain: 'thelumbra.com', slogan: 'Light the calm.', sloganAlt: 'The warmest gift in the room.', colors: { primary: '#E8A855', dark: '#2B2622', light: '#F7F1E8', accent: '#6E4B2A', cta: '#D97B29' }, fontDisplay: 'Fraunces', fontBody: 'Inter', voz: 'La amiga calmada que ya arregló su vida. Serena, cálida, un punto poética, nunca cursi, nunca gritona. Hablamos de rituales, atmósfera, el final del día.', nunca: '"¡OFERTA!", "gadget", claims médicos ("cura", "trata"). Máximo 1 emoji por copy (🕯️✨🌙).', logo: 'Wordmark serif tracking amplio + isotipo: círculo cálido sobre semicírculo (luz sobre vaso de vela / sol en horizonte). Monolinea.', packaging: 'Caja negra mate, isotipo dorado, interior crema, tarjeta "Your first ritual" con 3 pasos.' };
  p.avatar = {
    nombre: 'Maya', demo: 'Mujer 26-42, US, $45-90K, renta o primera casa. Compra velas cada mes. Feed: cozy home, 5-9 after my 9-5, romanticize your life. Impulso sin consultar: <$80. Secundario Q4: "el que regala" ($50-100 sin pestañear).',
    dolores: ['Miedo real a dejarse la vela encendida (dormirse, salir, gato)', 'Humo negro y hollín en paredes; aire que respira', 'Velas de $30 que se consumen en días → culpa', 'Túnel en la vela: se desperdicia la mitad de la cera', 'No logra "apagar la cabeza" en la noche; termina en el teléfono', 'Su cuarto no se siente como el Pinterest que guarda'],
    deseos: ['Un hogar que se sienta santuario', 'Ritual nocturno que la haga sentir en control', 'Objetos que digan algo de ella (quiet luxury)', 'Ahorro sin sentirse tacaña', 'Regalos que la gente recuerde'],
    objeciones: [
      { o: 'Will it really make the candle smell stronger?', r: 'Yes — flame burns fragrance oil before it evaporates. Gentle top-down heat melts the whole surface evenly, releasing scent without combusting it.' },
      { o: 'Will it fit my Bath & Body Works 3-wick?', r: 'Yes. Height-adjustable arm fits any candle up to 8 inches.' },
      { o: 'Is it safe to leave on?', r: 'No flame; wax warms to ~130-165°F. Treat it like any lamp.' },
      { o: 'En Amazon hay más baratas', r: 'Diseño nogal real + dimmer continuo + garantía 2 años + Ritual Set. "Las baratas derriten plástico, no cera."' },
      { o: '¿Gasta mucha luz?', r: 'Bombilla halógena: centavos por noche.' },
    ],
    beneficios: ['Seguridad total: duérmete con ella encendida; el timer la apaga solo', 'Tu vela dura 3x: el calor derrite sin consumir la cera a llama', 'Aroma más intenso y parejo, cero humo', 'Es una lámpara hermosa: dimmer ámbar = atmósfera aunque no haya vela', 'El ritual: 10 segundos para convertir tu cuarto en santuario'],
    transDe: 'cuarto genérico, noche de scroll, ansiedad de vela encendida, velas caras que duran nada',
    transA: 'un click al atardecer → luz ámbar, aroma envolvente, teléfono lejos. You didn\'t buy a lamp. You bought your evenings back.',
    story: '"Casi quemo mi departamento por quedarme dormida con una vela encendida. Ahora enciendo mi Lumbra: la misma luz cálida, el mismo aroma —más fuerte, de hecho— y se apaga sola a las 11. Mi vela de $34 lleva DOS MESES viva." Arquetipo: el pequeño objeto que ordena el caos (Stanley Cup = hidratación; Lumbra = noches).',
    pilares: ['ASMR/satisfying: cera derritiéndose, dimmer bajando (40%)', 'Ritual nocturno / romanticize your evening (25%)', 'Seguridad + mascotas/bebés (15%)', 'Ahorro/velas eternas + hack B&BW (10%)', 'Gifting (10%, sube a 40% en Q4)'],
  };
  const H = (cat, arr) => arr.map(t => ({ id: 'h' + Math.random().toString(36).slice(2, 8), cat, text: t, fav: true }));
  p.hooks = [
    ...H('Miedo/Seguridad', ['I fell asleep with a candle burning… again.', 'POV: you\'re 40 minutes from home and can\'t remember if you blew out the candle.', 'It turns off by itself at 11pm. Even if I\'m already asleep.', 'If you have cats, stop lighting candles. Seriously.']),
    ...H('Ahorro', ['My $34 candle has lasted 2 months and it\'s still full.', 'Bath & Body Works doesn\'t want you to know this.', 'The rich don\'t burn their candles. They melt them.']),
    ...H('Curiosidad/Demo', ['It\'s not a lamp. Well… it is. But watch.', 'Watching the wax melt under the light is my new personality.', 'It makes your candle smell STRONGER. I don\'t get it either.']),
    ...H('Ritual/Identidad', ['The last 20 minutes of my day belong to this lamp.', 'POV: it\'s 9:47pm and your room turns into a sanctuary.', 'There are two types of people: candle burners and candle melters.', 'The "big light" could never.']),
    ...H('Regalo', ['The gift that makes her think of you every single night.', 'For the person who "already has everything": they don\'t have this.']),
  ];
  p.concepts = [
    { id: 'k1', formato: 'UGC', text: '"Casi quemo mi departamento" — historia completa, giro, solución (32s)' },
    { id: 'k2', formato: 'UGC', text: 'Review honesta día 30: lo bueno, lo malo (el melt tarda 15 min), la vela intacta' },
    { id: 'k3', formato: 'POV', text: 'POV: son las 9:47pm y tu cuarto se convierte en santuario (15s, sin voz)' },
    { id: 'k4', formato: 'Demo', text: 'Time-lapse 20 min: capa superior volviéndose espejo líquido (12s, ASMR)' },
    { id: 'k5', formato: 'Comparación', text: 'Costo anual: 12 velas × $34 vs lámpara + 4 velas (girl math en pantalla)' },
    { id: 'k6', formato: 'Problema-Solución', text: 'Vela con túnel → rescate en 40 min bajo la lámpara (before/after satisfying)' },
    { id: 'k7', formato: 'Humor', text: 'El encendedor de la casa presenta su renuncia formal (carta leída en VO)' },
    { id: 'k8', formato: 'Tendencia', text: '"Things in my apartment that just make sense" — night edition, cierre en la lámpara' },
  ];
  p.scripts = [
    { id: 's1', titulo: 'UGC-1 · Casi quemo mi departamento', formato: 'UGC', dur: '32s', hook: '"I fell asleep with a candle burning… again." (a cámara, seria, luz de día)', desarrollo: 'Tercera vez → tiró las velas → odió su depa sin ellas → el feed le enseñó esto. Corte: unboxing rápido + demo dimmer y timer. "Mismo olor —más fuerte— cero llama."', prueba: 'Vela de enero sigue viva (muestra fecha de compra en pantalla)', cta: '"30 noches de prueba en thelumbra.com" + toma final: cuarto ámbar, ella dormida, luz apagándose sola', texto: '"fell asleep with it ON 😳" → "flame-free 🕯️" → "auto-off timer" → "30-night trial"', musica: 'Lo-fi suave, sube al reveal del cuarto', estado: 'listo' },
    { id: 's2', titulo: 'DEMO-1 · Melt pool time-lapse', formato: 'Demo', dur: '12s', hook: 'Macro inmediato de cera empezando a brillar. Texto: "the most satisfying 20 minutes, in 10 seconds"', desarrollo: 'Time-lapse continuo: superficie mate → espejo líquido reflejando la luz ámbar. Sin cortes, sin voz.', prueba: '', cta: 'Frame final: logo + "Light the calm — thelumbra.com"', texto: 'Mínimo: el video ES el texto', musica: 'ASMR crackle + ambient (audio original = mejor distribución)', estado: 'listo' },
    { id: 's3', titulo: 'COMP-2 · Girl math anual', formato: 'Comparación', dur: '20s', hook: 'Nota del teléfono en pantalla: "Cuánto gasté en velas en 2025: $412 😵"', desarrollo: 'Cálculo animado: 12 velas × $34 = $412/año. Con lámpara: 4 velas + lámpara = $196 el primer año. Ella asintiendo a cámara.', prueba: 'Los números en pantalla SON la prueba', cta: '"Tu colección de velas por fin es una inversión. Link en bio."', texto: 'El cálculo completo (protagonista del video)', musica: 'Trend "money" sound del momento', estado: 'borrador' },
  ];
  p.checks.tienda = { dominio: true, pixels: true, shoppay: false, muestra: true };
  p.launch = { budget: 1500, days: 30, metaPct: 70 };
  return p;
}
