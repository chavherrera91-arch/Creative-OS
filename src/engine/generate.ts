import type {
  AbTestPlan,
  AdCreative,
  Campaign,
  CreativeScore,
  HookGroup,
  Intelligence,
  LandingCopy,
  LibraryLink,
  Offer,
  PlannerWeek,
  ProductInput,
  PromptGroup,
  Scene,
  Script,
  SourceType,
  ThumbnailConcept,
  UgcCreator,
  ViralPrediction,
  VisualSet,
} from "../types";
import { CategoryKB, detectCategory, getCategory } from "./data";

// ---------- RNG con semilla (mismo producto => misma campaña, editable) ----------
function makeRng(seed: string) {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return () => {
    h ^= h << 13;
    h ^= h >>> 17;
    h ^= h << 5;
    return ((h >>> 0) % 100000) / 100000;
  };
}

type Rng = () => number;
const pick = <T,>(rng: Rng, arr: T[]): T => arr[Math.floor(rng() * arr.length)];
const sample = <T,>(rng: Rng, arr: T[], n: number): T[] => {
  const copy = [...arr];
  const out: T[] = [];
  while (out.length < n && copy.length) {
    out.push(copy.splice(Math.floor(rng() * copy.length), 1)[0]);
  }
  return out;
};
const int = (rng: Rng, min: number, max: number) => Math.floor(rng() * (max - min + 1)) + min;

// ---------- Análisis de URL de origen ----------
export function detectSourceType(url: string): SourceType {
  const u = url.toLowerCase();
  if (!u) return "manual";
  if (u.includes("aliexpress")) return "aliexpress";
  if (u.includes("amazon") || u.includes("amzn.")) return "amazon";
  if (u.includes("tiktok")) return "tiktok";
  if (u.includes("myshopify") || u.includes("shopify")) return "shopify";
  if (u.startsWith("http")) return "tienda";
  return "manual";
}

// Extrae un nombre probable de producto del slug de la URL
export function guessNameFromUrl(url: string): string {
  try {
    const u = new URL(url);
    const segs = u.pathname.split("/").filter(Boolean);
    let slug =
      segs.find((s) => s.length > 12 && s.includes("-")) ||
      segs.sort((a, b) => b.length - a.length)[0] ||
      "";
    slug = slug
      .replace(/\.html?$/i, "")
      .replace(/\d{6,}/g, "")
      .replace(/[-_+]/g, " ")
      .replace(/\b(dp|item|products?|product|detail|itm|ref|gp)\b/gi, "")
      .replace(/\s+/g, " ")
      .trim();
    if (slug.length < 4) return "";
    return slug
      .split(" ")
      .map((w) => (w.length > 2 ? w[0].toUpperCase() + w.slice(1) : w))
      .join(" ");
  } catch {
    return "";
  }
}

const SOURCE_LABEL: Record<SourceType, string> = {
  aliexpress: "AliExpress",
  amazon: "Amazon",
  shopify: "Shopify",
  tiktok: "TikTok",
  tienda: "Tienda online",
  imagen: "Imagen",
  manual: "Manual",
};
export { SOURCE_LABEL };

// ---------- Generador principal ----------
// Nombre corto para insertar en hooks y guiones: los listings traen títulos
// kilométricos ("X Multifuncional 14 en 1 Acero Inoxidable...") que arruinan el copy.
export function shortName(full: string): string {
  const stop = new Set(["de", "en", "el", "la", "los", "las", "y", "con", "para", "por", "a", "x", "the", "of", "for", "with", "and", "in"]);
  let words = full.trim().split(/\s+/).slice(0, 4);
  // recortar conectores y números sueltos al final
  while (words.length > 2 && (stop.has(words[words.length - 1].toLowerCase()) || /^[\d.,]+$/.test(words[words.length - 1]))) {
    words = words.slice(0, -1);
  }
  return words.join(" ");
}

export function generateCampaign(input: ProductInput): Campaign {
  const cat = input.categoryId ? getCategory(input.categoryId) : detectCategory(input.name + " " + input.description + " " + input.sourceUrl);
  const rng = makeRng(input.name + input.sourceUrl);
  const fullName = input.name.trim() || "este producto";
  const p = shortName(fullName) || "este producto";

  const intelligence = genIntelligence(rng, cat, p, input);
  const score = genScore(rng, cat, p);
  const hooks = genHooks(rng, cat, p, intelligence);
  const scripts = genScripts(rng, cat, p, intelligence);
  const ads = genAds(rng, cat, p, intelligence, hooks);
  const visualSets = genVisualSets(rng, cat, p, intelligence);
  const imagePrompts = genImagePrompts(rng, cat, p);
  const videoPrompts = genVideoPrompts(rng, cat, p);
  const ugc = genUgc(rng, cat, p, intelligence);
  const landing = genLanding(rng, cat, p, intelligence);
  const offers = genOffers(rng, cat, p, intelligence);
  const planner = genPlanner(rng, cat, p);
  const viral = genViral(rng, cat, p, score);
  const abTests = genAbTests(rng, cat, p, hooks, intelligence);
  const thumbnails = genThumbnails(rng, cat, p, intelligence);
  const library = genLibrary(p, cat);

  return {
    id: `cmp_${Date.now().toString(36)}_${Math.floor(Math.random() * 1e6).toString(36)}`,
    createdAt: Date.now(),
    generatedBy: "local",
    input: { ...input, categoryId: cat.id },
    intelligence,
    score,
    hooks,
    ads,
    scripts,
    visualSets,
    imagePrompts,
    videoPrompts,
    ugc,
    library,
    thumbnails,
    landing,
    offers,
    planner,
    viral,
    abTests,
    competitor: null,
    iteration: null,
  };
}

// ---------- 1. Product Intelligence ----------
function genIntelligence(rng: Rng, cat: CategoryKB, p: string, input: ProductInput): Intelligence {
  const [lo, hi] = cat.priceBand;
  const rec = Math.round((lo + (hi - lo) * 0.55) / 5) * 5 - 0.05;
  const emotions = ["Deseo", "Alivio", "Curiosidad", "Estatus", "Miedo a perder", "Pertenencia"];

  const angles = [
    {
      name: "Solución al problema",
      emotion: "Alivio",
      description: `Mostrar el problema (“${cat.problem.split("—")[0].split(",")[0].toLowerCase()}”) en su peor momento y presentar ${p} como el corte definitivo.`,
      bigIdea: `“Deja de sufrir lo que ya tiene solución.”`,
    },
    {
      name: "Descubrimiento / secreto",
      emotion: "Curiosidad",
      description: `Posicionar ${p} como el hallazgo que pocos conocen todavía. El espectador siente que llegó antes que el resto.`,
      bigIdea: `“El que lo encontró primero, no lo cuenta.”`,
    },
    {
      name: "Antes vs. Después",
      emotion: "Deseo",
      description: `El contraste visual hace todo el trabajo: la vida antes de ${p} vs. la vida después. Sin argumentos, solo evidencia.`,
      bigIdea: `“No te lo contamos. Te lo mostramos.”`,
    },
    {
      name: "Ahorro inteligente",
      emotion: "Estatus",
      description: `Comparar el coste de la alternativa tradicional (servicio, marca cara, tiempo perdido) con el precio único de ${p}.`,
      bigIdea: `“Pagar de más no te hace premium. Te hace cliente.”`,
    },
    {
      name: "Prueba social masiva",
      emotion: "Pertenencia",
      description: `Reseñas, cifras de ventas y UGC real. Si tanta gente lo usa y lo repite, el riesgo percibido desaparece.`,
      bigIdea: `“No lo decimos nosotros. Lo dicen miles.”`,
    },
    {
      name: "Urgencia de temporada",
      emotion: "Miedo a perder",
      description: `Vincular ${p} al momento del año o tendencia actual: el coste de esperar es perder la ventana.`,
      bigIdea: `“El mejor momento fue ayer. El segundo mejor es ahora.”`,
    },
  ];

  const objections = [
    { objection: "«Seguro que es de mala calidad, como todo lo barato»", response: `Mostrar pruebas en cámara: materiales, resistencia, uso real. Añadir garantía de devolución de 30 días sin preguntas — el riesgo lo asumes tú, no el cliente.` },
    { objection: "«¿Y si no funciona para mi caso?»", response: `Contenido segmentado por tipo de usuario (${cat.audiences.map((a) => a.name.toLowerCase()).join(", ")}). Cada audiencia debe verse a sí misma usándolo.` },
    { objection: "«Puedo encontrarlo más barato en AliExpress»", response: `Diferénciate con envío rápido local, garantía real, soporte en español y bundle de regalo. Vendes certeza, no solo el objeto.` },
    { objection: "«No lo necesito ahora mismo»", response: `Cuantificar el coste de esperar: cada semana sin ${p} son horas/dinero perdidos. Ofertas con caducidad real refuerzan la decisión.` },
    { objection: "«No confío en tiendas que no conozco»", response: `Reviews con foto y vídeo, contador de pedidos, políticas visibles, checkout con pasarelas reconocidas y presencia activa en redes.` },
    { objection: "«El envío tardará semanas»", response: `Comunicar tiempos reales arriba del fold, con tracking incluido. Si usas fulfillment local, conviértelo en argumento central de venta.` },
  ];

  return {
    problem: `${cat.problem}. ${p} ataca ese problema de frente con una solución visual, demostrable y de precio accesible.`,
    secondaryProblems: sample(rng, cat.secondaryProblems, Math.min(4, cat.secondaryProblems.length)),
    benefits: sample(rng, cat.benefits, Math.min(7, cat.benefits.length)),
    audiences: cat.audiences,
    angles: sample(rng, angles, 6).map((a, i) => ({ ...a, emotion: a.emotion || emotions[i % emotions.length] })),
    objections: sample(rng, objections, 6),
    differentiators: [
      `Demostrabilidad: el efecto de ${p} se puede enseñar en cámara en menos de 5 segundos — oro puro para ads`,
      `Momento de mercado: la categoría "${cat.name.toLowerCase()}" tiene demanda constante y búsquedas activas`,
      `Margen: coste estimado bajo frente a un precio de venta percibido como "chollo" — espacio para ads agresivos`,
      `Ángulos múltiples: sirve para ${cat.audiences.length} audiencias distintas sin cambiar el producto, solo el creativo`,
      `Regalabilidad: funciona como compra personal y como regalo, duplicando las temporadas de venta`,
    ],
    pricing: {
      recommended: `$${rec.toFixed(2)} USD`,
      range: `$${lo}–$${hi} USD según posicionamiento`,
      strategy: `Precio ancla: mostrar precio "normal" de $${Math.round(hi * 1.6)} tachado. Precio de oferta $${rec.toFixed(2)}. Bundle x2 con 30% de descuento en la segunda unidad para subir el AOV. Envío gratis a partir del bundle.`,
      marginNote: `Con coste típico de producto+envío en esta categoría, apunta a un margen bruto ≥ 65% para sostener CPAs de test. Si el margen baja de 55%, sube precio o añade bundle antes de escalar.`,
    },
    scaling: {
      level: cat.saturation <= 2 ? "Muy alto" : cat.saturation === 3 ? "Alto" : "Medio",
      reasoning:
        cat.saturation >= 4
          ? `La categoría está saturada (${cat.saturation}/5), pero eso confirma demanda. Escala con ángulos nuevos y UGC nativo, no con los mismos creativos que todos usan. La diferenciación estará en el creativo, no en el producto.`
          : `Saturación moderada-baja (${cat.saturation}/5) con demanda demostrada: hay espacio para posicionarse antes de que la competencia gruesa llegue. Escala rápido mientras el CPM lo permita.`,
      channels: ["TikTok Ads (test inicial)", "Meta Ads (escalado)", "TikTok orgánico + afiliados", "YouTube Shorts", "Influencers micro (UGC seeding)", "Google Shopping (captura de demanda)"],
    },
  };
}

// ---------- 2. Creative Score ----------
function genScore(rng: Rng, cat: CategoryKB, p: string): CreativeScore {
  const contentIdeas = Math.min(5, Math.max(3, cat.visualAppeal));
  const viralPotential = Math.min(5, Math.round((cat.visualAppeal + cat.ugcFit + (5 - cat.saturation) + cat.explainability) / 4) + (rng() > 0.5 ? 1 : 0));
  const metrics = [
    { label: "Contenido posible", stars: contentIdeas, note: `La categoría permite ${contentIdeas >= 5 ? "docenas de" : "varios"} formatos: demo, antes/después, UGC, comparación y ASMR.` },
    { label: "Potencial viral", stars: Math.min(5, viralPotential), note: viralPotential >= 4 ? "El momento 'wow' es claro y cabe en los primeros 3 segundos." : "Necesita un hook fuerte: el efecto no es obvio de inmediato." },
    { label: "Saturación", stars: cat.saturation, note: cat.saturation >= 4 ? "Mucha competencia activa: diferénciate por creativo y oferta." : "Competencia moderada: ventana de oportunidad abierta." },
    { label: "Facilidad de explicar", stars: cat.explainability, note: cat.explainability >= 4 ? "Se entiende sin narración: la demo lo dice todo." : "Requiere 1-2 frases de contexto antes de la demo." },
    { label: "Visualmente atractivo", stars: cat.visualAppeal, note: cat.visualAppeal >= 4 ? "El resultado en cámara es satisfactorio de ver y repetible." : "Apóyate en reacciones humanas más que en el producto." },
    { label: "UGC potencial", stars: cat.ugcFit, note: cat.ugcFit >= 4 ? "Perfecto para creators: encaja en rutinas y vlogs sin parecer anuncio." : "El UGC necesitará guion: no fluye solo." },
  ];
  // Puntuación: pondera lo bueno, penaliza saturación
  const positive = contentIdeas + viralPotential + cat.explainability + cat.visualAppeal + cat.ugcFit; // máx 25
  const raw = (positive / 25) * 80 + ((5 - cat.saturation) / 5) * 20;
  const total = Math.max(35, Math.min(98, Math.round(raw + int(rng, -2, 3))));

  const meta = Math.min(10, Math.round((cat.explainability + cat.visualAppeal) * 0.9 + (5 - cat.saturation) * 0.2 + 1));
  const tiktok = Math.min(10, Math.round((viralPotential + cat.ugcFit) * 0.95 + 0.5));
  const platforms = [
    { name: "TikTok", score: tiktok, note: tiktok >= 8 ? "Prioridad #1: formato nativo, demo rápida y UGC." : "Viable con hooks agresivos en el primer segundo." },
    { name: "Meta Ads", score: meta, note: meta >= 8 ? "Escalable: funciona en frío con antes/después y prueba social." : "Mejor para retargeting que para frío." },
    { name: "YouTube Shorts", score: Math.max(5, Math.min(10, tiktok - 1)), note: "Recicla los mejores TikToks; audiencia algo mayor, más orientada a utilidad." },
    { name: "Pinterest", score: cat.visualAppeal >= 4 ? 7 : 5, note: cat.visualAppeal >= 4 ? "Buen canal secundario si el producto es estético." : "Canal menor para esta categoría." },
  ];

  const verdict =
    total >= 85
      ? `${p} es un candidato excelente: demanda probada, demo visual y múltiples ángulos. Entra agresivo con UGC en TikTok y escala ganadores en Meta.`
      : total >= 70
        ? `${p} tiene potencial sólido. La clave será diferenciarse por creativo: ejecuta los 3 ángulos principales y mata rápido lo que no funcione.`
        : `${p} es viable pero exigente: necesitará hooks muy fuertes y una oferta agresiva para despegar. Testea barato antes de comprometer presupuesto.`;

  return { total, verdict, metrics, platforms };
}

// ---------- 3. Hooks ----------
function genHooks(rng: Rng, cat: CategoryKB, p: string, intel: Intelligence): HookGroup[] {
  const desire = () => pick(rng, cat.desires);
  const fear = () => pick(rng, cat.fears);
  const aud = () => pick(rng, cat.audiences).name.toLowerCase();
  const pain = () => pick(rng, cat.audiences.flatMap((a) => a.pains));
  const benefit = () => pick(rng, intel.benefits).toLowerCase();
  const days = () => int(rng, 7, 30);
  const price = () => int(rng, 80, 300);

  const groups: { category: string; emoji: string; templates: (() => string)[] }[] = [
    {
      category: "Curiosidad",
      emoji: "🔍",
      templates: [
        () => `No sabía que necesitaba ${p} hasta que vi esto…`,
        () => `El 90% de la gente usa mal esto todos los días (y no lo sabe)`,
        () => `¿Por qué nadie habla de ${p}?`,
        () => `Encontré la solución a "${pain()}" — y no es lo que esperaba`,
        () => `Esto es lo que pasa cuando usas ${p} durante ${days()} días`,
        () => `Hay una razón por la que ${aud()} está comprando esto en silencio`,
        () => `Lo que descubrí después de ${days()} días con ${p} me cambió la rutina`,
        () => `Nadie me avisó de esto antes de comprar ${p}…`,
        () => `El detalle de ${p} que nadie te muestra en los anuncios`,
        () => `Prometí no contarlo, pero ${p} es demasiado bueno para callarlo`,
      ],
    },
    {
      category: "Miedo",
      emoji: "⚠️",
      templates: [
        () => `El miedo a ${fear()} se acaba hoy`,
        () => `Estás perdiendo dinero cada día que no resuelves esto`,
        () => `La forma en que lo haces ahora te está costando más de lo que crees`,
        () => `Deja de ${pain().toLowerCase()} antes de que sea demasiado tarde`,
        () => `Esto es lo que nadie te dice sobre ${fear()}`,
        () => `Cuidado: si te pasa esto, lo estás haciendo mal`,
        () => `El error silencioso que comete todo ${aud()} — y cómo evitarlo`,
        () => `Yo también pensaba que no me hacía falta. Me equivoqué.`,
        () => `Lo barato sale caro… excepto cuando es esto`,
        () => `No compres ${p} sin ver esto primero`,
      ],
    },
    {
      category: "Dolor",
      emoji: "💢",
      templates: [
        () => `¿Cansado de ${pain().toLowerCase()}? Mira esto`,
        () => `Llevaba años sufriendo ${pain().toLowerCase()}. Se acabó.`,
        () => `Nadie debería seguir aguantando ${pain().toLowerCase()} en 2026`,
        () => `POV: otra vez ${pain().toLowerCase()}… hasta hoy`,
        () => `Si ${pain().toLowerCase()} es tu día a día, esto te va a cambiar la semana`,
        () => `Lo que más odiaba de mi rutina ya no existe gracias a ${p}`,
        () => `Este era mi momento más frustrante del día. Ya no.`,
        () => `Duele más seguir igual que probar algo nuevo`,
        () => `Mi ${pain().toLowerCase()} tenía solución de $${cat.priceBand[0]} y no lo sabía`,
      ],
    },
    {
      category: "Humor",
      emoji: "😂",
      templates: [
        () => `Yo explicándole a mi pareja por qué NECESITO ${p} 😅`,
        () => `Mi cuenta bancaria: 💀 | Yo comprando ${p}: 🛒✨`,
        () => `Nadie: … | Yo a las 3am viendo ${p} en TikTok: AÑADIR AL CARRITO`,
        () => `Mi ${aud()} interior cuando descubre ${p}:`,
        () => `Le dije que era para toda la familia. Es solo para mí. 🤫`,
        () => `Fase 1: "qué tontería" → Fase 2: "bueno, uno" → Fase 3: [este video]`,
        () => `Instrucciones: úsalo. Yo: llorando de felicidad por algo de $${cat.priceBand[0]}`,
        () => `El vendedor de ${p} viendo cómo vuelvo por tercera vez:`,
        () => `POV: eres ${p} y me has arruinado el "yo no compro cosas de TikTok"`,
      ],
    },
    {
      category: "Storytelling",
      emoji: "📖",
      templates: [
        () => `Hace ${days()} días mi rutina era un caos. Esta es la historia de cómo cambió.`,
        () => `Mi ${pick(rng, ["madre", "pareja", "mejor amiga", "compañero de piso"])} se rió cuando compré ${p}. Ahora quiere uno.`,
        () => `Casi devuelvo ${p} el primer día. Menos mal que no lo hice.`,
        () => `Compré ${p} por impulso a las 2am. Fue la mejor mala decisión del año.`,
        () => `Primero lo vi en TikTok. Luego en casa de una amiga. Luego entendí por qué.`,
        () => `Tres productos fallidos después, encontré el que sí funciona`,
        () => `El día que dejé de ${pain().toLowerCase()} empezó con un paquete en la puerta`,
        () => `No soy de comprar online. Esta fue la excepción que valió la pena.`,
        () => `De escéptica total a recomendárselo a todo mi grupo. Así fue.`,
      ],
    },
    {
      category: "ASMR",
      emoji: "🎧",
      templates: [
        () => `El sonido de ${p} funcionando es lo más satisfactorio que verás hoy 🎧`,
        () => `Sube el volumen. Gracias después. 🔊`,
        () => `ASMR de ${p} — sin hablar, solo el proceso completo`,
        () => `Este video no necesita palabras. Solo mira (y escucha).`,
        () => `Textura + sonido + resultado. Los 3 en 15 segundos.`,
        () => `El unboxing más satisfactorio de la semana`,
        () => `Si te relaja verlo, imagina usarlo todos los días`,
        () => `Oddly satisfying: edición ${p}`,
      ],
    },
    {
      category: "Comparación",
      emoji: "⚖️",
      templates: [
        () => `${p} de $${cat.priceBand[0]} vs. la alternativa de $${price()}. Mira la diferencia.`,
        () => `Probé el método tradicional y ${p} el mismo día. No hay color.`,
        () => `Lo caro vs. lo viral: hice la prueba para que tú no gastes`,
        () => `Lado a lado: lo que usaba antes vs. ${p}`,
        () => `Mismo resultado, 10 veces menos precio. Te muestro cómo.`,
        () => `${p} barato vs. caro: la diferencia real que nadie te enseña`,
        () => `Hice la comparación que todos piden y el resultado me sorprendió hasta a mí`,
        () => `Marca famosa vs. ${p}: test a ciegas`,
      ],
    },
    {
      category: "Error común",
      emoji: "🚫",
      templates: [
        () => `Llevas toda la vida haciendo esto mal (yo también lo hacía)`,
        () => `El error #1 que comete todo ${aud()} — corrígelo hoy`,
        () => `Deja de gastar en ${pick(rng, ["soluciones a medias", "lo de siempre", "parches temporales"])}: esto es lo que funciona`,
        () => `3 errores que cometes cada día sin saberlo (el 2º es el peor)`,
        () => `Si lo guardas así, lo estás arruinando. Haz esto.`,
        () => `Pensaba que lo hacía bien. Este video me demostró lo contrario.`,
        () => `No es que no funcione. Es que lo estás usando mal.`,
        () => `El mito sobre ${cat.name.toLowerCase()} que te está costando dinero`,
      ],
    },
    {
      category: "Antes vs Después",
      emoji: "🔄",
      templates: [
        () => `Antes de ${p} vs. después. Mismo espacio, misma persona, otra vida.`,
        () => `Día 1 vs. día ${days()}. Los resultados hablan solos.`,
        () => `El "después" que no me creía ni yo`,
        () => `Esto era mi antes 😩 → esto es mi ahora ✨`,
        () => `Guardé el "antes" para este momento. Vale la pena verlo.`,
        () => `Sin filtros, sin trucos: antes y después reales con ${p}`,
        () => `10 segundos de antes. 10 segundos de después. Tú decides.`,
        () => `La transformación que hizo a mi familia preguntar qué cambió`,
      ],
    },
    {
      category: "POV",
      emoji: "👀",
      templates: [
        () => `POV: descubres ${p} después de años sufriendo ${pain().toLowerCase()}`,
        () => `POV: eres ${aud()} y encuentras la solución en tu feed a las 2am`,
        () => `POV: te llega el paquete que va a arreglar tu semana`,
        () => `POV: tu ${pick(rng, ["pareja", "madre", "roomie"])} descubre lo que compraste (y ahora lo usa más que tú)`,
        () => `POV: es lunes pero tienes ${p} y ya nada te frustra igual`,
        () => `POV: la versión de ti que ${desire()} ya existe. Le faltaba esto.`,
        () => `POV: vuelves a ver el video que te hizo comprarlo para dar las gracias`,
      ],
    },
    {
      category: "Shock",
      emoji: "🤯",
      templates: [
        () => `NO PUEDE SER que esto cueste menos de $${cat.priceBand[1]}`,
        () => `Espera al segundo 3. En serio.`,
        () => `Pensé que era fake hasta que lo probé en cámara`,
        () => `Esto no debería funcionar tan bien. Pero funciona.`,
        () => `Lo que hace ${p} en 10 segundos no es normal`,
        () => `Grabé esto sin cortes para que nadie diga que es edición`,
        () => `Mi reacción fue exactamente la tuya al final del video`,
        () => `El resultado me dejó sin palabras (y eso que lo vendo)`,
      ],
    },
    {
      category: "Datos",
      emoji: "📊",
      templates: [
        () => `Pierdes ${int(rng, 5, 12)} horas al mes por no automatizar esto`,
        () => `${p} hace en ${int(rng, 5, 30)} segundos lo que antes tomaba ${int(rng, 5, 20)} minutos`,
        () => `Cuesta menos que ${int(rng, 2, 4)} cafés y lo usas todos los días durante años`,
        () => `Haz los números: $${price()} al año en la alternativa vs. $${cat.priceBand[0]} una sola vez`,
        () => `3 datos sobre ${cat.name.toLowerCase()} que cambiarán cómo compras`,
        () => `El costo real de no resolver esto: te lo desgloso en 20 segundos`,
        () => `${int(rng, 60, 90)}% del resultado con el ${int(rng, 5, 15)}% del esfuerzo. Así:`,
      ],
    },
    {
      category: "Estadísticas",
      emoji: "📈",
      templates: [
        () => `+${int(rng, 10, 60)}.000 vendidos este mes. Hay una razón.`,
        () => `${int(rng, 89, 97)}% de compradores lo volvería a comprar. Yo soy uno.`,
        () => `4.${int(rng, 6, 9)} estrellas en ${int(rng, 2, 15)}.000 reseñas no pueden estar equivocadas`,
        () => `1 de cada ${int(rng, 3, 5)} personas que lo prueba, compra otro para regalar`,
        () => `Las búsquedas de "${cat.name.toLowerCase()}" crecieron ${int(rng, 40, 180)}% este año. Esto explica por qué.`,
        () => `Se agota cada ${int(rng, 2, 6)} semanas. Este video es tu aviso.`,
        () => `El ${int(rng, 70, 85)}% abandona el método tradicional después de probar esto`,
      ],
    },
    {
      category: "Testimonio",
      emoji: "🗣️",
      templates: [
        () => `“Es de las mejores compras que he hecho este año” — y lo confirmo en este video`,
        () => `Mi reseña honesta de ${p} después de ${days()} días de uso real`,
        () => `Me lo recomendó mi ${pick(rng, ["hermana", "fisio", "compañera de trabajo", "vecina"])} y ahora entiendo la insistencia`,
        () => `No me pagan por decir esto (ojalá): ${p} vale cada centavo`,
        () => `Lo compré escéptico. Grabo esto convencido.`,
        () => `Reseña sin guion: lo bueno, lo malo y si lo volvería a comprar`,
        () => `Actualización a los ${days()} días: ¿sigue funcionando igual?`,
        () => `Le regalé uno a mi madre. Ahora quiere otro para mi tía. Señal clara.`,
      ],
    },
  ];

  return groups.map((g) => ({
    category: g.category,
    emoji: g.emoji,
    items: g.templates.map((t) => t()),
  }));
}

// ---------- 4. Ads ----------
function genAds(rng: Rng, cat: CategoryKB, p: string, intel: Intelligence, hooks: HookGroup[]): AdCreative[] {
  const allHooks = hooks.flatMap((h) => h.items);
  const h = () => pick(rng, allHooks);
  const b = (i: number) => intel.benefits[i % intel.benefits.length];
  const price = intel.pricing.recommended;

  return [
    {
      format: "Video (demo)", platform: "Meta Ads", title: `Meta · Video demo 15-30s`,
      primaryText: `${h()}\n\n${b(0)}. ${b(1)}.\n\n✅ ${b(2)}\n✅ Garantía de 30 días\n✅ Envío con seguimiento\n\nMás de 10.000 clientes ya lo usan a diario. Hoy con oferta de lanzamiento: ${price}.`,
      headline: `${p} — ${b(0).split(":")[0]}`,
      description: `Oferta por tiempo limitado · Garantía 30 días`,
      cta: "Comprar ahora",
      specs: "Video 1:1 o 4:5 · 15-30s · hook en los 2 primeros segundos · subtítulos siempre",
      notes: "Estructura: problema (0-3s) → demo (3-15s) → prueba social (15-22s) → oferta + CTA (22-30s).",
    },
    {
      format: "Imagen estática", platform: "Meta Ads", title: `Meta · Imagen antes/después`,
      primaryText: `La diferencia está a la vista 👇\n\n${b(0)}.\n\nMiles de personas ya dejaron atrás ${pick(rng, cat.audiences.flatMap((a) => a.pains)).toLowerCase()}. Con garantía de devolución: si no te convence, te devolvemos el dinero.`,
      headline: `El antes y después que lo explica todo`,
      description: `${price} · Envío rápido`,
      cta: "Más información",
      specs: "1080×1080 · split vertical antes/después · texto <20% del área",
      notes: "La imagen debe funcionar sin leer el copy. Testear versión con y sin precio visible.",
    },
    {
      format: "Carrusel", platform: "Meta Ads", title: `Meta · Carrusel de beneficios`,
      primaryText: `5 razones por las que ${p} se está agotando 👉 desliza`,
      headline: `Desliza para ver por qué`,
      description: `Tarjeta 1: hook visual · 2-4: un beneficio por tarjeta · 5: oferta + CTA`,
      cta: "Comprar ahora",
      specs: "5 tarjetas 1080×1080 · texto grande y un beneficio por tarjeta",
      notes: `Tarjetas: 1) "${h()}" 2) ${b(0)} 3) ${b(1)} 4) Prueba social (reseña real) 5) Oferta ${price} + garantía.`,
    },
    {
      format: "Video UGC", platform: "TikTok Ads", title: `TikTok · Spark Ad estilo UGC`,
      primaryText: `${h()} #TikTokMadeMeBuyIt`,
      headline: `(usa el video como creativo nativo)`,
      description: `Video hablado a cámara, luz natural, sin producción visible`,
      cta: "Comprar ahora",
      specs: "9:16 · 15-34s · grabado con móvil · subtítulos nativos de TikTok",
      notes: "Publicar primero como orgánico desde cuenta creadora, luego amplificar como Spark Ad: mantiene likes y comentarios.",
    },
    {
      format: "Video In-Feed", platform: "TikTok Ads", title: `TikTok · In-feed directo`,
      primaryText: `${pick(rng, allHooks)} 🔥 Oferta solo esta semana`,
      headline: `${p}`,
      description: `Demo + oferta con urgencia`,
      cta: "Comprar ahora",
      specs: "9:16 · 9-15s · corte cada 1.5-2s · música trending",
      notes: "Versión corta y agresiva: hook (0-1s), demo x3 ángulos (1-9s), precio+CTA (9-15s). Iterar solo el primer segundo entre variantes.",
    },
    {
      format: "Short", platform: "YouTube Shorts", title: `Shorts · Demo con narración`,
      primaryText: `${h()}`,
      headline: `${p}: demostración real`,
      description: `Narración explicativa con demo, tono más informativo que TikTok`,
      cta: "Ver oferta",
      specs: "9:16 · 20-40s · narración clara · el título del Short es parte del hook",
      notes: "Audiencia de Shorts responde mejor a utilidad ('cómo funciona') que a puro hype. Añadir link en comentario fijado.",
    },
    {
      format: "Reel", platform: "Instagram", title: `IG Reels · Aesthetic + demo`,
      primaryText: `${b(0)} ✨ Link en bio`,
      headline: `${p}`,
      description: `Versión estética del demo: mejor luz, mejor encuadre, música suave`,
      cta: "Comprar ahora",
      specs: "9:16 · 15-30s · estética cuidada · transiciones limpias",
      notes: "En IG la estética vende: mismo guion que TikTok pero con producción más pulida. Portada del Reel = mini thumbnail.",
    },
    {
      format: "VSL", platform: "Landing / YouTube", title: `VSL · Video de venta 2-3 min`,
      primaryText: `Guion completo disponible en Script Generator (duración 3 minutos)`,
      headline: `La historia completa de por qué ${p} funciona`,
      description: `Para tráfico templado: retargeting y landing page`,
      cta: "Comprar con garantía de 30 días",
      specs: "16:9 o 9:16 · 2-3 min · estructura PAS + prueba + oferta + garantía",
      notes: "Usar en la landing sobre el fold y como retargeting a quienes vieron >50% de los videos cortos.",
    },
    {
      format: "GIF", platform: "Meta / Email", title: `GIF · Loop de demo`,
      primaryText: `El momento exacto en que entiendes por qué todos lo compran 👇`,
      headline: `Míralo en acción`,
      description: `Loop de 2-4 segundos del momento wow`,
      cta: "Ver más",
      specs: "1:1 · 2-4s en loop perfecto · sin texto o mínimo",
      notes: `Capturar: ${cat.wowMoment}. Ideal para emails de carrito abandonado y placements de bajo coste.`,
    },
    {
      format: "Banner", platform: "Display / Web", title: `Banner · Display remarketing`,
      primaryText: `¿Todavía pensándolo? Tu ${p} sigue esperando · -30% termina hoy`,
      headline: `Vuelve y llévatelo con descuento`,
      description: `Set de banners para remarketing`,
      cta: "Recuperar mi oferta",
      specs: "300×250, 728×90, 320×50, 160×600 · producto sobre fondo limpio + precio + CTA",
      notes: "Solo para retargeting: en frío los banners de display tienen CTR ínfimo para e-commerce.",
    },
  ];
}

// ---------- 5. Scripts ----------
function genScripts(rng: Rng, cat: CategoryKB, p: string, intel: Intelligence): Script[] {
  const pain = () => pick(rng, cat.audiences.flatMap((a) => a.pains)).toLowerCase();
  const benefit = (i: number) => intel.benefits[i % intel.benefits.length];
  const scripts: Script[] = [];
  const ctas = [
    `Toca el enlace antes de que vuelva a agotarse.`,
    `Está en oferta esta semana — link en el perfil.`,
    `Si llegaste hasta aquí, ya sabes qué hacer. Link abajo.`,
    `Pruébalo 30 días. Si no te convence, te devuelven el dinero.`,
    `El link está abajo. Tu yo del futuro te lo agradece.`,
  ];

  const angleDefs = [
    { angle: "Problema → Solución", hookIdx: "Dolor" },
    { angle: "Antes vs Después", hookIdx: "Antes vs Después" },
    { angle: "Testimonio honesto", hookIdx: "Testimonio" },
    { angle: "Comparación con alternativa cara", hookIdx: "Comparación" },
    { angle: "Descubrimiento viral", hookIdx: "Curiosidad" },
    { angle: "Humor / relatable", hookIdx: "Humor" },
  ];

  const mk = (duration: string, angle: string, title: string, hook: string, beats: { time: string; label: string; voiceover: string; visual: string }[]) => {
    scripts.push({ duration, angle, title, hook, beats, cta: pick(rng, ctas) });
  };

  for (const ad of angleDefs) {
    // 15 segundos
    mk("15s", ad.angle, `${ad.angle} — versión rápida`, hookFor(rng, ad.angle, p, pain, cat), [
      { time: "0-2s", label: "Hook", voiceover: hookFor(rng, ad.angle, p, pain, cat), visual: `Primer plano del problema o del producto en acción. Texto grande en pantalla con el hook.` },
      { time: "2-8s", label: "Demo", voiceover: `Mira esto: ${benefit(0).toLowerCase()}. Así de simple.`, visual: `${cat.demoAction}. Cortes rápidos, 3 ángulos distintos de la misma acción.` },
      { time: "8-12s", label: "Beneficio", voiceover: `${benefit(1)}. Y cuesta menos que ${pick(rng, ["una cena fuera", "dos cafés a la semana", "lo que pierdes cada mes sin él"])}.`, visual: `Resultado final en pantalla + precio superpuesto.` },
      { time: "12-15s", label: "CTA", voiceover: pick(rng, ctas), visual: `Producto + oferta + flecha al botón. Texto: "OFERTA ESTA SEMANA".` },
    ]);

    // 30 segundos
    mk("30s", ad.angle, `${ad.angle} — versión estándar`, hookFor(rng, ad.angle, p, pain, cat), [
      { time: "0-3s", label: "Hook", voiceover: hookFor(rng, ad.angle, p, pain, cat), visual: `Escena del problema en su peor momento. Expresión de frustración real.` },
      { time: "3-8s", label: "Agitación", voiceover: `Todos los días lo mismo: ${pain()}. Y las soluciones de siempre no funcionan.`, visual: `Secuencia rápida de intentos fallidos con el método tradicional.` },
      { time: "8-18s", label: "Solución + Demo", voiceover: `Hasta que probé ${p}. ${benefit(0)}. En serio: ${benefit(1).toLowerCase()}.`, visual: `${cat.demoAction}. El momento wow en el segundo 12: ${cat.wowMoment}.` },
      { time: "18-24s", label: "Prueba social", voiceover: `No soy la única: miles de personas ya lo usan a diario y las reseñas hablan solas.`, visual: `Capturas de reseñas de 5 estrellas + contador de ventas.` },
      { time: "24-30s", label: "Oferta + CTA", voiceover: `Está en ${intel.pricing.recommended} solo esta semana. ${pick(rng, ctas)}`, visual: `Precio tachado vs. oferta + garantía 30 días + botón.` },
    ]);

    // 45 segundos
    mk("45s", ad.angle, `${ad.angle} — versión completa`, hookFor(rng, ad.angle, p, pain, cat), [
      { time: "0-3s", label: "Hook", voiceover: hookFor(rng, ad.angle, p, pain, cat), visual: `Apertura con el momento más impactante del video (spoiler del wow).` },
      { time: "3-10s", label: "Contexto", voiceover: `Te cuento: llevaba meses con ${pain()}. Probé de todo y nada funcionaba de verdad.`, visual: `Persona hablando a cámara en ${cat.environment}, tono cercano.` },
      { time: "10-22s", label: "Demo detallada", voiceover: `Entonces encontré ${p}. Mira cómo funciona: ${benefit(0).toLowerCase()}, y además ${benefit(1).toLowerCase()}.`, visual: `${cat.demoAction} paso a paso, con primer plano del mecanismo/resultado.` },
      { time: "22-32s", label: "Objeción", voiceover: `Sé lo que piensas: "seguro que es como los demás". Yo pensaba igual. Por eso grabé esta prueba sin cortes.`, visual: `Prueba en tiempo real, sin edición, con timer visible en pantalla.` },
      { time: "32-40s", label: "Beneficio emocional", voiceover: `Lo que de verdad cambia es esto: ${pick(rng, cat.desires)}. Eso no tiene precio (aunque este casi ni cuenta).`, visual: `Escena de vida mejorada: la persona disfrutando el resultado.` },
      { time: "40-45s", label: "CTA", voiceover: `${pick(rng, ctas)}`, visual: `Oferta completa: precio, garantía, envío. Botón animado.` },
    ]);

    // 60 segundos
    mk("1 min", ad.angle, `${ad.angle} — historia completa`, hookFor(rng, ad.angle, p, pain, cat), [
      { time: "0-4s", label: "Hook doble", voiceover: `${hookFor(rng, ad.angle, p, pain, cat)} Quédate, porque al final te enseño el resultado sin cortes.`, visual: `Flash del resultado final (1s) + corte a presentador.` },
      { time: "4-14s", label: "Historia", voiceover: `Contexto real: soy ${pick(rng, cat.audiences).name.toLowerCase()} y mi problema era ${pain()}. No es drama: es el día a día de miles de personas.`, visual: `B-roll de la rutina real con el problema visible.` },
      { time: "14-28s", label: "Presentación + Demo", voiceover: `${p} apareció en mi feed y decidí probarlo. Primera sorpresa: ${benefit(0).toLowerCase()}. Segunda: ${benefit(1).toLowerCase()}.`, visual: `Unboxing rápido (3s) + demo principal con 3 tomas.` },
      { time: "28-40s", label: "Prueba extendida", voiceover: `Lo usé ${int(rng, 7, 21)} días seguidos. Esto es lo que cambió — y lo que no. Honestidad ante todo.`, visual: `Montaje de días de uso con fecha en pantalla. Antes/después.` },
      { time: "40-50s", label: "Para quién es", voiceover: `Si eres de los que ${pain()}, esto es para ti. Si no… igual conoces a alguien que lo necesita.`, visual: `Cortes de distintos tipos de usuario usándolo.` },
      { time: "50-60s", label: "Oferta + CTA", voiceover: `Ahora está en ${intel.pricing.recommended} con garantía de 30 días. ${pick(rng, ctas)}`, visual: `Resumen visual de la oferta + botón + urgencia real.` },
    ]);

    // 2 minutos
    mk("2 min", ad.angle, `${ad.angle} — mini VSL`, hookFor(rng, ad.angle, p, pain, cat), [
      { time: "0-5s", label: "Hook + promesa", voiceover: `${hookFor(rng, ad.angle, p, pain, cat)} En los próximos 2 minutos te muestro exactamente cómo — con pruebas.`, visual: `Montaje rápido de los 3 momentos más fuertes del video.` },
      { time: "5-20s", label: "El problema real", voiceover: `Hablemos claro: ${cat.problem.toLowerCase()}. Y cada semana que pasa, el coste sube: tiempo, dinero y paciencia.`, visual: `Escenas del problema en distintos contextos. Cifras en pantalla.` },
      { time: "20-35s", label: "Por qué lo demás falla", voiceover: `Las soluciones típicas fallan por tres razones: son caras, son lentas o simplemente no se sostienen en el tiempo.`, visual: `Los 3 fallos en pantalla con ejemplos visuales de cada uno.` },
      { time: "35-60s", label: "La solución", voiceover: `${p} lo resuelve distinto: ${benefit(0).toLowerCase()}. Además, ${benefit(1).toLowerCase()} y ${benefit(2).toLowerCase()}.`, visual: `Demo completa y detallada. Primeros planos del mecanismo. ${cat.wowMoment}.` },
      { time: "60-80s", label: "Pruebas y testimonios", voiceover: `Pero no me creas a mí. Mira lo que dicen quienes lo compraron hace meses.`, visual: `2-3 clips de testimonios UGC + capturas de reseñas verificadas.` },
      { time: "80-100s", label: "Manejo de objeciones", voiceover: `¿Calidad? Garantía de 30 días. ¿Envío? Con seguimiento. ¿Precio? Menos de lo que gastas en un mes en la alternativa.`, visual: `Cada objeción aparece como pregunta en pantalla y se tacha al responderla.` },
      { time: "100-120s", label: "Cierre + CTA", voiceover: `Puedes seguir como hasta ahora o probarlo con cero riesgo. ${pick(rng, ctas)}`, visual: `Oferta final completa + cuenta atrás + botón grande.` },
    ]);

    // 3 minutos
    mk("3 min", ad.angle, `${ad.angle} — VSL completo`, hookFor(rng, ad.angle, p, pain, cat), [
      { time: "0-8s", label: "Patrón interrumpido", voiceover: `${hookFor(rng, ad.angle, p, pain, cat)} Y no, no es otro producto milagro: te voy a enseñar exactamente cómo funciona y para quién NO es.`, visual: `Apertura directa a cámara, sin música, tono serio y cercano.` },
      { time: "8-30s", label: "Historia personal", voiceover: `Primero, contexto. ${pick(rng, ["Hace un año", "Hace unos meses", "El año pasado"])} yo estaba exactamente donde tú estás: ${pain()}. Había probado ${int(rng, 3, 6)} soluciones distintas. Ninguna duró.`, visual: `B-roll narrativo de la situación previa, tono documental.` },
      { time: "30-55s", label: "El descubrimiento", voiceover: `Todo cambió cuando entendí el problema de raíz: ${pick(rng, cat.secondaryProblems).toLowerCase()}. ${p} está diseñado justo para eso.`, visual: `Explicación con gráficos simples del mecanismo/causa raíz.` },
      { time: "55-90s", label: "Demo profunda", voiceover: `Te lo enseño en directo, paso a paso, sin cortes. Fíjate en tres cosas: velocidad, resultado y lo fácil que es.`, visual: `Demo íntegra en tiempo real. Zoom a los detalles clave. Timer en pantalla.` },
      { time: "90-120s", label: "Resultados de terceros", voiceover: `Estos son resultados de clientes reales — con sus palabras, no las mías. Nota lo que se repite: ${pick(rng, cat.desires)}.`, visual: `3 testimonios en video + reseñas destacadas con nombre y foto.` },
      { time: "120-145s", label: "Para quién es / no es", voiceover: `Sé honesto contigo: si buscas magia sin usar el producto, no es para ti. Si quieres ${pick(rng, cat.desires)} con un método simple, sí lo es.`, visual: `Dos columnas en pantalla: "Es para ti si…" / "No es para ti si…".` },
      { time: "145-165s", label: "Oferta apilada", voiceover: `Esto es todo lo que recibes hoy: ${p}, garantía de 30 días, envío con seguimiento y soporte real. Valor total muy por encima del precio de hoy: ${intel.pricing.recommended}.`, visual: `Stack visual de la oferta, cada elemento aparece con su valor.` },
      { time: "165-180s", label: "Cierre con escasez", voiceover: `El precio vuelve a subir cuando termine la semana. Doble camino: seguir igual, o probarlo sin riesgo. Tú eliges. ${pick(rng, ctas)}`, visual: `Cuenta atrás real + botón + última toma del momento wow.` },
    ]);
  }

  return scripts;
}

function hookFor(rng: Rng, angle: string, p: string, pain: () => string, cat: CategoryKB): string {
  const map: Record<string, string[]> = {
    "Problema → Solución": [`¿Cansado de ${pain()}? Mira esto.`, `Deja de sufrir ${pain()}: existe solución.`, `Esto acaba con ${pain()} en segundos.`],
    "Antes vs Después": [`Antes de ${p} vs. después. Juzga tú.`, `El antes y después que no me creía ni yo.`, `Guardé el "antes" solo para enseñarte esto.`],
    "Testimonio honesto": [`Mi reseña honesta de ${p} tras semanas de uso.`, `Lo compré escéptico. Grabo esto convencido.`, `Nadie me paga por decir esto: ${p} vale cada centavo.`],
    "Comparación con alternativa cara": [`Lo caro vs. ${p}: hice la prueba por ti.`, `Mismo resultado, 10 veces menos precio.`, `Marca famosa vs. ${p}: test real.`],
    "Descubrimiento viral": [`No sabía que necesitaba ${p} hasta ver esto.`, `¿Por qué nadie habla de ${p}?`, `El hallazgo que no pensaba compartir.`],
    "Humor / relatable": [`Yo explicando por qué NECESITO ${p} 😅`, `Nadie: … Yo a las 3am: AÑADIR AL CARRITO.`, `Fase 1: "qué tontería" → Fase 3: [este video].`],
  };
  return pick(rng, map[angle] ?? map["Problema → Solución"]);
}

// ---------- 6. Visual Generator ----------
function genVisualSets(rng: Rng, cat: CategoryKB, p: string, intel: Intelligence): VisualSet[] {
  const persons = ["Mujer, 28 años", "Hombre, 32 años", "Mujer, 35 años", "Mujer, 24 años", "Hombre, 26 años", "Mujer, 45 años"];
  const person = pick(rng, persons);
  const pain = pick(rng, cat.audiences.flatMap((a) => a.pains)).toLowerCase();

  const set1: Scene[] = [
    { n: 1, shot: "Close-up", subject: person, expression: "Frustrada, suspiro visible", light: "Natural, ligeramente fría", text: `POV: otra vez ${pain}`, movement: "Cámara fija, ligero push-in", duration: "2s", audio: "Sonido ambiente + silencio incómodo" },
    { n: 2, shot: "Plano medio", subject: `${person} con el producto en mano`, expression: "Curiosidad, ceja levantada", light: "Natural cálida", text: `Hasta que probé esto…`, movement: "Paneo suave hacia el producto", duration: "2s", audio: "Inicio del beat musical" },
    { n: 3, shot: "Primer plano macro", subject: `${p} en acción`, expression: "—", light: "Direccional que resalte textura", text: "", movement: "Slow motion 0.5x del momento clave", duration: "3s", audio: "ASMR del producto + música baja" },
    { n: 4, shot: "Plano detalle", subject: "El resultado inmediato", expression: "—", light: "Brillante, saturada", text: `En serio funciona así de rápido`, movement: "Whip-pan desde el producto al resultado", duration: "2s", audio: "Beat drop" },
    { n: 5, shot: "Plano medio", subject: person, expression: "Sorpresa genuina → sonrisa", light: "Natural cálida", text: `¿POR QUÉ NADIE ME LO DIJO ANTES?`, movement: "Cámara en mano, ligera sacudida de energía", duration: "2s", audio: "Música arriba + reacción vocal" },
    { n: 6, shot: "Plano general", subject: `${cat.environment} transformado`, expression: "—", light: "Golden hour o luz idealizada", text: `Link en bio · -30% esta semana`, movement: "Zoom out lento revelando todo", duration: "3s", audio: "Música con cierre + voz CTA" },
  ];

  const set2: Scene[] = [
    { n: 1, shot: "Pantalla dividida", subject: "Izquierda: método antiguo / Derecha: con el producto", expression: "—", light: "Idéntica en ambos lados", text: `Mismo objetivo. Dos mundos.`, movement: "Ambos lados en time-lapse sincronizado", duration: "4s", audio: "Tic-tac de reloj acelerado" },
    { n: 2, shot: "Close-up al lado antiguo", subject: "Manos luchando con el método tradicional", expression: "Tensión en las manos", light: "Ligeramente subexpuesta", text: `${int(rng, 10, 25)} minutos y contando…`, movement: "Cámara fija con timer en pantalla", duration: "3s", audio: "Suspiro + ambiente" },
    { n: 3, shot: "Close-up al lado nuevo", subject: `${p} completando la tarea`, expression: "—", light: "Limpia y brillante", text: `${int(rng, 8, 40)} segundos. Listo.`, movement: "Un solo take, sin cortes", duration: "4s", audio: "Ding de completado" },
    { n: 4, shot: "Plano medio frontal", subject: person, expression: "Mirada a cámara, complicidad", light: "Natural", text: `Tú decides cómo seguir`, movement: "Cámara fija", duration: "2s", audio: "Música suave + voz directa" },
    { n: 5, shot: "Producto hero", subject: `${p} rotando sobre fondo limpio`, expression: "—", light: "Estudio, 3 puntos", text: `${intel.pricing.recommended} · Garantía 30 días`, movement: "Rotación 360° en turntable", duration: "3s", audio: "Cierre musical + CTA hablado" },
  ];

  const set3: Scene[] = [
    { n: 1, shot: "POV unboxing", subject: "Manos abriendo el paquete", expression: "—", light: "Natural de ventana", text: `Llegó lo que TikTok me obligó a comprar`, movement: "POV cámara en la frente/pecho", duration: "3s", audio: "ASMR papel + expectación" },
    { n: 2, shot: "Plano detalle", subject: `${p} recién sacado, primer contacto`, expression: "—", light: "Natural", text: `Primera impresión: ${pick(rng, ["pesa más de lo que esperaba (bien)", "se siente premium", "es más compacto de lo que parece"])}`, movement: "Manos girando el producto ante cámara", duration: "3s", audio: "Comentario en voz en off natural" },
    { n: 3, shot: "Plano medio", subject: `${person} probándolo por primera vez`, expression: "Concentración → sorpresa", light: "Ambiente real, sin preparar", text: `Primer intento, sin editar:`, movement: "Cámara apoyada, estilo casero", duration: "4s", audio: "Sonido real sin música" },
    { n: 4, shot: "Close-up reacción", subject: person, expression: "Sorpresa auténtica, risa", light: "La misma, real", text: `NO ESPERABA ESO`, movement: "Cámara en mano acercándose", duration: "2s", audio: "Risa/exclamación genuina" },
    { n: 5, shot: "Selfie a cámara", subject: person, expression: "Veredicto sincero", light: "Frontal suave", text: `Veredicto: ${pick(rng, ["aprobado con nota", "vale cada centavo", "repetiría la compra"])}`, movement: "Selfie estático", duration: "3s", audio: "Voz directa + música sutil de cierre" },
  ];

  return [
    { title: "Storyboard A · Problema → Wow", concept: `El clásico que convierte: mostrar el dolor real y resolverlo en cámara. Pensado para TikTok/Reels en frío.`, scenes: set1 },
    { title: "Storyboard B · Comparación en paralelo", concept: `Pantalla dividida método antiguo vs. ${p}. La evidencia visual elimina la incredulidad. Ideal para Meta Ads.`, scenes: set2 },
    { title: "Storyboard C · Unboxing UGC honesto", concept: `Estilo 100% nativo: unboxing con reacción real y veredicto. Perfecto para Spark Ads y cuentas de afiliados.`, scenes: set3 },
  ];
}

// ---------- 7-8. AI Prompts ----------
function genImagePrompts(rng: Rng, cat: CategoryKB, p: string): PromptGroup[] {
  const base = `${p}, ${cat.name.toLowerCase()}`;
  const envEn = cat.environment;
  const mk = (title: string, prompt: string, meta: string) => ({ title, prompt, meta });

  return [
    {
      tool: "GPT Image",
      prompts: [
        mk("Hero shot para landing", `Professional product photography of ${base}, centered hero shot on a clean gradient studio background (deep violet to soft cyan), soft three-point lighting, subtle reflection below the product, ultra-sharp details, e-commerce hero image style, 4k`, "1:1 · landing y ads"),
        mk("Lifestyle en contexto", `Photorealistic lifestyle photo: a happy person using ${base} in ${envEn}, natural window light, candid moment, shallow depth of field, warm color grading, authentic UGC feel, shot on smartphone aesthetic`, "4:5 · Meta feed"),
        mk("Antes y después", `Split-screen comparison image: left side shows the frustrating 'before' situation (messy, dull colors), right side shows the perfect 'after' result using ${base} (bright, clean, vibrant), clear visual contrast, bold dividing line, advertising style`, "1:1 · imagen estática"),
        mk("Infografía de beneficios", `Clean modern infographic of ${base} in the center with 4 callout lines pointing to its key features, minimal flat design with soft shadows, brand colors violet and cyan, white background, professional e-commerce infographic`, "1:1 · carrusel"),
      ],
    },
    {
      tool: "Midjourney",
      prompts: [
        mk("Hero editorial", `${base} floating in mid-air, dramatic studio lighting, dark premium background with volumetric light rays, commercial advertising photography, hyper detailed --ar 4:5 --style raw --v 7`, "4:5 · ads premium"),
        mk("Macro de textura", `extreme macro shot of ${base}, surface texture detail, water droplets, dramatic side lighting, product commercial photography, shallow DOF --ar 1:1 --style raw`, "1:1 · detalle"),
        mk("Escena aspiracional", `cinematic lifestyle scene, person enjoying the result of using ${base} in ${envEn}, golden hour light through windows, warm tones, editorial magazine photography --ar 9:16 --style raw`, "9:16 · stories"),
        mk("Bodegón con props", `flat lay composition of ${base} surrounded by relevant props on a pastel surface, top-down view, soft even lighting, e-commerce catalog style, negative space for text on the left --ar 16:9`, "16:9 · banner"),
      ],
    },
    {
      tool: "Flux",
      prompts: [
        mk("UGC realista", `amateur smartphone photo of ${base} being used at home in ${envEn}, slightly imperfect framing, natural daylight, realistic skin tones, authentic user-generated content look, no studio lighting`, "9:16 · nativo TikTok"),
        mk("Hero con texto", `product advertisement for ${base}, bold headline space at top, product centered bottom two-thirds, vibrant gradient background, high contrast commercial lighting, ad creative layout`, "4:5 · ad con overlay"),
        mk("Resultado wow", `photorealistic close-up of the exact 'wow moment': ${cat.wowMoment}, freeze-frame action shot, crisp motion detail, bright commercial lighting`, "1:1 · thumbnail"),
      ],
    },
    {
      tool: "Nano Banana",
      prompts: [
        mk("Edición: fondo limpio", `Take this product photo of ${p} and place it on a clean seamless studio background with a soft violet-to-cyan gradient, keep the product exactly as is, add a subtle floor reflection and soft drop shadow`, "editar foto real"),
        mk("Edición: en manos de modelo", `Place this ${p} naturally into the hands of a smiling 28-year-old woman in ${envEn}, natural light, make it look like an authentic lifestyle photo, keep product details identical`, "editar foto real"),
        mk("Variación de escena", `Show this same ${p} in four different everyday contexts as a 2x2 grid: at home, outdoors, as a gift being unwrapped, and in professional use. Keep the product identical in each`, "grid 2x2"),
      ],
    },
    {
      tool: "Hailuo (imagen)",
      prompts: [
        mk("Retrato con producto", `A cheerful person holding ${base} towards the camera, excited expression, bright natural lighting in ${envEn}, vertical composition optimized for mobile ads, photorealistic`, "9:16"),
        mk("Producto dramático", `${base} on a pedestal with dramatic spotlight, dark background, floating particles, premium commercial product shot, cinematic color grade`, "1:1"),
      ],
    },
    {
      tool: "Kling (imagen)",
      prompts: [
        mk("Escena de demo", `Photorealistic frame of ${base} mid-action: ${cat.demoAction}, motion blur on moving parts, sharp focus on product, bright commercial lighting, vertical mobile format`, "9:16 · frame inicial para video"),
        mk("Reacción humana", `Close-up of a person's genuinely surprised face reacting to ${base}, mouth slightly open, wide eyes, natural indoor lighting, authentic candid emotion, vertical format`, "9:16 · frame de reacción"),
      ],
    },
  ];
}

function genVideoPrompts(rng: Rng, cat: CategoryKB, p: string): PromptGroup[] {
  const envEn = cat.environment;
  const mk = (title: string, prompt: string, meta: string) => ({ title, prompt, meta });
  return [
    {
      tool: "Veo",
      prompts: [
        mk("Demo cinemática", `Cinematic product video: ${p} in use, ${cat.demoAction}. Camera starts with a slow dolly-in on the product, then cuts to a top-down view of the action. Bright natural lighting in ${envEn}. Smooth 24fps motion, commercial advertising quality. Audio: subtle satisfying product sounds.`, "8s · 9:16"),
        mk("Reacción UGC", `Handheld smartphone-style video of a woman in her late 20s trying ${p} for the first time in ${envEn}. Her expression shifts from skepticism to genuine surprise and delight. Natural window light, authentic UGC aesthetic, slight camera shake. She looks at the camera and smiles at the end.`, "8s · 9:16"),
        mk("Antes/después con transición", `Video with a match-cut transition: first half shows a frustrating 'before' scene (dull colors, slow motion), a hand swipe wipes the frame, second half reveals the vibrant 'after' result of using ${p}. Dynamic lighting change from cold to warm.`, "8s · 9:16"),
      ],
    },
    {
      tool: "Kling",
      prompts: [
        mk("Momento wow en slow motion", `Ultra slow-motion shot of the key moment: ${cat.wowMoment}. Macro detail, dramatic lighting with soft highlights, particles/texture visible, commercial quality, loop-friendly ending. Vertical 9:16.`, "5-10s · loop"),
        mk("Producto 360 flotante", `${p} floating and slowly rotating in a dark premium studio space, volumetric light beams, subtle camera orbit in the opposite direction, dust particles in the light, luxury commercial aesthetic. Vertical format.`, "5s · hero"),
        mk("Demo con manos", `Close-up of hands using ${p} in ${envEn}: ${cat.demoAction}. Smooth confident hand movements, bright even lighting, sharp focus follows the action, satisfying pacing.`, "10s · demo"),
      ],
    },
    {
      tool: "Hailuo",
      prompts: [
        mk("Escena lifestyle", `A person in ${envEn} uses ${p} as part of their daily routine, camera follows with a smooth gimbal movement, warm morning light, aspirational but realistic tone, ends on a satisfied smile to camera.`, "6s · 9:16"),
        mk("Time-lapse de transformación", `Time-lapse of a transformation using ${p}: the scene visibly improves from chaotic/frustrating to clean/resolved, fixed camera position, natural light shifting subtly, satisfying final reveal frame.`, "6s · reveal"),
      ],
    },
    {
      tool: "Runway",
      prompts: [
        mk("Intro con impacto", `High-energy opening shot: rapid push-in from medium to extreme close-up on ${p} right as it performs its key action (${cat.wowMoment}), speed-ramp effect, flash transition at the end. Commercial advertising energy. 9:16 vertical.`, "4s · hook visual"),
        mk("B-roll de detalle", `Slow elegant B-roll sequence of ${p}: three chained shots — macro texture pan, rotating three-quarter view, final hero frame with light sweep. Dark gradient background, premium tech-ad aesthetic.`, "8s · b-roll"),
      ],
    },
    {
      tool: "Pika",
      prompts: [
        mk("Loop satisfying", `Perfectly looping video of ${p} performing its most satisfying action repeatedly: ${cat.demoAction}. Clean composition, pastel background, ASMR visual quality, seamless loop point.`, "3s · GIF/loop"),
        mk("Unboxing mágico", `Stylized unboxing: the box of ${p} opens by itself with a soft glow, the product rises gently and settles into place, confetti-like particles, playful commercial style, vertical format.`, "5s · teaser"),
      ],
    },
  ];
}

// ---------- 9. UGC ----------
function genUgc(rng: Rng, cat: CategoryKB, p: string, intel: Intelligence): UgcCreator[] {
  const b = (i: number) => intel.benefits[i % intel.benefits.length];
  const pain = pick(rng, cat.audiences.flatMap((a) => a.pains)).toLowerCase();
  return [
    {
      persona: "Mamá", emoji: "👩‍👧", profile: "Madre de 2, 34 años, cero tiempo libre, compra soluciones prácticas y las comparte en su grupo de madres",
      tone: "Cercano, cómplice, ligeramente caótico-realista ('esto me salvó la semana')",
      setting: `Su casa real, con ruido de fondo de niños; graba en la cocina o el salón entre tareas`,
      hook: `Mamás: esto me devolvió ${int(rng, 2, 5)} horas a la semana. No exagero.`,
      script: `[A cámara, con el producto en mano] Ok, escúchenme porque esto es serio. Entre los niños, la casa y el trabajo, yo NO tengo tiempo para ${pain}. Una amiga del grupo de mamás me pasó ${p} y pensé "otra cosa más que no funciona"… [demo rápida] ¿VIERON ESO? ${b(0)}. Lo uso todos los días desde hace ${int(rng, 2, 6)} semanas. Si eres mamá, esto no es un gasto, es supervivencia. Link abajo — y me lo agradeces luego.`,
      wardrobe: "Ropa cómoda real (no producida), pelo recogido, cero maquillaje de estudio",
    },
    {
      persona: "Doctor / especialista", emoji: "🥼", profile: "Profesional de la salud o especialista del sector, 38 años, aporta autoridad y desmonta mitos",
      tone: "Educativo, calmado, con autoridad; explica el 'porqué' científico o técnico",
      setting: "Consultorio o espacio neutro profesional, bata o vestimenta formal",
      hook: `Como especialista, esto es lo que le digo a mis pacientes sobre ${cat.name.toLowerCase()}.`,
      script: `[A cámara, tono profesional] Me preguntan mucho por ${p}, así que hablemos con datos. El problema real es este: ${pick(rng, cat.secondaryProblems).toLowerCase()}. La mayoría de soluciones no atacan la causa. [muestra el producto] Lo que me parece bien diseñado de este: ${b(0).toLowerCase()}, y sobre todo, ${b(1).toLowerCase()}. ¿Es magia? No. ¿Es una herramienta útil si la usas con constancia? Absolutamente. Mi recomendación honesta: pruébalo con la garantía de 30 días y evalúa tú mismo.`,
      wardrobe: "Bata blanca o camisa formal, fondo ordenado con credibilidad visual",
    },
    {
      persona: "Deportista", emoji: "🏋️", profile: "Atleta amateur de 27 años, entrena 5 días por semana, audiencia que confía en su disciplina",
      tone: "Energético, directo, orientado a resultados y rendimiento",
      setting: "Gimnasio en casa o parque, grabando entre series, respiración real post-entreno",
      hook: `Llevo ${int(rng, 3, 8)} semanas usando ${p} y estos son mis resultados reales.`,
      script: `[Post-entreno, algo agitado] Sin rodeos: yo no recomiendo cosas que no uso. ${p} llegó porque ${pain} me estaba frenando. [demo en contexto deportivo] La diferencia real: ${b(0).toLowerCase()}. Lo mido, porque yo lo mido todo: ${int(rng, 15, 40)}% de mejora en mi rutina diaria. No es suplemento mágico ni humo: es una herramienta que funciona si tú funcionas. Link en mi perfil. Nos vemos entrenando.`,
      wardrobe: "Ropa deportiva usada de verdad, toalla al hombro, botella al lado",
    },
    {
      persona: "Estudiante", emoji: "🎓", profile: "Universitaria de 21 años, presupuesto mínimo, experta en encontrar chollos y compartirlos",
      tone: "Rápido, divertido, generación Z, cortes ágiles y texto en pantalla",
      setting: "Su habitación/residencia, luz de anillo, decoración estudiantil",
      hook: `Cosas que valen la pena con presupuesto de estudiante, parte ${int(rng, 3, 17)}:`,
      script: `[Cortes rápidos] Ok presupuesto real: soy estudiante, cada peso cuenta, y AÚN ASÍ ${p} entró a mi top del año. [demo casera] Uno: ${b(0).toLowerCase()}. Dos: cuesta menos que una salida de viernes. Tres: llevo usándolo ${int(rng, 1, 4)} meses y sigue como el primer día. ¿Hace falta? Técnicamente no. ¿Mejora tu vida diaria por lo que cuesta? Al 100%. Está en oferta esta semana, corre. [señala el link]`,
      wardrobe: "Sudadera oversize, estilo casual auténtico de campus",
    },
    {
      persona: "CEO / emprendedor", emoji: "💼", profile: "Fundador de 35 años, optimiza cada minuto, su audiencia compra 'eficiencia'",
      tone: "Ejecutivo pero cercano, enfocado en ROI de tiempo y decisiones inteligentes",
      setting: "Oficina moderna o home office premium, entre reuniones",
      hook: `Compro cualquier cosa que me ahorre 10 minutos al día. Esto me ahorra más.`,
      script: `[Sentado en su escritorio] Regla personal: si algo me devuelve tiempo, el precio casi no importa. ${p} pasó el filtro. [demo eficiente] El cálculo es simple: ${pain} me costaba ${int(rng, 15, 45)} minutos a la semana. Esto lo reduce a segundos. ${b(0)}. En un año, son horas recuperadas por el precio de un almuerzo de trabajo. Las mejores inversiones no siempre están en la bolsa. Link abajo.`,
      wardrobe: "Camisa o polo limpio, reloj visible, setup ordenado de fondo",
    },
    {
      persona: "Pareja", emoji: "💑", profile: "Pareja de 26 y 29 años, comparten la cuenta y el contenido, dinámica divertida de 'él escéptico / ella convencida'",
      tone: "Divertido, con química real, mini-sketch con giro final",
      setting: "Su apartamento, plano fijo estilo sketch",
      hook: `Él dijo que era tirar el dinero. Ahora no me lo presta. 🙃`,
      script: `[Ella a cámara] Compré ${p} y este señor [lo señala] dijo, cito textual: "otra cosa de TikTok". [Él, de fondo]: ¡Porque lo era! [Ella] Ajá. ¿Y quién lo usó esta mañana? [silencio culpable] [Demo conjunta] La verdad: ${b(0).toLowerCase()}, y hasta el escéptico oficial de la casa lo aprueba. [Él, resignado]: …está bueno. Compren dos. No cometan nuestro error. [risas] Link en bio.`,
      wardrobe: "Ropa casual de estar en casa, naturalidad ante todo",
    },
    {
      persona: "Abuelo/a", emoji: "👴", profile: "Jubilado de 68 años carismático, la honestidad de otra generación genera confianza total",
      tone: "Entrañable, directo, sin filtros ('a mi edad no tengo tiempo para mentiras')",
      setting: "Su casa de toda la vida, luz natural, quizá con nieto grabando",
      hook: `Tengo ${int(rng, 65, 75)} años y esto es lo más útil que me han regalado en décadas.`,
      script: `[Sentado en su sillón, producto en mano] Mi nieta me regaló esto de ${p} y le dije: "hija, yo llevo 40 años haciéndolo a mi manera". [pausa] Pues mi manera era peor. [demo pausada y clara] Miren: ${b(0).toLowerCase()}. Sin complicaciones, sin manuales de 30 páginas. Si yo puedo usarlo, puede usarlo cualquiera. Y a mi edad, no pierdo el tiempo recomendando tonterías. Díganle a sus nietos que les compren uno.`,
      wardrobe: "Su ropa habitual de domingo, gafas, autenticidad total",
    },
  ];
}

// ---------- 13. Landing ----------
function genLanding(rng: Rng, cat: CategoryKB, p: string, intel: Intelligence): LandingCopy {
  const b = intel.benefits;
  const desire = pick(rng, cat.desires);
  const names = ["María G.", "Carlos R.", "Lucía F.", "Andrea M.", "Jorge L.", "Valentina S.", "Pablo T.", "Camila D."];
  const picked = sample(rng, names, 4);
  return {
    headline: `${desire[0].toUpperCase() + desire.slice(1)} — sin gastar de más y desde el primer día`,
    subheadline: `${p} resuelve lo que llevas meses aguantando: ${pick(rng, cat.audiences.flatMap((a) => a.pains)).toLowerCase()}. Con garantía de 30 días y envío con seguimiento.`,
    benefits: b.slice(0, 5).map((x) => {
      const [t, ...rest] = x.split(":");
      return { title: t.trim(), text: rest.join(":").trim() || `${p} lo hace posible desde el primer uso, sin curva de aprendizaje.` };
    }),
    faq: [
      { q: "¿Cuánto tarda el envío?", a: "Entre 5 y 12 días hábiles con número de seguimiento incluido. Te avisamos en cada etapa del trayecto." },
      { q: "¿Y si no me convence?", a: "Tienes 30 días de garantía de devolución sin preguntas. Nos escribes, lo devuelves y te reembolsamos. Así de simple." },
      { q: "¿Es difícil de usar?", a: `Para nada: ${p} está diseñado para funcionar desde el primer minuto. Incluye instrucciones claras en español.` },
      { q: "¿Funciona para mi caso?", a: `Sí: está pensado para ${cat.audiences.map((a) => a.name.toLowerCase()).join(", ")}. Si tienes dudas concretas, escríbenos por chat y te asesoramos antes de comprar.` },
      { q: "¿Es seguro pagar aquí?", a: "Usamos pasarelas de pago encriptadas (las mismas de las grandes tiendas). No almacenamos datos de tu tarjeta." },
      { q: "¿Hay descuento por comprar más de uno?", a: "Sí: la segunda unidad tiene 30% de descuento y el envío es gratis en pedidos de 2 o más. Ideal para regalar." },
    ],
    guarantee: `Garantía incondicional de 30 días: pruébalo en tu día a día. Si no notas la diferencia, te devolvemos el 100% del dinero sin preguntas ni formularios eternos. El riesgo lo asumimos nosotros.`,
    ctas: [
      "QUIERO EL MÍO CON -30%",
      "Comprar ahora con garantía de 30 días",
      "Sí, quiero resolverlo hoy",
      "Pedir el mío antes de que se agote",
      "Probar sin riesgo durante 30 días",
    ],
    comparison: [
      { feature: "Resultado desde el primer uso", us: "✅ Sí, demostrable", them: "❌ Semanas o nunca" },
      { feature: "Precio", us: `✅ ${intel.pricing.recommended} pago único`, them: "❌ Gasto recurrente o 3-5x más caro" },
      { feature: "Facilidad de uso", us: "✅ Listo en minutos", them: "❌ Curva de aprendizaje o citas" },
      { feature: "Garantía", us: "✅ 30 días sin preguntas", them: "❌ Letra pequeña" },
      { feature: "Envío con seguimiento", us: "✅ Incluido", them: "⚠️ Depende del vendedor" },
    ],
    reviews: picked.map((name, i) => ({
      name,
      stars: i === 2 ? 4 : 5,
      text: pick(rng, [
        `Sinceramente no esperaba mucho y me sorprendió. ${b[i % b.length]}. Ya pedí otro para regalar.`,
        `Lo uso todos los días desde que llegó. ${pick(rng, cat.desires)[0].toUpperCase() + pick(rng, cat.desires).slice(1)} por fin es real.`,
        `Llegó antes de lo esperado y funciona tal cual el video. Le quito una estrella solo porque quiero que siga habiendo stock 😅`,
        `Se lo recomendé a mi hermana y a dos compañeras de trabajo. Eso lo dice todo.`,
      ]),
      detail: `Compra verificada · hace ${int(rng, 2, 30)} días`,
    })),
  };
}

// ---------- 14. Offers ----------
function genOffers(rng: Rng, cat: CategoryKB, p: string, intel: Intelligence): Offer[] {
  const rec = parseFloat(intel.pricing.recommended.replace(/[^0-9.]/g, "")) || 39.95;
  const f = (n: number) => `$${n.toFixed(2)}`;
  return [
    { type: "2x1", name: "Doble o nada", description: `Compra 1 ${p} y llévate el segundo gratis durante el lanzamiento.`, structure: `Precio del bundle = ${f(rec * 1.7)} (percibido: 2 unidades por casi el precio de una). Margen sostenido subiendo el precio ancla unitario.`, example: `"Hoy: 2x1 — el segundo para regalar (o para no compartir el tuyo)."`, bestFor: "Productos con coste bajo y alta regalabilidad. Dispara el AOV desde el día 1." },
    { type: "Bundle", name: "Kit completo", description: `${p} + accesorio complementario + guía rápida digital como paquete único.`, structure: `Producto (${f(rec)}) + accesorio (valor ${f(rec * 0.4)}) + guía (valor ${f(9.95)}) = valor total ${f(rec * 1.4 + 9.95)}. Precio del kit: ${f(rec * 1.25)}.`, example: `"El Kit Completo: todo lo que necesitas para empezar hoy, con ${Math.round(((rec * 1.4 + 9.95 - rec * 1.25) / (rec * 1.4 + 9.95)) * 100)}% de descuento sobre el valor real."`, bestFor: "Subir el ticket medio sin bajar el precio unitario percibido." },
    { type: "Compra 2 y recibe...", name: "Segundo al 50%", description: `La segunda unidad a mitad de precio + envío gratis automático.`, structure: `Unidad 1: ${f(rec)} · Unidad 2: ${f(rec / 2)} · Envío gratis desde 2 unidades (el coste de envío se absorbe con el margen extra).`, example: `"Llévate 2: el segundo a -50% y el envío corre por nuestra cuenta."`, bestFor: "El punto medio entre margen y conversión. La oferta más segura para empezar." },
    { type: "Regalo gratis", name: "Regalo sorpresa", description: `Todo pedido de hoy incluye un regalo de valor percibido alto y coste real mínimo.`, structure: `Regalo: accesorio o mini-producto con coste < ${f(3)} pero valor percibido ${f(14.95)}. Comunicar el valor, nunca el coste.`, example: `"Solo hoy: tu pedido llega con un regalo valorado en ${f(14.95)}. No lo elegimos al azar: lo vas a usar junto al producto."`, bestFor: "Diferenciarse de competidores que venden el mismo producto sin extras." },
    { type: "Descuento progresivo", name: "Escalera de descuento", description: `Más unidades, más descuento: 1 = precio normal, 2 = -20%, 3 = -30%.`, structure: `1 ud: ${f(rec)} · 2 uds: ${f(rec * 2 * 0.8)} · 3 uds: ${f(rec * 3 * 0.7)}. Mostrar la opción de 2 como "MÁS POPULAR" (anclaje al centro).`, example: `Selector visual en la landing con 3 tarjetas y la del medio destacada: "El 68% elige esta opción".`, bestFor: "Maximizar AOV en productos consumibles o regalables. La tarjeta central hace el trabajo." },
    { type: "Urgencia", name: "Oferta con reloj real", description: `Descuento de lanzamiento con fecha de fin real y visible.`, structure: `-30% hasta el domingo 23:59. Cuenta atrás en landing y en los ads. IMPORTANTE: cumplirla de verdad (subir el precio al terminar) — la urgencia falsa mata la confianza y las cuentas publicitarias.`, example: `"El precio de lanzamiento termina el domingo. Después vuelve a ${f(rec * 1.4)}."`, bestFor: "Semana de lanzamiento y picos de tráfico (paydays, fechas especiales)." },
    { type: "Escasez", name: "Stock visible", description: `Mostrar unidades restantes reales del lote actual.`, structure: `"Quedan X unidades del lote" con número real del inventario. Al agotarse: lista de espera con email (captura leads para el siguiente lote).`, example: `"Lote 3 casi agotado — quedan 47 unidades. El lote 4 llega en 3 semanas."`, bestFor: "Productos con demanda demostrada. La lista de espera convierte la escasez en base de datos." },
  ];
}

// ---------- 15. Planner ----------
function genPlanner(rng: Rng, cat: CategoryKB, p: string): PlannerWeek[] {
  return [
    {
      week: "Semana 1 · Test de ángulos",
      goal: "Descubrir qué ángulo y hook conectan. Presupuesto pequeño repartido, matar rápido lo que no funcione.",
      items: [
        { count: 3, type: "Videos UGC", priority: "Alta", notes: "Un ángulo distinto cada uno: problema→solución, antes/después y testimonio. Usa los guiones de 15-30s.", platform: "TikTok" },
        { count: 8, type: "Hooks en video", priority: "Alta", notes: "El mismo cuerpo de video con 8 primeros segundos distintos. Solo cambia el hook.", platform: "TikTok / Reels" },
        { count: 5, type: "Imágenes estáticas", priority: "Media", notes: "2 antes/después, 2 hero con headline, 1 infografía de beneficios.", platform: "Meta" },
        { count: 2, type: "Carruseles", priority: "Media", notes: "Uno de beneficios y uno de reseñas reales.", platform: "Meta" },
        { count: 2, type: "Memes", priority: "Baja", notes: "Formato relatable del problema. Barato de producir, sorprende cuánto convierte.", platform: "TikTok / IG" },
      ],
    },
    {
      week: "Semana 2 · Iterar ganadores",
      goal: "Duplicar presupuesto en lo que funcionó (CTR > 1.5%, CPC bajo) y crear variaciones de los 2 mejores creativos.",
      items: [
        { count: 4, type: "Variaciones del video ganador", priority: "Alta", notes: "Mismo video: cambia hook, primera escena, música y CTA (una variable por versión).", platform: "El canal ganador" },
        { count: 2, type: "UGC con nuevas personas", priority: "Alta", notes: "El guion ganador grabado por 2 creadores de perfil distinto (edad/género).", platform: "TikTok" },
        { count: 1, type: "Video de 45-60s", priority: "Media", notes: "Versión extendida del ángulo ganador para retargeting.", platform: "Meta / YouTube" },
        { count: 3, type: "Thumbnails nuevos", priority: "Media", notes: "Para los videos con buen watch-time pero bajo CTR inicial.", platform: "Shorts" },
        { count: 1, type: "Story interactiva", priority: "Baja", notes: "Encuesta '¿te pasa esto?' → respuesta con el producto. Alimenta retargeting.", platform: "Instagram" },
      ],
    },
    {
      week: "Semana 3-4 · Escalar y ampliar",
      goal: "Escalar presupuesto en ganadores (20-30% cada 2-3 días), abrir segundo canal y montar el embudo completo.",
      items: [
        { count: 1, type: "VSL de 2-3 min", priority: "Alta", notes: "Para la landing y retargeting de visitantes que no compraron. Guion en Script Generator.", platform: "Landing / Meta" },
        { count: 4, type: "UGC de mantenimiento", priority: "Alta", notes: "El feed se quema: 2 creativos nuevos por semana mínimo para sostener el rendimiento.", platform: "TikTok / Meta" },
        { count: 2, type: "Carruseles de objeciones", priority: "Media", notes: "Cada tarjeta responde una objeción real de los comentarios de tus ads.", platform: "Meta" },
        { count: 3, type: "Banners de remarketing", priority: "Media", notes: "Display para carritos abandonados con oferta de recuperación.", platform: "Display / Email" },
        { count: 1, type: "Colaboración con micro-influencer", priority: "Media", notes: "1 creador de 10-100k seguidores del nicho. Pide derechos de uso para Spark Ads.", platform: "TikTok" },
      ],
    },
  ];
}

// ---------- 16. Viral Predictor ----------
function genViral(rng: Rng, cat: CategoryKB, p: string, score: CreativeScore): ViralPrediction {
  const factors: import("../types").ViralFactor[] = [
    { factor: "Momento 'wow' en <3 segundos", impact: cat.visualAppeal >= 4 ? "Positivo" : "Neutro", note: cat.visualAppeal >= 4 ? `${cat.wowMoment} — cabe perfectamente al inicio del video.` : "El efecto tarda en apreciarse: compensa con reacción humana inmediata." },
    { factor: "Se entiende sin sonido", impact: cat.explainability >= 4 ? "Positivo" : "Neutro", note: cat.explainability >= 4 ? "La demo visual comunica sola: ideal para scroll con volumen apagado." : "Requiere subtítulos grandes y texto en pantalla desde el segundo 0." },
    { factor: "Genera comentarios y debate", impact: "Positivo", note: `Preguntas tipo "¿funciona de verdad?" y "¿dónde lo compro?" — responde con video-respuestas para duplicar el alcance.` },
    { factor: "Nivel de saturación del feed", impact: cat.saturation >= 4 ? "Negativo" : "Positivo", note: cat.saturation >= 4 ? "El público ya vio productos parecidos: el hook tiene que romper el patrón, no repetirlo." : "Todavía hay efecto novedad en el feed: aprovéchalo antes de que llegue el resto." },
    { factor: "Replicabilidad UGC", impact: cat.ugcFit >= 4 ? "Positivo" : "Neutro", note: cat.ugcFit >= 4 ? "Cualquier creador puede grabarlo en casa en una tarde: el volumen de creativos escala barato." : "Necesita cierto setting o habilidad: selecciona bien a los creadores." },
    { factor: "Emoción compartible", impact: "Positivo", note: `El contenido dispara "${pick(rng, ["esto le pasa a mi hermana", "necesito enseñárselo a mi madre", "etiqueta a quien le pasa"])}" — el share es el multiplicador viral más barato.` },
  ];
  const positives = factors.filter((f) => f.impact === "Positivo").length;
  const negatives = factors.filter((f) => f.impact === "Negativo").length;
  const probability = Math.max(25, Math.min(95, Math.round(score.total * 0.6 + positives * 7 - negatives * 9 + int(rng, 0, 6))));
  return {
    probability,
    verdict:
      probability >= 75
        ? `Potencial viral alto. ${p} tiene los 3 ingredientes: demo visual, emoción compartible y facilidad UGC. La ejecución del hook decidirá el resto.`
        : probability >= 55
          ? `Potencial viral medio-alto. Funcionará con hooks fuertes y volumen de creativos; no esperes que un solo video lo haga todo.`
          : `Potencial viral moderado. Apuesta por conversión directa más que por viralidad: ads eficientes > sueño del video viral.`,
    factors,
    recommendations: [
      "Publica 2-3 videos orgánicos diarios los primeros 14 días: el algoritmo premia consistencia y te da datos gratis de qué hook retiene.",
      "Los primeros 1-2 segundos determinan el 80% del resultado: testea 8+ hooks sobre el mismo cuerpo de video antes de grabar contenido nuevo.",
      "Responde comentarios con video-respuestas: cada respuesta es un creativo nuevo con distribución gratuita.",
      "Cuando un video orgánico supere el 10% de engagement, conviértelo en Spark Ad en menos de 48h: el momentum caduca.",
      "Guarda todos los comentarios con objeciones: son los guiones de tus próximos creativos.",
    ],
  };
}

// ---------- 18. A/B Testing ----------
function genAbTests(rng: Rng, cat: CategoryKB, p: string, hooks: HookGroup[], intel: Intelligence): AbTestPlan[] {
  const allHooks = hooks.flatMap((h) => h.items);
  const ctas = [
    "Comprar ahora", "Lo quiero", "Ver oferta", "Pedir el mío", "Probar sin riesgo", "Comprar con -30%",
    "Sí, lo necesito", "Resolverlo hoy", "Ver cómo funciona", "Conseguir el mío", "Aprovechar la oferta",
    "Comprar antes de que se agote", "Empezar hoy", "Quiero el descuento", "Ver precio de hoy",
    "Añadir al carrito", "Descubrir más", "Reclamar mi oferta", "Pedir con garantía", "Comprar el kit",
  ];
  const thumbs = [
    `Cara de sorpresa + producto + "¿ESTO FUNCIONA?"`, `Antes/después dividido + "DÍA 1 vs DÍA 30"`,
    `Producto gigante + precio tachado`, `"NO COMPRES ESTO…" (sin terminar la frase)`,
    `Flecha roja al detalle clave del producto`, `Persona señalando el resultado + "MIRA ESTO"`,
    `"$${int(rng, 150, 400)} vs $${cat.priceBand[0]}" en grande`, `Primer plano del momento wow congelado`,
    `"El secreto de ${cat.name.toLowerCase()}" + candado`, `Reacción exagerada + círculo rojo`,
    `"Lo probé ${int(rng, 7, 30)} días" + calendario`, `Comparación lado a lado de tamaño real`,
    `"POR QUÉ NADIE DICE ESTO" + producto`, `Mano sosteniendo el producto hacia cámara`,
    `Resultado final + "SIN EDICIÓN"`, `"${int(rng, 10, 50)}.000 vendidos" + producto`,
    `Cara tapada con el producto (curiosidad)`, `Texto grande: "ME EQUIVOQUÉ"`,
    `Split: método viejo tachado / producto con check`, `Zoom extremo a la textura + "ESPERA AL FINAL"`,
  ];
  const intros = [
    "Abrir con el resultado final (spoiler) y rebobinar", "Abrir con la cara de reacción antes de mostrar nada",
    "Abrir con el problema en su peor momento", "Abrir con una pregunta directa a cámara",
    "Abrir con el precio de la alternativa cara", "Abrir con 'esto se va a agotar y te explico por qué'",
    "Abrir con el sonido ASMR del producto", "Abrir con un dato/estadística en pantalla completa",
    "Abrir con la caja llegando a la puerta", "Abrir con 'me pidieron que no contara esto'",
    "Abrir con el error común que todos cometen", "Abrir en mitad de la acción (in media res)",
    "Abrir con testimonio de otra persona en pantalla", "Abrir con comparación lado a lado ya corriendo",
    "Abrir con 'día 1 usando esto' estilo vlog",
  ];
  const endings = [
    "CTA directo + urgencia real ('la oferta termina el domingo')", "Pregunta a la audiencia ('¿lo probarías?') para comentarios",
    "Loop perfecto: el final conecta con el inicio del video", "Resultado final en silencio + texto con el precio",
    "Bloopers/toma falsa (humaniza y retiene hasta el final)", "'Sígueme para la parte 2' con teaser del siguiente test",
    "Testimonio de un tercero cerrando ('mi madre ya me pidió otro')", "Antes/después final en 1 segundo + logo + CTA",
    "Oferta apilada visual (producto + regalo + garantía)", "El creador usando el producto mientras habla el CTA",
  ];
  return [
    { element: "Hooks", emoji: "🪝", variants: sample(rng, allHooks, Math.min(50, allHooks.length)), metric: "Retención a 3 segundos (thumb-stop rate)" },
    { element: "CTAs", emoji: "👆", variants: ctas, metric: "CTR del botón y tasa de conversión post-clic" },
    { element: "Thumbnails", emoji: "🖼️", variants: thumbs, metric: "CTR de impresión a visualización" },
    { element: "Intros (primeros 3s)", emoji: "🎬", variants: intros, metric: "Retención al 25% del video" },
    { element: "Finales", emoji: "🏁", variants: endings, metric: "Tasa de clic al perfil/link y shares" },
  ];
}

// ---------- 12. Thumbnails ----------
function genThumbnails(rng: Rng, cat: CategoryKB, p: string, intel: Intelligence): ThumbnailConcept[] {
  return [
    { concept: "Reacción + producto", headline: "¿ESTO FUNCIONA?", style: "Cara de sorpresa genuina en primer plano, producto en la esquina inferior", colors: ["#FFD400", "#111111", "#FFFFFF"], layout: "Cara ocupa 60% derecha · texto arriba izquierda · producto abajo izquierda con borde blanco", prompt: `YouTube thumbnail style image: extreme close-up of a person's shocked face (60% right side), ${p} product photo bottom-left corner with white outline, bold yellow text space top-left, high contrast, saturated colors, 1280x720` },
    { concept: "Antes vs Después", headline: "DÍA 1 → DÍA 30", style: "Split vertical con contraste dramático de color entre ambos lados", colors: ["#F87171", "#34D399", "#FFFFFF"], layout: "Mitad izquierda desaturada (antes) · mitad derecha vibrante (después) · flecha central gruesa", prompt: `Split-screen thumbnail: left half shows dull desaturated 'before' scene, right half shows vibrant colorful 'after' result of using ${p}, thick white arrow in the center, bold text banner at bottom, 1280x720, high contrast` },
    { concept: "Precio shock", headline: `$${int(rng, 150, 400)} vs $${cat.priceBand[0]}`, style: "Comparación de precios gigante con el producto entre ambos números", colors: ["#F87171", "#34D399", "#0B0B12"], layout: "Precio caro tachado a la izquierda · producto al centro · precio bajo en verde brillante a la derecha", prompt: `Bold comparison thumbnail: large red crossed-out expensive price on the left, ${p} product photo in the center with glow effect, large green price on the right, dark background, dramatic lighting, 1280x720` },
    { concept: "Curiosidad prohibida", headline: "NO COMPRES ESTO…", style: "Frase incompleta que obliga al clic, producto parcialmente oculto", colors: ["#FBBF24", "#111111", "#FFFFFF"], layout: "Texto gigante centrado · producto borroso o semitapado detrás · esquina con '...' visible", prompt: `Clickbait-style thumbnail: large bold warning text in the center, ${p} partially hidden/blurred behind the text, dark moody background with a spotlight, yellow and white typography, 1280x720` },
    { concept: "Momento wow congelado", headline: "ESPERA AL SEGUNDO 3", style: "Frame exacto del momento más impactante con círculo rojo", colors: ["#EF4444", "#FFFFFF", "#22D3EE"], layout: "Acción congelada a pantalla completa · círculo rojo señalando el detalle · texto en franja inferior", prompt: `Action freeze-frame thumbnail: the exact 'wow moment' of ${p} in use (${cat.wowMoment}), motion blur on edges, red circle highlighting the key detail, text banner along the bottom, vivid colors, 1280x720` },
    { concept: "Autoridad con datos", headline: `${int(rng, 10, 60)}.000 VENDIDOS`, style: "Cifra de ventas gigante + producto hero + estrellas de reseñas", colors: ["#22D3EE", "#FFD400", "#0B0B12"], layout: "Número enorme arriba · producto centrado con glow · 5 estrellas y mini reseñas abajo", prompt: `Social-proof thumbnail: huge bold sales number at the top, ${p} hero shot in the center with cyan glow, five golden stars at the bottom, dark premium background, commercial style, 1280x720` },
  ];
}

// ---------- 11. Library ----------
function genLibrary(p: string, cat: CategoryKB): LibraryLink[] {
  const q = encodeURIComponent(p);
  const qCat = encodeURIComponent(cat.name.split(" ")[0]);
  return [
    { platform: "TikTok", name: "TikTok Creative Center — Top Ads", url: `https://ads.tiktok.com/business/creativecenter/inspiration/topads/pc/en?keyword=${q}`, note: "Los anuncios con mejor rendimiento de la categoría: estudia sus primeros 3 segundos y su CTA." },
    { platform: "TikTok", name: `Búsqueda orgánica: "${p}"`, url: `https://www.tiktok.com/search?q=${q}`, note: "El contenido orgánico que ya funciona. Ordena mentalmente por: hook usado, duración y comentarios." },
    { platform: "Facebook", name: "Meta Ad Library", url: `https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL&q=${q}&media_type=all`, note: "Todos los ads activos con este producto. Si un ad lleva 30+ días activo, es rentable: analízalo a fondo." },
    { platform: "Instagram", name: `Hashtags del nicho`, url: `https://www.instagram.com/explore/search/keyword/?q=${q}`, note: "Contenido orgánico e influencers que ya publican sobre el producto o la categoría." },
    { platform: "Pinterest", name: `Pinterest Trends`, url: `https://www.pinterest.com/search/pins/?q=${q}`, note: "Estética ganadora de la categoría: paletas, composición y estilos de foto que el público guarda." },
    { platform: "YouTube", name: `Reviews y unboxings`, url: `https://www.youtube.com/results?search_query=${q}+review`, note: "Las reviews largas revelan las objeciones reales: apunta cada 'pero' que mencionen — son tus próximos creativos." },
    { platform: "Google", name: "Google Trends de la categoría", url: `https://trends.google.com/trends/explore?q=${qCat}`, note: "Estacionalidad y tendencia de demanda: decide cuándo acelerar o frenar presupuesto." },
    { platform: "AliExpress", name: "Búsqueda por ventas", url: `https://www.aliexpress.com/wholesale?SearchText=${q}&SortType=total_tranpro_desc`, note: "Ordena por pedidos: los números de venta reales validan (o desmienten) la demanda." },
  ];
}

// ---------- Competitor Analyzer (bajo demanda) ----------
export function analyzeCompetitor(url: string, pastedCopy: string, cat: CategoryKB, p: string): import("../types").CompetitorAnalysis {
  const rng = makeRng(url + p);
  const text = pastedCopy.trim();
  const lines = text.split(/\n+/).map((l) => l.trim()).filter((l) => l.length > 8 && l.length < 160);
  const foundHooks = lines.filter((l) => /[?!]|gratis|descuento|oferta|nuevo|últim|solo|ya|ahora|%/i.test(l)).slice(0, 6);
  const foundCtas = lines.filter((l) => /^(compra|pide|consigue|obt[eé]n|a[ñn]ade|lo quiero|shop|buy|order|get|claim|reclama|aprovecha|descubre)/i.test(l) || (l.length < 40 && /comprar|carrito|oferta|ahora/i.test(l))).slice(0, 5);
  let domain = url;
  try { domain = new URL(url).hostname.replace("www.", ""); } catch { /* URL inválida: usar texto tal cual */ }

  return {
    url,
    hooks: foundHooks.length ? foundHooks : [
      `(No se detectaron hooks en el texto pegado — pega el copy visible de su web o sus ads)`,
      `Revisa manualmente: su primer texto sobre el fold es su hook principal`,
    ],
    ctas: foundCtas.length ? foundCtas : [`(Pega el texto de sus botones para detectarlos)`, `Busca: texto de botones, barras de anuncio y pop-ups`],
    storytelling: text.length > 100
      ? `Del copy pegado se deduce una estructura ${/antes|despu[eé]s|era|hasta que/i.test(text) ? "de transformación (antes → después)" : /\d+%|clientes|reseñas|vendidos/i.test(text) ? "basada en prueba social y datos" : "directa de beneficio → oferta"}. Compárala con tus 6 ángulos: la oportunidad está en el ángulo que ellos NO usan.`
      : `Sin texto para analizar. Estrategia: entra a ${domain}, copia todo el texto de su home/landing y pégalo aquí para el desglose completo.`,
    colors: ["Revisa su web: anota color primario del CTA", "Color de fondo dominante", "Color de acento en ofertas"],
    offer: /2x1|bundle|gratis|descuento|%|env[ií]o gratis/i.test(text)
      ? `Oferta detectada en su copy: "${lines.find((l) => /2x1|bundle|gratis|descuento|%|env[ií]o/i.test(l)) ?? "descuento directo"}". Tu contraoferta debe cambiar la estructura, no solo el número: si ellos dan -30%, tú da bundle+regalo.`
      : `No se detectó oferta explícita en el texto. Si venden a precio seco, tienes ventaja inmediata con cualquier oferta estructurada (bundle, regalo, garantía extendida).`,
    guarantees: /garant[ií]a|devoluci[oó]n|reembolso|30 d[ií]as|refund/i.test(text)
      ? [`Detectada: "${lines.find((l) => /garant[ií]a|devoluci[oó]n|reembolso|refund/i.test(l)) ?? "garantía estándar"}"`, "Supérala: si ofrecen 30 días, ofrece 60 o añade 'sin preguntas'"]
      : ["No se detectó garantía visible: gran oportunidad — haz de tu garantía de 30 días un elemento central del creativo"],
    framework: `Framework probable del anuncio de ${domain}: Hook (${foundHooks[0]?.slice(0, 40) ?? "problema/beneficio"}...) → Agitación → Demo → Prueba social → Oferta → CTA (${foundCtas[0] ?? "compra directa"}). Para superarlo: no copies el framework, invierte el orden — abre con la prueba social o el resultado final.`,
    weaknesses: [
      "Si su copy es genérico (aplica a cualquier producto), tu especificidad gana: usa números, tiempos y casos concretos",
      "Si no tienen UGC real, tu contenido nativo convertirá mejor con menos presupuesto",
      "Si su landing es lenta o sin reviews con foto, ataca con velocidad y prueba social visual",
      `Si no responden comentarios en sus ads, sus objeciones sin responder son tus mejores hooks`,
    ],
    howToBeat: [
      `Ángulo diferencial: revisa sus ads en Meta Ad Library y lista los ángulos que usan. Ejecuta los ${int(rng, 2, 3)} ángulos que NO están usando.`,
      "Mejor oferta percibida: mismo precio pero con bundle/regalo/garantía superior — la comparación te favorece sin bajar margen.",
      "Velocidad de iteración: publica más variantes por semana que ellos. En creativo, el volumen con criterio gana.",
      "Comunidad: responde cada comentario con video. La marca que conversa parece 10 veces más grande.",
    ],
  };
}

// ---------- Creative Iteration (bajo demanda) ----------
export function analyzeIteration(description: string, cat: CategoryKB, p: string): import("../types").IterationAdvice {
  const d = description.toLowerCase();
  const rng = makeRng(description);
  const wrong: string[] = [];
  const remove: string[] = [];
  const add: string[] = [];

  if (d.length < 60) wrong.push("La descripción del creativo es muy breve: describe hook, duración, escenas y CTA para un diagnóstico más preciso.");
  if (!/hook|primer|inicio|apertura|arranc/i.test(d)) wrong.push("No mencionas el hook: si no puedes describir tu primer segundo en una frase, el espectador tampoco sabrá por qué quedarse.");
  if (/logo|intro|presentaci[oó]n de marca/i.test(d)) { wrong.push("Abrir con logo o presentación de marca: nadie espera a conocer tu marca, esperan una razón para no hacer scroll."); remove.push("Logo/intro de marca de los primeros 3 segundos — muévelo al final o elimínalo"); }
  if (/(30|40|45|60|90)\s*segundos|largo|minuto/.test(d) && !/vsl|retarget/i.test(d)) wrong.push("Duración larga para tráfico frío: en frío, 15-25 segundos casi siempre gana. Guarda lo largo para retargeting.");
  if (!/precio|oferta|descuento|cta|link|comprar/i.test(d)) wrong.push("No describes CTA ni oferta: el video puede retener y aun así no convertir si el cierre es débil.");
  if (/m[uú]sica.*(gen[eé]rica|stock)|sin m[uú]sica/i.test(d)) wrong.push("Audio genérico: en TikTok/Reels el sonido trending es señal de contenido nativo; el stock genérico grita 'anuncio'.");
  if (wrong.length === 0) wrong.push("La estructura general parece correcta: el problema estará en la ejecución fina — hook, ritmo de cortes y fuerza de la oferta. Revisa las secciones siguientes.");

  remove.push("Cualquier plano que dure más de 2.5 segundos sin información nueva", "Explicaciones de características técnicas que no se traducen en beneficio visible", "Frases de relleno tipo 'este producto increíble' — muestra, no califiques");
  add.push(`Subtítulos grandes desde el segundo 0 (el 80% del feed se ve sin sonido)`, `El momento wow (${cat.wowMoment}) en los primeros 3 segundos, aunque lo repitas después`, "Prueba social visual: captura de reseña o contador de ventas en el segundo 10-15", "Un elemento de urgencia real en el cierre (fecha o stock)");

  return {
    input: description,
    wrong,
    remove,
    add,
    test: [
      "La versión de 15s contra tu duración actual — mismo contenido, mitad de tiempo",
      "Abrir con el resultado final vs. abrir con el problema (spoiler vs. suspenso)",
      "Voz de hombre vs. voz de mujer en la narración",
      "Con precio visible en el video vs. sin precio (deja la curiosidad al clic)",
      `Fondo con ${cat.environment} real vs. fondo neutro de estudio`,
    ],
    hookChanges: [
      `Hazlo específico: cambia "mira este producto" por una cifra o tiempo concreto ("de ${int(rng, 10, 20)} minutos a ${int(rng, 10, 40)} segundos")`,
      "Primera palabra = palabra de impacto: 'Deja', 'Nadie', 'Esto', '¿Sabías…?' — nunca 'Hola' ni el nombre de la marca",
      "Añade un hook visual simultáneo al verbal: algo moviéndose o a punto de pasar en el frame 1",
      "Prueba el hook negativo ('No compres esto si…'): rompe el patrón de anuncio típico",
    ],
    ctaChanges: [
      "Un solo CTA, no tres: cada opción extra reduce la acción total",
      "CTA con beneficio, no con orden: 'Resuélvelo hoy con -30%' > 'Compra ahora'",
      "Añade razón para actuar YA: fecha de fin de oferta o unidades del lote",
      "Verbaliza el CTA mientras se muestra en pantalla: doble canal, doble refuerzo",
    ],
    pacingChanges: [
      "Corte cada 1.5-2 segundos máximo en los primeros 10 segundos",
      "Cambia de plano o de escala (cerrado→abierto) en cada corte, no solo de ángulo",
      "Sube el volumen/energía justo antes del momento clave (crea anticipación)",
      "Si la retención cae en un punto exacto de tus analytics, corta ese segmento entero: no lo mejores, elimínalo",
    ],
  };
}
