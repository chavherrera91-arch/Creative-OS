// ============================================================
// JARVIS · Automatización: briefing diario
// Ejemplo de automatización ejecutable por el Automation Agent
// (herramienta ejecutar_automatizacion) o a mano:
//   node jarvis/automations/briefing-diario.js
//
// Resume el estado del día: tareas pendientes, tareas con fecha
// de hoy y notificaciones sin leer. Imprime a stdout; la salida
// vuelve al agente que la invocó.
// ============================================================
'use strict';

const store = require('../core/store');

// Fecha LOCAL (toISOString daría el día UTC, adelantado por la noche).
const d = new Date();
const hoy = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const tareas = store.listarTareas();
const pendientes = tareas.filter((t) => !t.hecha);
const deHoy = pendientes.filter((t) => t.fecha === hoy);
const sinLeer = store.listarNotificaciones().filter((n) => !n.leida);

const lineas = [
  `Briefing del ${hoy}`,
  `- Tareas pendientes: ${pendientes.length}`,
  ...(deHoy.length ? [`- Para hoy: ${deHoy.map((t) => t.titulo).join(' · ')}`] : ['- Para hoy: nada agendado']),
  `- Notificaciones sin leer: ${sinLeer.length}`,
];

console.log(lineas.join('\n'));
