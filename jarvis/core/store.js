// ============================================================
// JARVIS · Almacén de datos
// Tareas, notificaciones e historial de comandos, persistidos
// como JSON en jarvis/data/. Sin base de datos externa: los
// volúmenes de un asistente personal no la necesitan y así el
// sistema sigue funcionando sin instalar nada.
// ============================================================
'use strict';

const path = require('path');
const { RAIZ, leerJSON, escribirJSON, idCorto, ahora } = require('./utils');

const DIR_DATOS = path.join(RAIZ, 'data');
const RUTA_TAREAS = path.join(DIR_DATOS, 'tasks.json');
const RUTA_NOTIFICACIONES = path.join(DIR_DATOS, 'notifications.json');
const RUTA_HISTORIAL = path.join(DIR_DATOS, 'history.json');

// ---------- Tareas ----------
// { id, titulo, hecha, fecha (YYYY-MM-DD opcional → aparece en calendario),
//   prioridad: alta|media|baja, creada }

function listarTareas() {
  return leerJSON(RUTA_TAREAS, []);
}

function crearTarea({ titulo, fecha = null, prioridad = 'media' }) {
  if (!titulo || !String(titulo).trim()) throw new Error('La tarea necesita un título');
  const tareas = listarTareas();
  const tarea = {
    id: idCorto(),
    titulo: String(titulo).trim(),
    hecha: false,
    fecha,
    prioridad,
    creada: ahora(),
  };
  tareas.push(tarea);
  escribirJSON(RUTA_TAREAS, tareas);
  return tarea;
}

function actualizarTarea(id, cambios) {
  const tareas = listarTareas();
  const tarea = tareas.find((t) => t.id === id);
  if (!tarea) throw new Error(`Tarea no encontrada: ${id}`);
  for (const clave of ['titulo', 'hecha', 'fecha', 'prioridad']) {
    if (clave in cambios) tarea[clave] = cambios[clave];
  }
  escribirJSON(RUTA_TAREAS, tareas);
  return tarea;
}

function borrarTarea(id) {
  const tareas = listarTareas();
  const restantes = tareas.filter((t) => t.id !== id);
  if (restantes.length === tareas.length) throw new Error(`Tarea no encontrada: ${id}`);
  escribirJSON(RUTA_TAREAS, restantes);
}

// ---------- Notificaciones ----------
// { id, texto, nivel: info|exito|alerta, leida, creada }

function listarNotificaciones() {
  return leerJSON(RUTA_NOTIFICACIONES, []);
}

function notificar(texto, nivel = 'info') {
  const lista = listarNotificaciones();
  lista.unshift({ id: idCorto(), texto, nivel, leida: false, creada: ahora() });
  escribirJSON(RUTA_NOTIFICACIONES, lista.slice(0, 100));
  return lista[0];
}

function marcarLeidas() {
  const lista = listarNotificaciones().map((n) => ({ ...n, leida: true }));
  escribirJSON(RUTA_NOTIFICACIONES, lista);
  return lista;
}

// ---------- Historial de comandos ----------
// { id, origen: voz|texto, comando, respuesta, agente, creada }

function listarHistorial(limite = 50) {
  return leerJSON(RUTA_HISTORIAL, []).slice(0, limite);
}

function registrarComando({ origen, comando, respuesta, agente }, maximo = 200) {
  const lista = leerJSON(RUTA_HISTORIAL, []);
  lista.unshift({
    id: idCorto(),
    origen,
    comando,
    respuesta: String(respuesta || '').slice(0, 2000),
    agente: agente || null,
    creada: ahora(),
  });
  escribirJSON(RUTA_HISTORIAL, lista.slice(0, maximo));
}

module.exports = {
  listarTareas,
  crearTarea,
  actualizarTarea,
  borrarTarea,
  listarNotificaciones,
  notificar,
  marcarLeidas,
  listarHistorial,
  registrarComando,
};
