// ============================================================
// JARVIS · Motor de IA unificado (fachada de proveedores)
//
// Aquí vive el "interruptor" de proveedor:
//   config.json → ia.proveedor:
//     "auto"   → Claude si hay clave configurada; si no, Ollama (por defecto)
//     "claude" → fuerza Claude (requiere clave)
//     "ollama" → fuerza Ollama (requiere el servidor local corriendo)
//
// Toda la lógica común vive aquí — agentes, memoria en el system
// prompt, delegación CEO→agentes y ejecución de herramientas —
// de modo que cambiar de proveedor NO toca ninguna otra parte
// del proyecto: basta con agregar/quitar la clave o editar config.
// ============================================================
'use strict';

const path = require('path');
const { RAIZ, leerJSON } = require('./utils');
const memoria = require('./memory');
const agentes = require('../agents/agents');
const herramientas = require('../tools/tools');
const logger = require('./logger');
const claude = require('./claude');
const ollama = require('./ollama');

const CONFIG = leerJSON(path.join(RAIZ, 'config', 'config.json'), {});
const IA = CONFIG.ia || {};
const MODO = IA.proveedor || 'auto';
const CFG_CLAUDE = IA.claude || { modelo: CONFIG.modelo || 'claude-opus-4-8' };
const CFG_OLLAMA = IA.ollama || { url: 'http://127.0.0.1:11434', modelo: 'llama3.1' };

/** Decide qué proveedor usar ahora mismo. Devuelve 'claude' | 'ollama' | null. */
async function proveedorActivo() {
  if (MODO === 'claude') return claude.disponible() ? 'claude' : null;
  if (MODO === 'ollama') return (await ollama.disponible(CFG_OLLAMA)) ? 'ollama' : null;
  // auto: la clave de Claude manda; si no hay, Ollama local.
  if (claude.disponible()) return 'claude';
  if (await ollama.disponible(CFG_OLLAMA)) return 'ollama';
  return null;
}

/** Información para /api/status y el dashboard. */
async function info() {
  const proveedor = await proveedorActivo();
  return {
    disponible: proveedor !== null,
    proveedor,
    modelo: proveedor === 'claude' ? CFG_CLAUDE.modelo : proveedor === 'ollama' ? CFG_OLLAMA.modelo : null,
    modoConfigurado: MODO,
  };
}

/** System prompt compartido: identidad + memoria + fecha. */
function construirSystem(agente) {
  const fecha = new Date().toLocaleDateString('es-MX', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    timeZone: CONFIG.zonaHoraria || undefined,
  });
  return {
    base: agente.system,
    memoria: `## Memoria permanente de Jarvis (consúltala antes de responder)\n\n${memoria.volcadoCompleto()}`,
    fecha: `Fecha actual: ${fecha}.`,
  };
}

/**
 * Conversación con un agente, resolviendo herramientas y delegación,
 * con el proveedor que esté activo. Contrato estable para server.js:
 *   conversar({agenteId, mensajes, alTexto, alEvento}) → {texto, agente, proveedor}
 */
async function conversar({ agenteId = 'ceo', mensajes, alTexto, alEvento, profundidad = 0 }) {
  const proveedor = await proveedorActivo();
  if (!proveedor) throw new Error('No hay proveedor de IA disponible (ni clave de Claude ni Ollama en línea).');

  const agente = agentes.obtener(agenteId) || agentes.obtener('ceo');
  const puedeDelegar = agente.id === 'ceo' && profundidad === 0;
  const defs = herramientas.definicionesPara(agente, puedeDelegar);

  // La delegación pasa por esta misma fachada: los sub-agentes usan
  // el mismo proveedor sin que a los agentes les importe cuál es.
  const delegar = async (subId, encargo) => {
    const sub = agentes.obtener(subId);
    if (!sub || sub.id === 'ceo') return `Agente no válido: ${subId}`;
    if (alEvento) alEvento({ tipo: 'delegacion', agente: sub.id, nombre: sub.nombre });
    const resultado = await conversar({
      agenteId: sub.id,
      mensajes: [{ role: 'user', content: encargo }],
      alEvento,
      profundidad: profundidad + 1,
    });
    return resultado.texto || '(sin respuesta del agente)';
  };

  const ejecutarHerramienta = async (nombre, entrada) => {
    if (alEvento) alEvento({ tipo: 'herramienta', nombre, agente: agente.id });
    try {
      const salida = await herramientas.ejecutar(nombre, entrada, { delegar });
      return { salida, esError: false };
    } catch (e) {
      logger.error('herramientas', `${nombre}: ${e.message}`);
      return { salida: `Error: ${e.message}`, esError: true };
    }
  };

  const comun = {
    system: construirSystem(agente),
    defs,
    mensajes,
    alTexto: profundidad === 0 ? alTexto : null,
    ejecutarHerramienta,
  };

  const resultado =
    proveedor === 'claude'
      ? await claude.ejecutarBucle({ config: CFG_CLAUDE, ...comun })
      : await ollama.ejecutarBucle({ config: CFG_OLLAMA, ...comun });

  return { texto: resultado.texto, agente: agente.id, proveedor };
}

module.exports = { proveedorActivo, info, conversar };
