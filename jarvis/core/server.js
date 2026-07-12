// ============================================================
// JARVIS · Servidor principal
// - Sirve el dashboard (jarvis/dashboard) en /
// - Sirve Drop-Meta (../drop-meta) en /drop-meta/
// - Expone la API REST + el chat en streaming (SSE)
//
// Arranque:  node jarvis/core/server.js
// ============================================================
'use strict';

const http = require('http');
const os = require('os');
const path = require('path');
const fs = require('fs');

const {
  RAIZ,
  RAIZ_PROYECTO,
  leerJSON,
  cuerpoJSON,
  responderJSON,
  iniciarSSE,
  servirEstatico,
} = require('./utils');
const memoria = require('./memory');
const store = require('./store');
const logger = require('./logger');
const ia = require('./ia');
const localbrain = require('./localbrain');
const agentes = require('../agents/agents');
const herramientas = require('../tools/tools');
const clima = require('../integrations/weather');

const CONFIG = leerJSON(path.join(RAIZ, 'config', 'config.json'), {});
const PUERTO = Number(process.env.JARVIS_PORT || CONFIG.puerto || 8200);
const DIR_DASHBOARD = path.join(RAIZ, 'dashboard');
const DIR_DROPMETA = path.resolve(RAIZ, CONFIG.dropMeta?.ruta || '../drop-meta');
const INICIO = Date.now();

// Conversaciones en curso (por sesión del navegador), solo en memoria RAM.
const sesiones = new Map();
function historialDeSesion(id) {
  if (!sesiones.has(id)) sesiones.set(id, []);
  return sesiones.get(id);
}

// ---------- Endpoints de la API ----------

async function apiEstado(res) {
  let internet = false;
  try {
    const r = await fetch('https://www.google.com/generate_204', { signal: AbortSignal.timeout(4000) });
    internet = r.status === 204 || r.ok;
  } catch {
    internet = false;
  }
  responderJSON(res, 200, {
    nombre: CONFIG.nombre || 'Jarvis',
    version: '1.0.0',
    encendidoDesde: new Date(INICIO).toISOString(),
    segundosActivo: Math.round((Date.now() - INICIO) / 1000),
    internet,
    ia: await ia.info(),
    sistema: {
      plataforma: `${os.type()} ${os.release()}`,
      cpus: os.cpus().length,
      memoriaLibreMB: Math.round(os.freemem() / 1024 / 1024),
      memoriaTotalMB: Math.round(os.totalmem() / 1024 / 1024),
      cargaProceso: Math.round(process.memoryUsage().rss / 1024 / 1024),
    },
    dropMeta: { disponible: fs.existsSync(path.join(DIR_DROPMETA, 'index.html')), url: '/drop-meta/' },
    agentes: agentes.listar().length,
    automatizaciones: herramientas.listarAutomatizaciones(),
  });
}

async function apiChat(req, res) {
  const { mensaje, agenteId, sesion, origen } = await cuerpoJSON(req);
  if (!mensaje || !String(mensaje).trim()) {
    responderJSON(res, 400, { error: 'Falta el campo "mensaje"' });
    return;
  }
  const sse = iniciarSSE(res);
  const textoUsuario = String(mensaje).trim();

  // 1) Intento local (instantáneo, sin costo). El CEO por IA solo se usa
  //    si el comando no es una intención básica o si se pidió un agente.
  if (!agenteId || agenteId === 'ceo') {
    const local = localbrain.resolver(textoUsuario);
    if (local && (local.texto || local.accion)) {
      if (local.accion) sse.enviar({ tipo: 'accion', accion: local.accion });
      if (local.texto) sse.enviar({ tipo: 'texto', delta: local.texto });
      sse.enviar({ tipo: 'listo', texto: local.texto || '', agente: 'local' });
      sse.cerrar();
      store.registrarComando(
        { origen: origen || 'texto', comando: textoUsuario, respuesta: local.texto || '(acción)', agente: 'local' },
        CONFIG.historialMaximo,
      );
      return;
    }
  }

  // 2) Motor de IA (Claude u Ollama, según el interruptor de config).
  if (!(await ia.proveedorActivo())) {
    const aviso =
      'No tengo motor de inteligencia disponible, señor. Instale Ollama (ollama.com) y ejecute "ollama pull llama3.1", o configure su clave de Claude en jarvis/config/secrets.json. Mientras tanto atiendo comandos básicos: hora, fecha, clima, tareas y Drop-Meta.';
    sse.enviar({ tipo: 'texto', delta: aviso });
    sse.enviar({ tipo: 'listo', texto: aviso, agente: 'local' });
    sse.cerrar();
    return;
  }

  const historial = historialDeSesion(sesion || 'default');
  historial.push({ role: 'user', content: textoUsuario });

  try {
    const resultado = await ia.conversar({
      agenteId: agenteId || 'ceo',
      mensajes: historial,
      alTexto: (delta) => sse.enviar({ tipo: 'texto', delta }),
      alEvento: (ev) => sse.enviar(ev),
    });
    historial.push({ role: 'assistant', content: resultado.texto || '(sin texto)' });
    // Mantener el contexto acotado (las últimas 20 vueltas).
    if (historial.length > 40) historial.splice(0, historial.length - 40);

    sse.enviar({ tipo: 'listo', texto: resultado.texto, agente: resultado.agente });
    store.registrarComando(
      { origen: origen || 'texto', comando: textoUsuario, respuesta: resultado.texto, agente: resultado.agente },
      CONFIG.historialMaximo,
    );
  } catch (e) {
    logger.error('chat', e.message);
    sse.enviar({ tipo: 'error', mensaje: `Hubo un problema con la IA: ${e.message}` });
  }
  sse.cerrar();
}

async function enrutarAPI(req, res, ruta) {
  const metodo = req.method;

  // --- estado / clima / config ---
  if (ruta === '/api/status' && metodo === 'GET') return apiEstado(res);

  if (ruta === '/api/weather' && metodo === 'GET') {
    try {
      responderJSON(res, 200, await clima.obtener());
    } catch (e) {
      responderJSON(res, 502, { error: e.message });
    }
    return;
  }

  if (ruta === '/api/config' && metodo === 'GET') {
    // Solo la parte que el dashboard necesita (nunca secretos).
    const { nombre, saludo, musicaBienvenida, voz, aplausos, dropMeta, ciudad } = CONFIG;
    const estadoIA = await ia.info();
    responderJSON(res, 200, { nombre, saludo, musicaBienvenida, voz, aplausos, dropMeta: { abrirAlActivar: dropMeta?.abrirAlActivar ?? true }, ciudad, ia: estadoIA });
    return;
  }

  // --- agentes ---
  if (ruta === '/api/agents' && metodo === 'GET') {
    responderJSON(res, 200, agentes.listar());
    return;
  }

  // --- chat ---
  if (ruta === '/api/chat' && metodo === 'POST') return apiChat(req, res);

  // --- memoria ---
  if (ruta === '/api/memory' && metodo === 'GET') {
    responderJSON(res, 200, memoria.listar());
    return;
  }
  const memMatch = ruta.match(/^\/api\/memory\/([a-z0-9\-_.]+)$/i);
  if (memMatch) {
    const nombre = decodeURIComponent(memMatch[1]);
    if (metodo === 'GET') {
      try {
        responderJSON(res, 200, { nombre, contenido: memoria.leer(nombre) });
      } catch {
        responderJSON(res, 404, { error: 'No existe ese archivo de memoria' });
      }
      return;
    }
    if (metodo === 'PUT') {
      const { contenido } = await cuerpoJSON(req);
      memoria.escribir(nombre, contenido ?? '');
      responderJSON(res, 200, { ok: true });
      return;
    }
  }

  // --- tareas ---
  if (ruta === '/api/tasks' && metodo === 'GET') {
    responderJSON(res, 200, store.listarTareas());
    return;
  }
  if (ruta === '/api/tasks' && metodo === 'POST') {
    const datos = await cuerpoJSON(req);
    try {
      responderJSON(res, 201, store.crearTarea(datos));
    } catch (e) {
      responderJSON(res, 400, { error: e.message });
    }
    return;
  }
  const tareaMatch = ruta.match(/^\/api\/tasks\/([a-z0-9]+)$/i);
  if (tareaMatch) {
    const id = tareaMatch[1];
    try {
      if (metodo === 'PATCH') {
        responderJSON(res, 200, store.actualizarTarea(id, await cuerpoJSON(req)));
        return;
      }
      if (metodo === 'DELETE') {
        store.borrarTarea(id);
        responderJSON(res, 200, { ok: true });
        return;
      }
    } catch (e) {
      responderJSON(res, 404, { error: e.message });
      return;
    }
  }

  // --- notificaciones ---
  if (ruta === '/api/notifications' && metodo === 'GET') {
    responderJSON(res, 200, store.listarNotificaciones());
    return;
  }
  if (ruta === '/api/notifications/read' && metodo === 'POST') {
    responderJSON(res, 200, store.marcarLeidas());
    return;
  }

  // --- historial de comandos ---
  if (ruta === '/api/history' && metodo === 'GET') {
    responderJSON(res, 200, store.listarHistorial());
    return;
  }

  responderJSON(res, 404, { error: `Sin ruta: ${metodo} ${ruta}` });
}

// ---------- Servidor HTTP ----------

const servidor = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PUERTO}`);
  const ruta = url.pathname;

  try {
    if (ruta.startsWith('/api/')) {
      await enrutarAPI(req, res, ruta);
      return;
    }

    // Drop-Meta montado bajo /drop-meta/
    if (ruta === '/drop-meta') {
      res.writeHead(302, { Location: '/drop-meta/' });
      res.end();
      return;
    }
    if (ruta.startsWith('/drop-meta/')) {
      const relativa = ruta.slice('/drop-meta/'.length) || 'index.html';
      if (servirEstatico(res, DIR_DROPMETA, relativa)) return;
      responderJSON(res, 404, { error: 'Drop-Meta: archivo no encontrado' });
      return;
    }

    // Dashboard de Jarvis
    const relativa = ruta === '/' ? 'index.html' : ruta.slice(1);
    if (servirEstatico(res, DIR_DASHBOARD, relativa)) return;

    responderJSON(res, 404, { error: 'No encontrado' });
  } catch (e) {
    logger.error('servidor', `${req.method} ${ruta}: ${e.message}`);
    if (!res.headersSent) responderJSON(res, 500, { error: e.message });
    else res.end();
  }
});

memoria.asegurarMemoria();
servidor.listen(PUERTO, async () => {
  logger.info('servidor', `Jarvis en línea → http://localhost:${PUERTO}`);
  logger.info('servidor', `Drop-Meta servido en → http://localhost:${PUERTO}/drop-meta/`);
  const estadoIA = await ia.info();
  logger.info(
    'servidor',
    estadoIA.disponible
      ? `Motor IA: ${estadoIA.proveedor} (${estadoIA.modelo})`
      : 'Motor IA: ninguno — instale Ollama o configure la clave de Claude (modo local básico activo)',
  );
});
