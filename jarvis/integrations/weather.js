// ============================================================
// JARVIS · Integración de clima
// Open-Meteo: gratuito, sin clave de API. Caché de 10 minutos
// para no golpear el servicio en cada refresco del dashboard.
// ============================================================
'use strict';

const path = require('path');
const { RAIZ, leerJSON } = require('../core/utils');

const CONFIG = leerJSON(path.join(RAIZ, 'config', 'config.json'), {});

const CODIGOS = {
  0: 'Despejado', 1: 'Mayormente despejado', 2: 'Parcialmente nublado', 3: 'Nublado',
  45: 'Niebla', 48: 'Niebla con escarcha',
  51: 'Llovizna ligera', 53: 'Llovizna', 55: 'Llovizna intensa',
  61: 'Lluvia ligera', 63: 'Lluvia', 65: 'Lluvia intensa',
  71: 'Nieve ligera', 73: 'Nieve', 75: 'Nieve intensa',
  80: 'Chubascos ligeros', 81: 'Chubascos', 82: 'Chubascos fuertes',
  95: 'Tormenta', 96: 'Tormenta con granizo', 99: 'Tormenta fuerte con granizo',
};

let cache = { datos: null, hasta: 0 };

async function obtener() {
  if (cache.datos && Date.now() < cache.hasta) return cache.datos;

  const lat = CONFIG.latitud ?? 19.4326;
  const lon = CONFIG.longitud ?? -99.1332;
  const url =
    `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}` +
    `&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m` +
    `&daily=temperature_2m_max,temperature_2m_min&timezone=auto&forecast_days=1`;

  const respuesta = await fetch(url, { signal: AbortSignal.timeout(8000) });
  if (!respuesta.ok) throw new Error(`Open-Meteo respondió ${respuesta.status}`);
  const json = await respuesta.json();

  const datos = {
    ciudad: CONFIG.ciudad || 'Ubicación configurada',
    temperatura: Math.round(json.current.temperature_2m),
    humedad: json.current.relative_humidity_2m,
    viento: Math.round(json.current.wind_speed_10m),
    descripcion: CODIGOS[json.current.weather_code] || 'Sin datos',
    maxima: Math.round(json.daily.temperature_2m_max[0]),
    minima: Math.round(json.daily.temperature_2m_min[0]),
  };
  cache = { datos, hasta: Date.now() + 10 * 60 * 1000 };
  return datos;
}

module.exports = { obtener };
