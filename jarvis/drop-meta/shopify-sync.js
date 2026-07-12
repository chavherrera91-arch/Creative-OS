// ============================================================
// DROP-META · Snapshot de Shopify (sincronizado por Claude vía MCP)
// Para refrescar: pide a Claude "re-sincroniza mi tienda" y este archivo se reescribe.
// ============================================================

const SHOPIFY_SNAPSHOT = {
  syncedAt: '2026-07-11',
  shop: {
    name: 'Lumbra',
    domain: 'lumbra-11.myshopify.com',
    plan: 'Basic',
    currency: 'USD',
    timezone: 'CST',
    country: 'Mexico',
  },
  products: [
    { title: 'Lumbra Candle Warmer Lamp (Yellow)', handle: 'lumbra-candle-warmer-lamp', status: 'ACTIVE', price: 49.95, sku: 'CJHD289470101AZ', inventory: 152, main: true },
    { title: 'Lumbra Candle Warmer Lamp (Pink)', handle: 'lumbra-candle-warmer-lamp-1', status: 'ACTIVE', price: 49.95, sku: 'CJHD289470701AZ', inventory: 151 },
    { title: 'Lumbra Candle Warmer Lamp (Green)', handle: 'lumbra-candle-warmer-lamp-2', status: 'ACTIVE', price: 49.95, sku: 'CJHD289471701AZ', inventory: 217 },
    { title: 'Lumbra Candle Warmer Lamp (Black)', handle: 'lumbra-candle-warmer-lamp-3', status: 'ACTIVE', price: 49.95, sku: 'CJHD289471001AZ', inventory: 254 },
    { title: 'The Lumbra Duo — 2 Candle Warmer Lamps', handle: 'lumbra-duo', status: 'DRAFT', price: 84.95, sku: null, inventory: 0 },
  ],
  cogsLanded: 32.30,  // CJ Dropshipping, bodega US (de tus registros)
  // Analytics últimos 30 días
  funnel30d: {
    sessions: 207,
    cartAdditions: 1,
    reachedCheckout: 0,
    completedCheckout: 0,
    conversionRate: 0.0,
  },
  orders: { count: 0, revenue: 0 },
  // Nota: las 207 sesiones y el add-to-cart son tráfico propio del dueño probando la tienda
  // mientras la termina de configurar — NO es tráfico real de mercado. No leer como señal de conversión.
  trafficIsSelfTesting: true,
  // Observaciones automáticas del operador sobre el estado real
  flags: [
    { sev: 'info', t: 'Sin tráfico real todavía', d: 'Las 207 sesiones registradas son del propio dueño probando la tienda mientras la termina de configurar — no reflejan interés real de compradores. La conversión 0% no es diagnóstico todavía; se vuelve relevante hasta que entre tráfico externo (orgánico o pagado).' },
    { sev: 'warn', t: '4 productos casi idénticos como listings separados', d: 'Yellow / Pink / Green / Black están como 4 productos distintos en vez de UN producto con variante de color. Esto divide reviews, confunde a los ads (¿a cuál mandas el tráfico?) y diluye la señal del píxel. Consolídalos en un solo producto con selector de color antes de lanzar tráfico.' },
    { sev: 'warn', t: 'Bundle Duo en DRAFT', d: 'El Duo ($84.95) sube el AOV pero está en borrador — nadie lo ve. Publícalo y preselecciónalo en la PDP para empujar el ticket antes de lanzar.' },
    { sev: 'info', t: 'Etapa: configurando la tienda, aún sin lanzar', d: 'Coherente con la estrategia de arrancar orgánico. El objetivo ahora es terminar la configuración (checkout, tema, políticas) antes de buscar las primeras ventas reales.' },
  ],
};

// Aplica el snapshot al proyecto activo: autocompleta economía y deja el embudo como lectura de dashboard.
function applyShopifySync() {
  const p = (typeof cur === 'function') ? cur() : null;
  if (!p) { toast('Abre un proyecto primero'); return; }
  const s = SHOPIFY_SNAPSHOT;
  const main = s.products.find(x => x.main) || s.products[0];
  // Economía real
  p.economics.price = main.price;
  p.economics.cogs = s.cogsLanded;
  p.economics.ship = 0;
  p.economics.fees = 2.9;
  if (!p.economics.anchor) p.economics.anchor = Math.round(main.price * 1.5 * 100) / 100;
  const duo = s.products.find(x => x.handle === 'lumbra-duo');
  if (duo && !p.economics.aovTarget) p.economics.aovTarget = 60;
  // Guarda el snapshot en el proyecto
  p.shopify = s;
  persist();
  render();
  toast('Tienda sincronizada · economía actualizada');
}
