// ============================================================
// JARVIS · Proveedor de IA: Ollama (local, por defecto)
// Habla con el servidor local de Ollama (http://127.0.0.1:11434)
// usando fetch nativo — sin dependencias. Soporta tool calling;
// si el modelo cargado no soporta herramientas, reintenta sin
// ellas para que Jarvis siga conversando.
//
// Interfaz de proveedor (la misma que core/claude.js):
//   disponible(config)  → Promise<boolean>
//   ejecutarBucle({...}) → Promise<{ texto }>
// ============================================================
'use strict';

const logger = require('./logger');

const MAX_VUELTAS = 12;
const TIMEOUT_MS = 5 * 60 * 1000; // los modelos locales pueden tardar

// La comprobación de disponibilidad se cachea 30 s para no añadir
// latencia a cada refresco del dashboard.
let cacheDisponible = { valor: false, hasta: 0 };

async function disponible(config) {
  const ahora = Date.now();
  if (ahora < cacheDisponible.hasta) return cacheDisponible.valor;
  let valor = false;
  try {
    const r = await fetch(`${config.url}/api/tags`, { signal: AbortSignal.timeout(1500) });
    valor = r.ok;
  } catch {
    valor = false;
  }
  cacheDisponible = { valor, hasta: ahora + 30_000 };
  return valor;
}

/** Convierte las herramientas (formato Anthropic) al formato de Ollama. */
function convertirHerramientas(defs) {
  return defs.map((d) => ({
    type: 'function',
    function: {
      name: d.name,
      description: d.description,
      parameters: d.input_schema,
    },
  }));
}

async function chat(config, cuerpo) {
  const r = await fetch(`${config.url}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...cuerpo, stream: false }),
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (!r.ok) {
    const detalle = await r.text().catch(() => '');
    throw new Error(`Ollama respondió ${r.status}: ${detalle.slice(0, 300)}`);
  }
  return r.json();
}

/**
 * Bucle agéntico con Ollama. Mismo contrato que el proveedor Claude:
 *  - system: { base, memoria, fecha } (se unen en un solo system prompt)
 *  - defs: herramientas en formato Anthropic (se convierten)
 *  - ejecutarHerramienta(nombre, entrada) → { salida, esError }
 *  - alTexto(delta): Ollama trabaja sin streaming (el tool calling en
 *    streaming es frágil entre versiones); el texto llega en un solo delta.
 */
async function ejecutarBucle({ config, system, defs, mensajes, alTexto, ejecutarHerramienta }) {
  const modelo = config.modelo || 'llama3.1';
  const systemUnido = [system.base, system.memoria, system.fecha].join('\n\n');

  const historial = [
    { role: 'system', content: systemUnido },
    ...mensajes.map((m) => ({ role: m.role, content: String(m.content) })),
  ];

  let herramientas = defs.length ? convertirHerramientas(defs) : undefined;
  let textoFinal = '';

  for (let vuelta = 0; vuelta < MAX_VUELTAS; vuelta++) {
    let respuesta;
    try {
      respuesta = await chat(config, {
        model: modelo,
        messages: historial,
        ...(herramientas ? { tools: herramientas } : {}),
      });
    } catch (e) {
      // Modelos sin soporte de herramientas (p. ej. algunos pequeños):
      // reintentar la conversación sin tools en vez de fallar.
      if (herramientas && /tool/i.test(e.message)) {
        logger.aviso('ollama', `El modelo ${modelo} no soporta herramientas; continuo sin ellas.`);
        herramientas = undefined;
        vuelta--;
        continue;
      }
      throw e;
    }

    const msg = respuesta.message || {};

    if (Array.isArray(msg.tool_calls) && msg.tool_calls.length > 0) {
      historial.push(msg);
      for (const llamada of msg.tool_calls) {
        const nombre = llamada.function?.name;
        const entrada = llamada.function?.arguments || {};
        const { salida } = await ejecutarHerramienta(nombre, entrada);
        historial.push({ role: 'tool', tool_name: nombre, content: String(salida) });
      }
      continue;
    }

    textoFinal = (msg.content || '').trim();
    break;
  }

  if (textoFinal && alTexto) alTexto(textoFinal);
  return { texto: textoFinal };
}

module.exports = { disponible, ejecutarBucle };
