// ============================================================
// JARVIS · Automatización: Daily CEO Report
// El resumen ejecutivo del día. El programador lo corre a las
// 8:00 (config.json → programador), lo guarda como documento,
// lo notifica en el dashboard y Jarvis lo lee en voz alta.
//
// También se puede pedir a mano: «ejecuta la automatización
// reporte-ceo» o correrlo directo:
//   node jarvis/automations/reporte-ceo.js
//
// Funciona con lo que haya disponible: si Shopify está
// configurado incluye ventas reales; si no, lo indica.
// ============================================================
'use strict';

const path = require('path');
const { RAIZ, leerJSON } = require('../core/utils');
const store = require('../core/store');
const memoria = require('../core/memory');
const shopify = require('../integrations/shopify');

const CONFIG = leerJSON(path.join(RAIZ, 'config', 'config.json'), {});

function fechaLocal() {
  return new Date().toLocaleDateString('sv', { timeZone: CONFIG.zonaHoraria || undefined });
}

function fechaLegible() {
  return new Date().toLocaleDateString('es-MX', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    timeZone: CONFIG.zonaHoraria || undefined,
  });
}

/** Primeras líneas útiles de un archivo de memoria (sin el título). */
function extractoMemoria(nombre, maxLineas = 4) {
  try {
    return memoria
      .leer(nombre)
      .split('\n')
      .map((l) => l.trim())
      .filter((l) => l && !l.startsWith('#') && !l.startsWith('<!--') && !l.startsWith('_('))
      .slice(0, maxLineas);
  } catch {
    return [];
  }
}

async function principal() {
  const hoy = fechaLocal();
  const lineas = [`Buenos días, señor. Reporte del ${fechaLegible()}.`, ''];

  // ── Ventas (Shopify) ──
  if (shopify.disponible()) {
    try {
      const v = await shopify.ventasDeHoy(CONFIG.zonaHoraria);
      lineas.push(`## Ventas`, `- Pedidos de hoy: ${v.pedidos}`, `- Facturado: ${v.total} ${v.moneda}`);
      const agotados = await shopify.productosSinStock();
      if (agotados.length) {
        lineas.push(`- ⚠ Sin inventario: ${agotados.map((p) => p.titulo).slice(0, 5).join(', ')}`);
      }
    } catch (e) {
      lineas.push(`## Ventas`, `- No pude leer Shopify: ${e.message}`);
    }
  } else {
    lineas.push(`## Ventas`, `- Shopify sin configurar (agregue shopify.dominio y tokenAdmin en secrets.json).`);
  }
  lineas.push('');

  // ── Tareas ──
  const tareas = store.listarTareas();
  const pendientes = tareas.filter((t) => !t.hecha);
  const deHoy = pendientes.filter((t) => t.fecha === hoy);
  const altas = pendientes.filter((t) => t.prioridad === 'alta');
  lineas.push(`## Tareas`);
  lineas.push(`- Pendientes: ${pendientes.length}${altas.length ? ` (${altas.length} de prioridad alta)` : ''}`);
  if (deHoy.length) lineas.push(`- Para hoy: ${deHoy.map((t) => t.titulo).join(' · ')}`);
  else lineas.push(`- Para hoy: nada con fecha de hoy.`);
  lineas.push('');

  // ── Objetivos y candidatos (memoria) ──
  const objetivos = extractoMemoria('objetivos', 3);
  if (objetivos.length) lineas.push(`## Objetivos vigentes`, ...objetivos.map((o) => `- ${o.replace(/^[-*]\s*/, '')}`), '');

  const candidatos = extractoMemoria('productos', 5).filter((l) => /candidat|LUMBRA|lámpara|producto/i.test(l));
  if (candidatos.length) lineas.push(`## Productos en juego`, ...candidatos.map((c) => `- ${c.replace(/^[-*]\s*/, '')}`), '');

  // ── Cierre ──
  const foco = altas[0] || deHoy[0] || pendientes[0];
  lineas.push(`## Foco sugerido del día`);
  lineas.push(foco ? `- ${foco.titulo}` : `- Sin tareas: buen momento para cazar producto nuevo con el Product Hunter.`);

  console.log(lineas.join('\n'));
}

principal().catch((e) => {
  console.error(`Error en el reporte: ${e.message}`);
  process.exit(1);
});
