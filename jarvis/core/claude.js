// ============================================================
// JARVIS · Proveedor de IA: Claude (opcional, mayor calidad)
// Usa el SDK oficial @anthropic-ai/sdk (instalado en la raíz del
// proyecto). Se activa solo si hay clave en secrets.json o en la
// variable ANTHROPIC_API_KEY — si no, Jarvis usa Ollama.
//
// Interfaz de proveedor (la misma que core/ollama.js):
//   disponible(config)  → boolean
//   ejecutarBucle({...}) → Promise<{ texto }>
//
// La memoria se envía como bloque con cache_control para
// aprovechar el prompt caching de la API.
// ============================================================
'use strict';

const path = require('path');
const { RAIZ, leerJSON } = require('./utils');

let Anthropic = null;
try {
  // Resuelve hacia ../node_modules del proyecto raíz.
  Anthropic = require('@anthropic-ai/sdk');
} catch {
  // Sin SDK instalado: este proveedor queda no disponible.
}

const MAX_VUELTAS = 12;

function claveAPI() {
  if (process.env.ANTHROPIC_API_KEY) return process.env.ANTHROPIC_API_KEY;
  const secretos = leerJSON(path.join(RAIZ, 'config', 'secrets.json'), {});
  return secretos.anthropicApiKey && secretos.anthropicApiKey.startsWith('sk-ant')
    ? secretos.anthropicApiKey
    : null;
}

function disponible() {
  return Boolean(Anthropic && claveAPI());
}

let cliente = null;
function obtenerCliente() {
  if (!cliente) cliente = new Anthropic({ apiKey: claveAPI() });
  return cliente;
}

/**
 * Bucle agéntico con Claude (streaming + herramientas).
 *  - system: { base, memoria, fecha } — la memoria lleva cache_control
 *  - defs: herramientas en formato Anthropic (nativo)
 *  - ejecutarHerramienta(nombre, entrada) → { salida, esError }
 */
async function ejecutarBucle({ config, system, defs, mensajes, alTexto, ejecutarHerramienta }) {
  const api = obtenerCliente();
  const modelo = config.modelo || 'claude-opus-4-8';

  const bloquesSystem = [
    { type: 'text', text: system.base },
    { type: 'text', text: system.memoria, cache_control: { type: 'ephemeral' } },
    { type: 'text', text: system.fecha },
  ];

  const historial = mensajes.map((m) => ({ role: m.role, content: m.content }));
  let textoFinal = '';

  for (let vuelta = 0; vuelta < MAX_VUELTAS; vuelta++) {
    const stream = api.messages.stream({
      model: modelo,
      max_tokens: 16000,
      thinking: { type: 'adaptive' },
      system: bloquesSystem,
      tools: defs,
      messages: historial,
    });

    if (alTexto) stream.on('text', (delta) => alTexto(delta));

    const respuesta = await stream.finalMessage();

    for (const bloque of respuesta.content) {
      if (bloque.type === 'text') textoFinal += bloque.text;
    }

    if (respuesta.stop_reason === 'pause_turn') {
      historial.push({ role: 'assistant', content: respuesta.content });
      continue;
    }

    if (respuesta.stop_reason !== 'tool_use') break;

    historial.push({ role: 'assistant', content: respuesta.content });
    const resultados = [];
    for (const bloque of respuesta.content) {
      if (bloque.type !== 'tool_use') continue;
      const { salida, esError } = await ejecutarHerramienta(bloque.name, bloque.input);
      resultados.push({
        type: 'tool_result',
        tool_use_id: bloque.id,
        content: String(salida),
        ...(esError ? { is_error: true } : {}),
      });
    }
    historial.push({ role: 'user', content: resultados });
    textoFinal = ''; // el texto previo era preámbulo; nos quedamos con la vuelta final
  }

  return { texto: textoFinal.trim() };
}

module.exports = { disponible, ejecutarBucle };
