// ============================================================
// JARVIS · Programador (tareas automáticas + vigilancia)
// El equivalente nativo a un flujo de n8n sencillo: tareas que
// corren a una hora fija cada día, y comprobaciones de
// emergencia periódicas. Sin dependencias, todo local.
//
// Configuración: config.json → "programador".tareas[]
//   { nombre, tipo: "automatizacion", objetivo: "<script>",
//     hora: "08:00", notificar: true, hablar: true, documento: true }
//
// El estado (qué corrió hoy) persiste en data/scheduler.json para
// no repetir tareas si el servidor se reinicia.
// ============================================================
'use strict';

const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');
const { RAIZ, leerJSON, escribirJSON, rutaSegura } = require('./utils');
const store = require('./store');
const logger = require('./logger');
const shopify = require('../integrations/shopify');

const CONFIG = leerJSON(path.join(RAIZ, 'config', 'config.json'), {});
const PROG = CONFIG.programador || { habilitado: false, tareas: [] };
const RUTA_ESTADO = path.join(RAIZ, 'data', 'scheduler.json');
const DIR_AUTOMATIZACIONES = path.join(RAIZ, 'automations');
const DIR_DOCS = path.join(RAIZ, 'docs', 'generados');

const TICK_TAREAS_MS = 30_000;       // revisa la hora cada 30 s
const TICK_VIGILANCIA_MS = 5 * 60_000; // emergencias cada 5 min

// ---------- Utilidades de fecha LOCAL (nunca toISOString/UTC) ----------

function fechaLocal() {
  // 'sv' produce YYYY-MM-DD; respetamos la zona horaria configurada.
  return new Date().toLocaleDateString('sv', { timeZone: CONFIG.zonaHoraria || undefined });
}

function horaLocal() {
  return new Date().toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: CONFIG.zonaHoraria || undefined,
  });
}

// ---------- Estado persistente ----------

function estado() {
  return leerJSON(RUTA_ESTADO, { corridasHoy: {}, fecha: fechaLocal(), alertas: {} });
}

function guardarEstado(e) {
  escribirJSON(RUTA_ESTADO, e);
}

// ---------- Ejecución de tareas programadas ----------

function correrAutomatizacion(nombre) {
  return new Promise((resolve, reject) => {
    const limpio = String(nombre).replace(/[^a-z0-9\-_]/gi, '');
    const script = path.join(DIR_AUTOMATIZACIONES, `${limpio}.js`);
    if (!fs.existsSync(script)) {
      reject(new Error(`No existe la automatización "${limpio}"`));
      return;
    }
    execFile(process.execPath, [script], { timeout: 120_000, cwd: RAIZ }, (err, stdout, stderr) => {
      if (err) reject(new Error(`${err.message}\n${stderr || ''}`.trim()));
      else resolve(stdout.trim());
    });
  });
}

async function ejecutarTarea(tarea) {
  logger.info('programador', `Ejecutando tarea programada: ${tarea.nombre}`);
  try {
    const salida = await correrAutomatizacion(tarea.objetivo || tarea.nombre);

    if (tarea.documento) {
      fs.mkdirSync(DIR_DOCS, { recursive: true });
      const ruta = rutaSegura(DIR_DOCS, `${fechaLocal()}-${tarea.nombre}.md`);
      fs.writeFileSync(ruta, salida + '\n', 'utf8');
    }

    if (tarea.notificar !== false) {
      // La primera línea como titular; el resto queda en el documento/log.
      const titular = salida.split('\n')[0].slice(0, 180) || `Tarea ${tarea.nombre} completada`;
      store.notificar(titular, 'info', { hablar: Boolean(tarea.hablar), detalle: salida.slice(0, 1500) });
    }
    logger.info('programador', `Tarea ${tarea.nombre} completada`);
  } catch (e) {
    logger.error('programador', `Tarea ${tarea.nombre} falló: ${e.message}`);
    store.notificar(`⚠ La automatización "${tarea.nombre}" falló: ${e.message.slice(0, 140)}`, 'alerta', { hablar: true });
  }
}

function tickTareas() {
  const e = estado();
  const hoy = fechaLocal();
  if (e.fecha !== hoy) {
    e.fecha = hoy;
    e.corridasHoy = {};
  }
  const ahora = horaLocal();

  for (const tarea of PROG.tareas || []) {
    if (!tarea.hora || e.corridasHoy[tarea.nombre]) continue;
    // Dispara cuando la hora local alcanza (o pasa) la programada.
    if (ahora >= tarea.hora) {
      e.corridasHoy[tarea.nombre] = ahora;
      guardarEstado(e);
      ejecutarTarea(tarea); // asíncrono; no bloquea el tick
    }
  }
  guardarEstado(e);
}

// ---------- Vigilancia de emergencias ----------
// Cada condición notifica UNA vez al entrar en fallo y otra al
// recuperarse (sin spam), usando data/scheduler.json → alertas.

async function vigilancia() {
  const e = estado();
  e.alertas = e.alertas || {};

  async function condicion(clave, textoFallo, textoRecuperado, comprobar) {
    let enFallo;
    try {
      enFallo = await comprobar();
    } catch {
      enFallo = true;
    }
    const estaba = Boolean(e.alertas[clave]);
    if (enFallo && !estaba) {
      e.alertas[clave] = fechaLocal();
      store.notificar(`🚨 ${textoFallo}`, 'alerta', { hablar: true });
      logger.aviso('vigilancia', textoFallo);
    } else if (!enFallo && estaba) {
      delete e.alertas[clave];
      store.notificar(`✅ ${textoRecuperado}`, 'exito');
      logger.info('vigilancia', textoRecuperado);
    }
  }

  // Drop-Meta presente en disco
  const dirDropMeta = path.resolve(RAIZ, CONFIG.dropMeta?.ruta || '../drop-meta');
  await condicion(
    'dropmeta',
    'Drop-Meta no está disponible en disco.',
    'Drop-Meta vuelve a estar disponible.',
    async () => !fs.existsSync(path.join(dirDropMeta, 'index.html')),
  );

  // Shopify accesible (solo si está configurado)
  if (shopify.disponible()) {
    await condicion(
      'shopify',
      'No puedo conectar con Shopify.',
      'Conexión con Shopify restablecida.',
      async () => !(await shopify.ping()),
    );

    // Inventario agotado (avisa una vez por día)
    const claveStock = `stock-${fechaLocal()}`;
    if (!e.alertas[claveStock]) {
      try {
        const agotados = await shopify.productosSinStock();
        if (agotados.length > 0) {
          e.alertas[claveStock] = true;
          store.notificar(
            `🚨 ${agotados.length} producto(s) sin inventario: ${agotados.slice(0, 3).map((p) => p.titulo).join(', ')}${agotados.length > 3 ? '…' : ''}`,
            'alerta',
            { hablar: true },
          );
        }
      } catch {
        /* la condición 'shopify' ya cubre el fallo de conexión */
      }
    }
  }

  guardarEstado(e);
}

// ---------- Arranque ----------

function iniciar() {
  if (!PROG.habilitado) {
    logger.info('programador', 'Programador deshabilitado en config.json');
    return;
  }
  setInterval(tickTareas, TICK_TAREAS_MS);
  setInterval(() => vigilancia().catch((e) => logger.error('vigilancia', e.message)), TICK_VIGILANCIA_MS);
  // Primera vigilancia a los 20 s del arranque (deja respirar al servidor).
  setTimeout(() => vigilancia().catch((e) => logger.error('vigilancia', e.message)), 20_000);
  logger.info(
    'programador',
    `Activo: ${(PROG.tareas || []).length} tarea(s) programada(s) — ${(PROG.tareas || [])
      .map((t) => `${t.nombre}@${t.hora}`)
      .join(', ') || 'ninguna'}`,
  );
}

/** Resumen para /api/status y el dashboard. */
function resumen() {
  const e = estado();
  return {
    habilitado: Boolean(PROG.habilitado),
    tareas: (PROG.tareas || []).map((t) => ({
      nombre: t.nombre,
      hora: t.hora,
      corrioHoy: Boolean(e.corridasHoy[t.nombre]),
    })),
    alertasActivas: Object.keys(e.alertas || {}).filter((k) => !k.startsWith('stock-')),
  };
}

module.exports = { iniciar, resumen, ejecutarTarea };
