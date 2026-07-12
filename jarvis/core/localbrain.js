// ============================================================
// JARVIS · Motor local (sin IA)
// Resuelve comandos frecuentes por intenciones en español,
// sin necesitar clave de API. Es el respaldo permanente:
// si Claude no está disponible, Jarvis sigue siendo útil.
// ============================================================
'use strict';

const path = require('path');
const { RAIZ, leerJSON } = require('./utils');
const store = require('./store');
const memoria = require('./memory');

const CONFIG = leerJSON(path.join(RAIZ, 'config', 'config.json'), {});

function horaActual() {
  return new Date().toLocaleTimeString('es-MX', {
    hour: 'numeric',
    minute: '2-digit',
    timeZone: CONFIG.zonaHoraria || undefined,
  });
}

function fechaActual() {
  return new Date().toLocaleDateString('es-MX', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: CONFIG.zonaHoraria || undefined,
  });
}

/**
 * Intenta resolver el comando localmente.
 * Devuelve { texto, accion? } o null si no reconoce la intención.
 * `accion` es una instrucción para el dashboard (p. ej. abrir Drop-Meta).
 */
function resolver(comando) {
  const c = String(comando).toLowerCase().trim();

  if (/\b(qué hora|que hora|dime la hora|hora es)\b/.test(c)) {
    return { texto: `Son las ${horaActual()}, señor.` };
  }

  if (/\b(qué día|que dia|fecha de hoy|qué fecha|que fecha)\b/.test(c)) {
    return { texto: `Hoy es ${fechaActual()}.` };
  }

  if (/\b(abre|abrir|lanza|inicia)\b.*\b(drop.?meta)\b/.test(c) || /^drop.?meta$/.test(c)) {
    return { texto: 'Abriendo Drop-Meta, señor.', accion: { tipo: 'abrir_dropmeta' } };
  }

  const nuevaTarea = c.match(/\b(?:agrega|añade|crea|apunta|anota)\b(?:\s+(?:una|la))?\s*tarea[:,]?\s+(.{3,})/);
  if (nuevaTarea) {
    const tarea = store.crearTarea({ titulo: nuevaTarea[1] });
    return { texto: `Anotado, señor: "${tarea.titulo}".`, accion: { tipo: 'refrescar_tareas' } };
  }

  const completar = c.match(/\b(?:completa|termina|marca)\b.*\btarea\b[:,]?\s*(.{3,})?/);
  if (completar) {
    const pendientes = store.listarTareas().filter((t) => !t.hecha);
    const busqueda = (completar[1] || '').trim();
    const objetivo = busqueda
      ? pendientes.find((t) => t.titulo.toLowerCase().includes(busqueda))
      : pendientes[0];
    if (!objetivo) return { texto: 'No encuentro esa tarea pendiente, señor.' };
    store.actualizarTarea(objetivo.id, { hecha: true });
    return { texto: `Hecho. "${objetivo.titulo}" queda completada.`, accion: { tipo: 'refrescar_tareas' } };
  }

  if (/\b(mis tareas|lista.*tareas|tareas pendientes|qué tengo pendiente|que tengo pendiente)\b/.test(c)) {
    const pendientes = store.listarTareas().filter((t) => !t.hecha);
    if (pendientes.length === 0) return { texto: 'No tiene tareas pendientes, señor.' };
    const primeras = pendientes.slice(0, 5).map((t, i) => `${i + 1}. ${t.titulo}`).join('. ');
    return {
      texto: `Tiene ${pendientes.length} ${pendientes.length === 1 ? 'tarea pendiente' : 'tareas pendientes'}: ${primeras}`,
    };
  }

  if (/\b(clima|tiempo hace|temperatura)\b/.test(c)) {
    return { texto: null, accion: { tipo: 'decir_clima' } };
  }

  if (/\b(estado del sistema|cómo estás|como estas|reporte de estado|status)\b/.test(c)) {
    return { texto: null, accion: { tipo: 'decir_estado' } };
  }

  const leerMem = c.match(/\b(?:lee|léeme|leeme|abre)\b.*\bmemoria\b(?:\s+de)?\s*([a-záéíóúñ]+)?/);
  if (leerMem && leerMem[1]) {
    try {
      const contenido = memoria.leer(leerMem[1]);
      const resumen = contenido.replace(/\s+/g, ' ').slice(0, 400);
      return { texto: `Memoria de ${leerMem[1]}: ${resumen}` };
    } catch {
      return { texto: `No encuentro un archivo de memoria llamado ${leerMem[1]}.` };
    }
  }

  if (/\b(ayuda|qué puedes hacer|que puedes hacer|comandos)\b/.test(c)) {
    return {
      texto:
        'Sin conexión con Claude puedo: decirle la hora y la fecha, el clima, gestionar sus tareas, abrir Drop-Meta, leer su memoria y darle el estado del sistema. Con la clave de API configurada, coordino a los diez agentes especializados.',
    };
  }

  return null;
}

module.exports = { resolver };
