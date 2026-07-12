// ============================================================
// JARVIS · Integración con Shopify (Admin API)
// Opcional: se activa agregando en jarvis/config/secrets.json
//   "shopify": { "dominio": "mitienda.myshopify.com",
//                "tokenAdmin": "shpat_..." }
// El token se crea en Shopify → Configuración → Apps → Desarrollar
// apps → (nueva app) → Admin API, con permisos de LECTURA de
// pedidos y productos. Solo lectura: Jarvis no modifica la tienda.
// ============================================================
'use strict';

const path = require('path');
const { RAIZ, leerJSON } = require('../core/utils');

const VERSION_API = '2024-10';

function credenciales() {
  const secretos = leerJSON(path.join(RAIZ, 'config', 'secrets.json'), {});
  const s = secretos.shopify || {};
  return s.dominio && s.tokenAdmin ? s : null;
}

function disponible() {
  return credenciales() !== null;
}

async function pedirAPI(recurso, parametros = '') {
  const cred = credenciales();
  if (!cred) throw new Error('Shopify no está configurado (falta shopify.dominio/tokenAdmin en secrets.json)');
  const url = `https://${cred.dominio}/admin/api/${VERSION_API}/${recurso}.json${parametros ? '?' + parametros : ''}`;
  const r = await fetch(url, {
    headers: { 'X-Shopify-Access-Token': cred.tokenAdmin, 'Content-Type': 'application/json' },
    signal: AbortSignal.timeout(12_000),
  });
  if (!r.ok) throw new Error(`Shopify respondió ${r.status} en ${recurso}`);
  return r.json();
}

/** Comprobación rápida de conectividad (para la vigilancia). */
async function ping() {
  try {
    await pedirAPI('shop', 'fields=name');
    return true;
  } catch {
    return false;
  }
}

/** Inicio del día LOCAL en ISO (para filtrar pedidos de hoy). */
function inicioDeHoyISO(zonaHoraria) {
  const hoy = new Date().toLocaleDateString('sv', { timeZone: zonaHoraria || undefined });
  // Interpreta las 00:00 locales; Shopify acepta ISO con zona del servidor.
  return new Date(`${hoy}T00:00:00`).toISOString();
}

/** Ventas de hoy: número de pedidos y total facturado. */
async function ventasDeHoy(zonaHoraria) {
  const desde = inicioDeHoyISO(zonaHoraria);
  const datos = await pedirAPI(
    'orders',
    `status=any&created_at_min=${encodeURIComponent(desde)}&fields=id,total_price,currency,financial_status&limit=250`,
  );
  const pedidos = datos.orders || [];
  const total = pedidos.reduce((s, p) => s + parseFloat(p.total_price || 0), 0);
  return {
    pedidos: pedidos.length,
    total: Math.round(total * 100) / 100,
    moneda: pedidos[0]?.currency || 'USD',
  };
}

/** Últimos pedidos (resumen breve para voz/panel). */
async function pedidosRecientes(cantidad = 5) {
  const datos = await pedirAPI(
    'orders',
    `status=any&fields=name,total_price,currency,created_at,financial_status&limit=${Math.min(cantidad, 20)}`,
  );
  return (datos.orders || []).map((p) => ({
    numero: p.name,
    total: p.total_price,
    moneda: p.currency,
    estado: p.financial_status,
    creado: p.created_at,
  }));
}

/** Variantes con inventario agotado (≤ 0). */
async function productosSinStock() {
  const datos = await pedirAPI('products', 'fields=title,variants&limit=100');
  const agotados = [];
  for (const producto of datos.products || []) {
    for (const v of producto.variants || []) {
      if (v.inventory_management && Number(v.inventory_quantity) <= 0) {
        agotados.push({
          titulo: producto.title + (v.title && v.title !== 'Default Title' ? ` (${v.title})` : ''),
          cantidad: Number(v.inventory_quantity),
        });
      }
    }
  }
  return agotados;
}

module.exports = { disponible, ping, ventasDeHoy, pedidosRecientes, productosSinStock };
