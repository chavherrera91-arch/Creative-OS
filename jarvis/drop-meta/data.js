// ============================================================
// DROP-META · Datos de la metodología (13 fases)
// ============================================================

const WEIGHTS = {
  tend:  { w: .15, nombre: 'Tendencia' },
  comp:  { w: .15, nombre: 'Competencia' },
  viral: { w: .10, nombre: 'Viralidad' },
  creat: { w: .10, nombre: 'Potencial creativo' },
  cpm:   { w: .07, nombre: 'CPM esperado' },
  ctr:   { w: .08, nombre: 'CTR esperado' },
  cpc:   { w: .05, nombre: 'CPC esperado' },
  conv:  { w: .10, nombre: 'Conversión esperada' },
  aov:   { w: .07, nombre: 'AOV' },
  ups:   { w: .05, nombre: 'Upsells' },
  cross: { w: .03, nombre: 'Cross-sells' },
  marca: { w: .05, nombre: 'Potencial de marca' },
};

// Guías: cómo puntuar cada criterio igual que lo hace el operador
const SCORE_GUIDES = {
  tend:  '90+: demanda creciente sostenida años (Google Trends al alza, 50M+ vistas hashtag). 70: tendencia sólida pero estable. 50: plana. <40: en declive o moda ya pasada.',
  comp:  'MÁS ALTO = MENOS saturado. Usa el conteo de Meta Ad Library: 15-80 ads activos y SIN marca DTC dominante = 70-85 (sweet spot). <15 = 50 (¿hay demanda?). 80-300 = 55-65. 300-800 = 40. >800 o con marca dueña de la categoría (ej. HeatPod en sauna blankets) = 20-35.',
  viral: '90+: el producto ES contenido (ASMR, satisfying, transformación visual en <3s). 70: visual pero necesita contexto. 50: hay que explicarlo. <40: aburrido en video.',
  creat: '¿Cuántos ángulos distintos soporta? 90+: 5+ ángulos (miedo, ahorro, estética, regalo, identidad). 70: 3 ángulos. 50: 1-2. Menos ángulos = fatiga creativa rápida.',
  cpm:   'MÁS ALTO = CPM más barato. Hogar/decor broad = 80-90 (CPM $8-14). Fitness/mascotas = 65. Beauty = 55. Salud/claims sensibles = 40 (Meta castiga o rechaza).',
  ctr:   'Estima el thumb-stop: producto visualmente magnético = 85+. Normal = 60. Genérico/commodity = 40.',
  cpc:   'Derivado de CPM y CTR. Nicho amplio con creativo fuerte = 80. Nicho caro (finanzas, salud) = 40.',
  conv:  'Compra impulsiva sin educación, precio <$80, oferta clara = 80+. Requiere comparar/preguntar a la pareja = 50. Ticket alto o compra pensada = 35.',
  aov:   '$70+ alcanzable con bundles = 80+. $40-70 = 60. <$35 = 35 (el CPA se come el margen).',
  ups:   '¿Hay upsell natural obvio? (2ª unidad, versión pro, accesorio) 90 = sí y barato de agregar. 50 = forzado. 20 = no existe.',
  cross: '¿Hay CONSUMIBLE recurrente? (velas, refills, cápsulas) = 90+ (motor de LTV). Accesorios one-off = 60. Nada = 25.',
  marca: '¿Puede ser "la marca" de la categoría? Categoría sin dueño + producto identitario = 90. Commodity puro = 25.',
};

// Filtro Fase 1 — los 9 criterios de entrada
const FILTER_CRITERIA = [
  { k: 'organico',  t: 'Mucho contenido orgánico ya existe (hashtags con 10M+ vistas)' },
  { k: 'saturacion',t: 'Poca saturación de anunciantes (verificado en Ad Library)' },
  { k: 'margen',    t: 'Margen ≥70% posible (COGS landed ≤30% del precio de venta)' },
  { k: 'impulso',   t: 'Se compra por impulso (no requiere investigación previa)' },
  { k: 'precio',    t: 'Precio de venta viable entre $30 y $120 USD' },
  { k: 'educacion', t: 'No requiere educación compleja (se entiende en 3 segundos de video)' },
  { k: 'envio',     t: 'Envío sencillo (ligero, sin batería/líquidos/tallas/frágil)' },
  { k: 'legal',     t: 'Sin problemas legales (sin claims médicos, sin marcas registradas, certificable)' },
  { k: 'ugc',       t: 'Alto potencial de UGC (la gente querría grabarse usándolo)' },
];

// Formatos de concepto (Fase 7)
const CONCEPT_FORMATS = [
  { k: 'UGC',       meta: 50, desc: 'Creador hablando a cámara, estilo review auténtica' },
  { k: 'POV',       meta: 30, desc: 'Punto de vista inmersivo, texto en pantalla' },
  { k: 'Storytelling', meta: 30, desc: 'Historia con conflicto, giro y resolución' },
  { k: 'Problema-Solución', meta: 30, desc: 'Dolor visual → producto resolviéndolo' },
  { k: 'Comparación', meta: 30, desc: 'Lado a lado: antes/después, barato/premium, con/sin' },
  { k: 'Demo',      meta: 30, desc: 'El producto trabajando, sin narrativa (satisfying)' },
  { k: 'Humor',     meta: 20, desc: 'Sketch, personificación, absurdo' },
  { k: 'Tendencia', meta: 20, desc: 'Plantilla viral del momento adaptada al producto' },
];

// Categorías de hooks con plantillas rellenables
const HOOK_ANGLES = [
  { k: 'Miedo/Seguridad', tpl: ['I almost {desastre} because of {producto_viejo}…', 'POV: you\'re 40 minutes away and can\'t remember if you {riesgo}', 'If you have {mascota/hijos}, stop using {producto_viejo}. Seriously.'] },
  { k: 'Ahorro', tpl: ['My {objeto} has lasted {tiempo} and it\'s still {estado}.', 'I did the math: this paid for itself in {n} weeks.', '{marca_conocida} doesn\'t want you to know this.'] },
  { k: 'Curiosidad/Demo', tpl: ['It\'s not a {categoria}. Well… it is. But watch.', 'Watch what happens to {objeto} after {tiempo}.', 'Everyone asks about this. Nobody believes what it does.'] },
  { k: 'Ritual/Identidad', tpl: ['The last 20 minutes of my day belong to this.', 'POV: it\'s {hora} and your {espacio} becomes a sanctuary.', 'Tell me you\'re in your {era} era without telling me.'] },
  { k: 'Regalo', tpl: ['The gift that makes her think of you every {frecuencia}.', 'For the person who "already has everything": they don\'t have this.', 'Stop giving {regalo_generico}. Give them {transformacion}.'] },
  { k: 'Comparación', tpl: ['I tested the $:{precio_bajo} one and the $:{precio_alto} one. Big difference.', 'There are two types of people: {tipo_a} and {tipo_b}.', '{solucion_vieja} vs this — side by side.'] },
  { k: 'Humor', tpl: ['My {objeto_viejo} handed in its resignation letter.', 'Girl math: technically this {producto} pays ME.', 'My {familiar} said "it\'s just a {categoria}." Day 9: it\'s THEIR {categoria} now.'] },
  { k: 'Social proof', tpl: ['I saw this {n} times on my feed before caving. Should\'ve caved sooner.', '{n}+ people bought this last month and I get why.', 'My most-asked-about purchase of {año}.'] },
];

// Plantilla maestra de guion (Fase 8)
const SCRIPT_TEMPLATE = {
  hook: 'Conflicto, pregunta o imagen imposible de ignorar (0-3s). El texto en pantalla SIEMPRE duplica el hook.',
  desarrollo: 'UNA sola idea. Cada 2-3 segundos algo cambia en pantalla. Mostrar el producto trabajando, no describirlo.',
  prueba: 'Número, fecha, comparación o reacción de un tercero (opcional, 3-5s).',
  cta: 'Beneficio + destino + reductor de riesgo. Nunca "buy now" seco.',
  texto: 'Máximo 6 palabras por frame. Subtítulos automáticos siempre.',
  musica: 'Cozy/lo-fi para POV y demo; trend sounds para UGC y humor. Renovar cada 2 semanas.',
};

// Checklist PDP / Tienda (Fase 11)
const STORE_CHECKLIST = [
  { k: 'dominio', t: 'Dominio propio comprado y conectado' },
  { k: 'galeria', t: 'PDP: 7 assets (hero, video 15s, macro, escala, lifestyle, unboxing, tabla comparativa)' },
  { k: 'reviews_top', t: 'Estrellas + conteo arriba del título' },
  { k: 'ancla', t: 'Precio con ancla tachada + badge de descuento' },
  { k: 'installments', t: 'Pagos en 4 visibles (Shop Pay installments)' },
  { k: 'bundles', t: 'Selector de bundle (Solo / Set ★ / Duo) con el Set preseleccionado' },
  { k: 'incluye', t: 'Lista "What\'s included" con regalos' },
  { k: 'sticky', t: 'Sticky Add-to-Cart activo' },
  { k: 'urgencia', t: 'Urgencia HONESTA (oferta semanal real con countdown, nunca stock falso)' },
  { k: 'trust', t: 'Trust badges bajo el ATC (garantía, envío, prueba, checkout seguro)' },
  { k: 'acordeones', t: 'Acordeones: How it works / Shipping / Warranty / Specs' },
  { k: 'comparativa', t: 'Sección comparativa (genérico vs premium vs tuyo)' },
  { k: 'reviews_fold', t: '6+ reviews con foto (reales, sembradas con muestras)' },
  { k: 'faqs', t: 'FAQs que matan las 5 objeciones principales' },
  { k: 'upsell_cart', t: 'Upsell in-cart (consumible/accesorio barato)' },
  { k: 'postpurchase', t: 'Post-purchase one-click upsell (AfterSell o similar)' },
  { k: 'shoppay', t: 'Checkout: Shop Pay + express buttons activados' },
  { k: 'checkout_min', t: 'Checkout: sin teléfono obligatorio, sin cuenta forzada' },
  { k: 'pixels', t: 'Pixel Meta + TikTok + CAPI instalados y verificados con evento de prueba' },
  { k: 'popup', t: 'Email popup (a los 12s o 40% scroll) con oferta de bienvenida' },
  { k: 'flow_welcome', t: 'Klaviyo flow: Welcome (3 emails)' },
  { k: 'flow_abandon', t: 'Klaviyo flow: Abandoned checkout (1h / 24h / 48h)' },
  { k: 'flow_post', t: 'Klaviyo flow: Post-purchase (expectativas → guía → review → cross-sell)' },
  { k: 'tracking_page', t: 'Página de tracking con branding (Track123 o similar)' },
  { k: 'politicas', t: 'Políticas completas: refund, shipping, privacy, terms' },
  { k: 'soporte', t: 'Email de soporte con macros, respuesta <12h' },
  { k: 'muestra', t: 'MUESTRA física aprobada en mano ANTES del primer dólar en ads' },
];

const LANDING_CHECKLIST = [
  { k: 'hero', t: 'Hero: promesa principal en <2s + CTA único + social proof' },
  { k: 'carga', t: 'Carga <2.5s en móvil (comprimir imágenes, sin apps basura)' },
  { k: 'espejo', t: 'El hero REPITE la promesa del ad ganador (message match)' },
  { k: 'beneficios', t: '4-6 beneficios en jerarquía emocional → racional' },
  { k: 'math', t: 'Sección de "matemáticas" (ahorro, costo por uso, payback)' },
  { k: 'compare', t: 'Tabla comparativa vs alternativas' },
  { k: 'oferta', t: 'Oferta con ancla, bundle y regalos claros' },
  { k: 'garantia', t: 'Garantía agresiva y visible junto al botón' },
  { k: 'reviews', t: 'Reviews con nombre, ciudad y foto' },
  { k: 'faq', t: 'FAQ = las objeciones del avatar respondidas' },
  { k: 'ctafinal', t: 'CTA final emocional + sticky ATC en scroll' },
];

// Kill rules y umbrales por defecto (Fase 12) — se recalculan con la economía del proyecto
const DEFAULT_THRESHOLDS = {
  ctrMin: 0.008,      // 0.8%
  ctrSano: 0.015,
  cpcMax: 2.50,
  minSpendRead: 20,
  crObjetivo: 0.02,
  crMin: 0.012,
  atcRateSano: 0.08,
  atcToPurchSano: 0.30,
  cpmAlto: 20,
  scaleRoas: 2.0,
};

// Prompts IA por tipo de asset (Fase 9) — plantillas con variables del proyecto
const AI_PROMPT_TEMPLATES = [
  { k: 'Imagen hero', tool: 'Midjourney / Flux / Gemini', tpl: 'Product photography of {producto}, {materiales}, {color_primario} accent lighting over dark warm background ({color_oscuro}), soft rim lighting, shallow depth of field, editorial style, 8k, photorealistic --ar 4:5' },
  { k: 'Lifestyle', tool: 'Midjourney / Flux', tpl: 'Cozy {espacio} at night, {producto} glowing {color_primario}, {avatar} using it naturally, warm shadows, cinematic photography, 35mm film grain --ar 9:16' },
  { k: 'Video demo', tool: 'Kling / Runway / Veo', tpl: 'Macro shot: {producto} in action, {accion_satisfying}, cozy dark room background, satisfying, photorealistic, static camera, 8 seconds, 9:16 vertical' },
  { k: 'Video POV', tool: 'Kling / Runway', tpl: 'First person POV: {ritual_de_uso}, warm light rises, shallow DOF, cozy night ambiance, 8 seconds, 9:16 vertical' },
  { k: 'Voice Over', tool: 'ElevenLabs (voz femenina 25-35, stability 45-55%)', tpl: '{hook_ganador} [pause] {desarrollo_conversacional} [pause] {cta_con_garantia}' },
  { k: 'Miniatura comparación', tool: 'Midjourney', tpl: 'Side-by-side comparison thumbnail: {alternativa_barata} on the left, {producto} premium on the right, dramatic lighting difference, high contrast, mobile-first composition --ar 9:16' },
  { k: 'Estático Meta', tool: 'Midjourney + Canva', tpl: 'Bold minimal advertisement graphic, split layout: {antes} labeled left, {despues} labeled right, {color_claro} background, dark typography, modern serif font, premium aesthetic --ar 1:1' },
];

// Estructura de lanzamiento (Fase 12)
const LAUNCH_PLAN = {
  semanas: [
    { t: 'Semana 0 — Pre-lanzamiento', items: ['Comprar dominio + registrar handles', 'Pedir 2 muestras (proveedores distintos)', 'Grabar 10 clips reales + banco IA', 'Producir batch de 12-24 ads', 'Tienda + pixels + CAPI + flows', 'Sembrar 20-30 reviews reales', '2 semanas de orgánico ANTES del paid (3 posts/día)'] },
    { t: 'Semanas 1-2 — Testing (ABO)', items: ['3-4 ad sets de $10-15/día, optimización Purchase desde día 1', 'Broad + 1 interés + Advantage+', 'Revisar kill rules 1 vez al día (no cada hora)', 'TikTok: 1 campaña, 2 ad groups broad'] },
    { t: 'Semanas 3-4 — Consolidación', items: ['Duplicar ganadores a 2× (nunca editar el original)', '+20-30% cada 48h si mantiene ROAS', 'Producir variantes SOLO del formato ganador', 'CBO cuando haya 3+ ads ganadores y 30+ compras'] },
  ],
  hitos30: [
    { cond: 'ROAS blended ≥ 1.25× tu break-even y CR ≥ 2%', accion: 'ESCALAR: sube a $150-300/día, packaging custom, negocia COGS' },
    { cond: 'ROAS entre break-even y 1.25× break-even', accion: 'ITERAR: nuevo batch del formato líder + test de precio/oferta' },
    { cond: 'ROAS < break-even tras 2 iteraciones de creativo y landing', accion: 'MATAR producto y pasar al candidato #2 del ranking. Las pérdidas se cortan, no se negocian.' },
  ],
};

// Oportunidades tipo (Fase 4) — el patrón de huecos que el operador busca siempre
const OPPORTUNITY_PATTERNS = [
  '¿Nadie tiene MARCA real? (nombres genéricos, packaging marrón) → sé la marca de la categoría',
  '¿Todos venden el aparato y nadie el RITUAL/emoción? → vende la transformación',
  '¿Existe consumible/recurrencia que nadie explota? → ecosistema de LTV',
  '¿Nadie hace paid social serio? (Ad Library vacía de players agresivos) → llega primero',
  '¿Hay un ángulo emocional virgen? (miedo, regalo, identidad) → hazlo tuyo',
  '¿Garantías tibias en todos? (30 días) → garantía agresiva como foso',
  '¿Unboxing/packaging descuidado en toda la categoría? → UGC gratis con packaging premium',
];

// ============================================================
// System prompt del Analista IA — la metodología destilada
// ============================================================
const AI_SYSTEM = `Eres DROP-META, un operador experto en dropshipping, marketing, branding, copywriting, análisis de datos, Meta Ads, TikTok Ads, CRO y Shopify. Analizas con la metodología de 13 fases:

REGLAS DE ANÁLISIS:
- Scoring de productos: pesos = Tendencia 15%, Competencia 15% (más alto = menos saturado; 15-80 ads activos en Meta Ad Library sin marca DTC dominante = sweet spot), Viralidad 10%, Creativo 10%, CPM 7%, CTR 8%, CPC 5%, Conversión 10%, AOV 7%, Upsells 5%, Cross-sells 3%, Marca 5%.
- Filtro de entrada: contenido orgánico probado, poca saturación, margen ≥70%, impulso, $30-120, sin educación compleja, envío sencillo, legal limpio, alto UGC.
- Economía: break-even ROAS = precio / (precio - COGS - envío - fees). Objetivo de escalado = 1.4× el break-even mínimo 2.0. AOV se empuja con bundles y consumibles.
- Kill rules: gasto ≥ 1×AOV sin compra = matar ad. CTR <0.8% con $20 = hook muerto (cambiar solo los primeros 3s). CTR sano pero CR <1.5% = problema de LANDING no de ads. ATC alto pero compra baja = problema de CHECKOUT/precio.
- Sé honesto y directo: distingue SIEMPRE entre datos verificados y estimaciones. Si una economía no cuadra (ej. margen <50% con ads), dilo sin suavizar. Las pérdidas se cortan, no se negocian.
- Riesgo publicitario: claims de salud/belleza = CPM castigado y cuentas en riesgo. Productos sin claims corren limpios.
- Marca > commodity: el foso es branding + garantía + bundle + consumibles, nunca el precio.

Responde en español, conciso y accionable. Cuando el usuario te pase datos de su proyecto, úsalos. Formato: texto plano estructurado con guiones y números, sin markdown pesado.`;

// ============================================================
// Plantilla de landing page (Fase 10) — genérica con variables
// ============================================================
function landingTemplate(p) {
  const b = p.brand, e = p.economics;
  const precio = (e.price || 59.95).toFixed(2), ancla = (e.anchor || e.price * 1.5 || 89.95).toFixed(2);
  const off = Math.round((1 - precio / ancla) * 100);
  const c = b.colors;
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${b.name || 'MI MARCA'} — ${b.slogan || 'Tagline'}</title>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{--primary:${c.primary};--dark:${c.dark};--light:${c.light};--accent:${c.accent};--cta:${c.cta};--muted:#7A6F63}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',sans-serif;color:#241F1B;background:var(--light);line-height:1.6}
h1,h2,h3{font-family:'Fraunces',serif;font-weight:600;line-height:1.15}
.wrap{max-width:1080px;margin:0 auto;padding:0 20px}
.btn{display:inline-block;background:var(--cta);color:#fff;font-weight:600;font-size:17px;padding:16px 36px;border-radius:999px;text-decoration:none;box-shadow:0 6px 24px rgba(0,0,0,.25)}
.btn-sub{display:block;font-size:12px;font-weight:400;opacity:.85;margin-top:3px}
.eyebrow{letter-spacing:.18em;text-transform:uppercase;font-size:12px;font-weight:600;color:var(--cta)}
section{padding:72px 0}.sub{color:var(--muted);text-align:center;max-width:60ch;margin:0 auto 44px}
.announce{background:var(--dark);color:var(--light);text-align:center;font-size:13px;padding:9px}
.announce b{color:var(--primary)}
.hero{background:var(--dark);color:var(--light);padding:64px 0 80px}
.hero .wrap{display:grid;grid-template-columns:1.05fr .95fr;gap:48px;align-items:center}
.hero h1{font-size:clamp(34px,4.6vw,54px);margin:14px 0 18px}
.hero h1 em{font-style:normal;color:var(--primary)}
.hero p{font-size:18px;opacity:.85;margin-bottom:26px}
.hero-img{border-radius:20px;background:rgba(0,0,0,.3);aspect-ratio:4/5;display:flex;align-items:center;justify-content:center;opacity:.7;font-size:13px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:24px}
.card{background:#fff;border-radius:18px;padding:30px 26px;box-shadow:0 4px 20px rgba(0,0,0,.06)}
.card h3{font-size:19px;margin-bottom:8px}.card p{font-size:14.5px;color:var(--muted)}
h2.center{font-size:clamp(28px,3.6vw,40px);text-align:center;margin-bottom:12px}
.offer-box{display:grid;grid-template-columns:1fr 1fr;gap:40px;align-items:center;background:#fff;border-radius:24px;padding:44px;box-shadow:0 20px 60px rgba(0,0,0,.12)}
.price{display:flex;align-items:baseline;gap:14px;margin:16px 0}
.price .now{font-family:'Fraunces',serif;font-size:44px}
.price .was{font-size:20px;color:var(--muted);text-decoration:line-through}
.price .off{background:var(--primary);color:var(--dark);font-size:12px;font-weight:700;padding:4px 10px;border-radius:999px}
.review{background:#fff;border-radius:16px;padding:24px;font-size:14.5px;box-shadow:0 4px 20px rgba(0,0,0,.06)}
.stars{color:var(--primary);letter-spacing:2px}
details{background:#fff;border-radius:14px;margin-bottom:12px}
summary{padding:20px 24px;font-weight:600;cursor:pointer;font-size:16px}
details .a{padding:0 24px 20px;color:var(--muted);font-size:14.5px}
.final{background:var(--dark);color:var(--light);text-align:center;padding:90px 0}
.final h2{font-size:clamp(30px,4vw,46px);margin-bottom:14px}.final h2 em{font-style:normal;color:var(--primary)}
.sticky{position:fixed;bottom:0;left:0;right:0;background:rgba(20,17,14,.97);color:#fff;display:flex;align-items:center;justify-content:space-between;padding:12px 20px;transform:translateY(110%);transition:transform .3s;z-index:99}
.sticky.show{transform:translateY(0)}
.sticky .sp{font-family:'Fraunces',serif;font-size:20px;color:var(--primary)}
footer{background:var(--dark);color:var(--muted);text-align:center;font-size:12px;padding:28px 20px}
@media(max-width:860px){.hero .wrap,.offer-box{grid-template-columns:1fr}.grid3{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="announce">✨ Launch offer — <b>${off}% OFF + Free Shipping</b> ends Sunday</div>
<header class="hero"><div class="wrap">
  <div>
    <span class="eyebrow">${p.producto || 'Tu producto'}</span>
    <h1>${p.avatar.transDe ? 'From “' + p.avatar.transDe + '”' : 'Your headline'} <em>${p.avatar.transA ? 'to “' + p.avatar.transA + '”' : 'with emphasis.'}</em></h1>
    <p>${(p.avatar.beneficios[0] || 'Beneficio principal aquí')}. ${(p.avatar.beneficios[1] || '')}</p>
    <a class="btn" href="#offer">Get ${b.name || 'it'} — $${precio}<span class="btn-sub">Free shipping · Guarantee included</span></a>
  </div>
  <div class="hero-img">[HERO IMAGE 4:5]</div>
</div></header>
<section><div class="wrap">
  <h2 class="center">Why it works</h2>
  <p class="sub">${b.slogan || ''}</p>
  <div class="grid3">
    ${(p.avatar.beneficios.slice(0, 6).map(x => `<div class="card"><h3>${x.split(':')[0] || x}</h3><p>${x.split(':')[1] || ''}</p></div>`).join('\n    ')) || '<div class="card"><h3>Beneficio 1</h3><p>Completa el avatar en Drop-Meta.</p></div>'}
  </div>
</div></section>
<section id="offer" style="background:#fff"><div class="wrap">
  <h2 class="center">Get yours</h2><p class="sub">Launch offer — this week only.</p>
  <div class="offer-box">
    <div class="hero-img" style="aspect-ratio:1">[PRODUCT + BOX]</div>
    <div>
      <span class="stars">★★★★★</span>
      <div class="price"><span class="now">$${precio}</span><span class="was">$${ancla}</span><span class="off">SAVE ${off}%</span></div>
      <a class="btn" href="#">Add to Cart — $${precio}<span class="btn-sub">Guarantee · Free shipping</span></a>
    </div>
  </div>
</div></section>
<section><div class="wrap">
  <h2 class="center">Real customers</h2><p class="sub">Seed these with real sample reviews before launch.</p>
  <div class="grid3">
    <div class="review"><span class="stars">★★★★★</span><p>"[Review real de muestra 1]"</p></div>
    <div class="review"><span class="stars">★★★★★</span><p>"[Review real de muestra 2]"</p></div>
    <div class="review"><span class="stars">★★★★★</span><p>"[Review real de muestra 3]"</p></div>
  </div>
</div></section>
<section style="background:#fff"><div class="wrap" style="max-width:760px">
  <h2 class="center">Questions, answered</h2><p class="sub">Cada FAQ mata una objeción del avatar.</p>
  ${(p.avatar.objeciones.slice(0, 6).map(o => `<details><summary>${o.o}</summary><div class="a">${o.r}</div></details>`).join('\n  ')) || '<details><summary>Objeción</summary><div class="a">Respuesta</div></details>'}
</div></section>
<section class="final"><div class="wrap">
  <h2>Tonight could feel <em>different.</em></h2>
  <p style="opacity:.8;margin-bottom:30px">${b.slogan || ''}</p>
  <a class="btn" href="#offer">${b.slogan || 'Get yours'} — $${precio}</a>
</div></section>
<footer>© ${new Date().getFullYear()} ${b.name || ''} · ${b.domain || ''}</footer>
<div class="sticky" id="sticky"><div><span class="sp">$${precio}</span> <s style="opacity:.5;font-size:13px">$${ancla}</s></div><a class="btn" style="font-size:14px;padding:12px 28px" href="#offer">Add to Cart</a></div>
<script>
const st=document.getElementById('sticky'),h=document.querySelector('.hero');
window.addEventListener('scroll',()=>st.classList.toggle('show',window.scrollY>h.offsetHeight));
</script>
</body></html>`;
}
