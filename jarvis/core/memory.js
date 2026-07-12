// ============================================================
// JARVIS · Sistema de memoria
// La memoria vive en jarvis/memory/*.md — archivos Markdown
// legibles que el usuario puede editar a mano. Jarvis los
// consulta SIEMPRE antes de responder (se inyectan en el
// system prompt) y puede escribir en ellos vía herramientas.
// ============================================================
'use strict';

const fs = require('fs');
const path = require('path');
const { RAIZ, rutaSegura, ahora } = require('./utils');

const DIR_MEMORIA = path.join(RAIZ, 'memory');

// Archivos canónicos: si no existen, se crean con una plantilla
// para que Jarvis y el usuario sepan qué va en cada uno.
const PLANTILLAS = {
  'usuario.md': '# Usuario\n\nQuién es el operador: nombre, rol, preferencias de trabajo y de comunicación.\n',
  'negocio.md': '# Negocio\n\nModelo de negocio, marcas activas (p. ej. LUMBRA), tiendas, canales de venta.\n',
  'objetivos.md': '# Objetivos\n\nMetas de corto y largo plazo, con fechas cuando existan.\n',
  'estrategias.md': '# Estrategias\n\nEstrategias vigentes de producto, tráfico, precios y contenido.\n',
  'proveedores.md': '# Proveedores\n\nProveedores evaluados: contacto, tiempos de envío, costos, notas de calidad.\n',
  'productos.md': '# Productos\n\nProductos activos y candidatos, con estado y aprendizajes por producto.\n',
  'anuncios.md': '# Anuncios\n\nCampañas y creativos: ángulos probados, hooks, métricas relevantes.\n',
  'errores.md': '# Errores\n\nErrores cometidos y su causa raíz, para no repetirlos.\n',
  'aprendizajes.md': '# Aprendizajes\n\nLecciones validadas que deben influir en decisiones futuras.\n',
};

function asegurarMemoria() {
  fs.mkdirSync(DIR_MEMORIA, { recursive: true });
  for (const [nombre, contenido] of Object.entries(PLANTILLAS)) {
    const ruta = path.join(DIR_MEMORIA, nombre);
    if (!fs.existsSync(ruta)) fs.writeFileSync(ruta, contenido, 'utf8');
  }
}

function listar() {
  asegurarMemoria();
  return fs
    .readdirSync(DIR_MEMORIA)
    .filter((n) => n.endsWith('.md'))
    .map((nombre) => {
      const stat = fs.statSync(path.join(DIR_MEMORIA, nombre));
      return { nombre, bytes: stat.size, modificado: stat.mtime.toISOString() };
    });
}

function normalizar(nombre) {
  let limpio = String(nombre).trim().toLowerCase();
  if (!limpio.endsWith('.md')) limpio += '.md';
  return limpio;
}

function leer(nombre) {
  asegurarMemoria();
  const ruta = rutaSegura(DIR_MEMORIA, normalizar(nombre));
  return fs.readFileSync(ruta, 'utf8');
}

function escribir(nombre, contenido) {
  asegurarMemoria();
  const ruta = rutaSegura(DIR_MEMORIA, normalizar(nombre));
  fs.writeFileSync(ruta, String(contenido), 'utf8');
}

function anexar(nombre, texto) {
  asegurarMemoria();
  const ruta = rutaSegura(DIR_MEMORIA, normalizar(nombre));
  const sello = `\n\n<!-- ${ahora()} -->\n${String(texto).trim()}\n`;
  fs.appendFileSync(ruta, sello, 'utf8');
}

/**
 * Devuelve toda la memoria como un bloque de texto para el system
 * prompt. Se mantiene estable entre peticiones para aprovechar el
 * prompt caching de la API (el contenido solo cambia cuando se
 * escribe memoria).
 */
function volcadoCompleto() {
  asegurarMemoria();
  const partes = [];
  for (const { nombre } of listar()) {
    const contenido = leer(nombre).trim();
    partes.push(`### ${nombre}\n${contenido}`);
  }
  return partes.join('\n\n');
}

module.exports = { asegurarMemoria, listar, leer, escribir, anexar, volcadoCompleto, DIR_MEMORIA };
