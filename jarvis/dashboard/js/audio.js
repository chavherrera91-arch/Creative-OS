// ============================================================
// JARVIS · Audio: detección de aplausos + sonido de bienvenida
//
// Detección de dos aplausos: análisis de amplitud con Web Audio.
// Un aplauso es un transitorio corto y fuerte; buscamos dos picos
// separados entre `separacionMinimaMs` y `separacionMaximaMs`.
//
// Bienvenida: si existe assets/welcome.mp3 (configurable en
// config.json) se reproduce; si no, se sintetiza una fanfarria
// breve con osciladores para que funcione desde el día uno.
// ============================================================
'use strict';

const JarvisAudio = (() => {
  let contexto = null;
  let analizador = null;
  let detectando = false;
  let alDobleAplauso = null;
  let opciones = { umbral: 0.32, sepMin: 120, sepMax: 700 };
  let ultimoPico = 0;      // momento del primer aplauso de la pareja
  let ultimaActivacion = 0; // anti-rebote entre activaciones
  let nivelActual = 0;     // amplitud del micrófono (0..1) para el reactor HUD

  function ctx() {
    if (!contexto) contexto = new (window.AudioContext || window.webkitAudioContext)();
    return contexto;
  }

  function bucle() {
    if (!detectando || !analizador) return;
    const datos = new Float32Array(analizador.fftSize);
    analizador.getFloatTimeDomainData(datos);
    let pico = 0;
    for (let i = 0; i < datos.length; i++) {
      const v = Math.abs(datos[i]);
      if (v > pico) pico = v;
    }
    // Nivel suavizado para la visualización (ataque rápido, caída lenta).
    nivelActual = pico > nivelActual ? pico : nivelActual * 0.92;

    const ahora = performance.now();
    if (pico > opciones.umbral && ahora - ultimoPico > opciones.sepMin) {
      const esSegundo = ultimoPico && ahora - ultimoPico < opciones.sepMax;
      if (esSegundo && ahora - ultimaActivacion > 2000) {
        ultimaActivacion = ahora;
        ultimoPico = 0;
        if (alDobleAplauso) alDobleAplauso();
      } else if (!esSegundo) {
        ultimoPico = ahora;
      }
    }
    if (ultimoPico && ahora - ultimoPico > opciones.sepMax) ultimoPico = 0;
    requestAnimationFrame(bucle);
  }

  /** Pide micrófono y arranca la detección de doble aplauso. */
  async function iniciarDeteccion(config, callback) {
    alDobleAplauso = callback;
    opciones = {
      umbral: config?.umbral ?? 0.32,
      sepMin: config?.separacionMinimaMs ?? 120,
      sepMax: config?.separacionMaximaMs ?? 700,
    };
    const flujo = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
    });
    const fuente = ctx().createMediaStreamSource(flujo);
    analizador = ctx().createAnalyser();
    analizador.fftSize = 1024;
    fuente.connect(analizador);
    detectando = true;
    bucle();
  }

  function pausarDeteccion() {
    detectando = false;
  }

  function reanudarDeteccion() {
    if (!analizador || detectando) return;
    detectando = true;
    ultimoPico = 0;
    bucle();
  }

  /** Reproduce la música de bienvenida; resuelve al terminar (tope 8 s). */
  async function bienvenida(rutaMusica) {
    if (rutaMusica) {
      const ok = await new Promise((resolve) => {
        const audio = new Audio(rutaMusica);
        audio.volume = 0.85;
        let temporizador = null;
        audio.onended = () => { clearTimeout(temporizador); resolve(true); };
        audio.onerror = () => resolve(false);
        audio
          .play()
          .then(() => {
            temporizador = setTimeout(() => { audio.pause(); resolve(true); }, 8000);
          })
          .catch(() => resolve(false));
      });
      if (ok) return;
    }
    await fanfarria();
  }

  /** Fanfarria futurista sintetizada (respaldo sin archivos). */
  function fanfarria() {
    return new Promise((resolve) => {
      const c = ctx();
      const maestro = c.createGain();
      maestro.gain.value = 0.22;
      maestro.connect(c.destination);
      const notas = [
        { f: 392.0, t: 0.0, d: 0.18 },   // G4
        { f: 523.25, t: 0.16, d: 0.18 }, // C5
        { f: 659.25, t: 0.32, d: 0.22 }, // E5
        { f: 783.99, t: 0.5, d: 0.55 },  // G5
      ];
      for (const { f, t, d } of notas) {
        const osc = c.createOscillator();
        const gan = c.createGain();
        osc.type = 'triangle';
        osc.frequency.value = f;
        gan.gain.setValueAtTime(0, c.currentTime + t);
        gan.gain.linearRampToValueAtTime(1, c.currentTime + t + 0.03);
        gan.gain.exponentialRampToValueAtTime(0.001, c.currentTime + t + d);
        osc.connect(gan).connect(maestro);
        osc.start(c.currentTime + t);
        osc.stop(c.currentTime + t + d + 0.05);
      }
      setTimeout(resolve, 1300);
    });
  }

  /** Amplitud actual del micrófono (0..1). 0 si no hay detección activa. */
  function getNivel() {
    return nivelActual;
  }

  return { iniciarDeteccion, pausarDeteccion, reanudarDeteccion, bienvenida, getNivel };
})();

// Exponer en window: los `const` de nivel superior no crean la propiedad,
// y otros módulos lo consultan como referencia opcional (window.JarvisAudio?).
window.JarvisAudio = JarvisAudio;
