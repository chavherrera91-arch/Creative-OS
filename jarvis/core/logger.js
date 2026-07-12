// ============================================================
// JARVIS · Registro (logs)
// Un archivo por día en jarvis/logs/. Formato: JSON Lines,
// fácil de inspeccionar y de procesar con cualquier herramienta.
// ============================================================
'use strict';

const fs = require('fs');
const path = require('path');
const { RAIZ, ahora } = require('./utils');

const DIR_LOGS = path.join(RAIZ, 'logs');

function rutaDeHoy() {
  // Fecha local para que el archivo del día coincida con el día real del usuario.
  const d = new Date();
  const dia = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  return path.join(DIR_LOGS, `jarvis-${dia}.log`);
}

function escribir(nivel, modulo, mensaje, extra) {
  const linea = JSON.stringify({ t: ahora(), nivel, modulo, mensaje, ...(extra ? { extra } : {}) });
  try {
    fs.mkdirSync(DIR_LOGS, { recursive: true });
    fs.appendFileSync(rutaDeHoy(), linea + '\n', 'utf8');
  } catch {
    // El log nunca debe tumbar al asistente.
  }
  const consola = nivel === 'error' ? console.error : console.log;
  consola(`[${nivel}] [${modulo}] ${mensaje}`);
}

module.exports = {
  info: (modulo, mensaje, extra) => escribir('info', modulo, mensaje, extra),
  error: (modulo, mensaje, extra) => escribir('error', modulo, mensaje, extra),
  aviso: (modulo, mensaje, extra) => escribir('aviso', modulo, mensaje, extra),
};
