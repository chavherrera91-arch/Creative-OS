// ============================================================
// JARVIS · Voz: reconocimiento (STT) y síntesis (TTS)
//
// Web Speech API del navegador. En Windows, Microsoft Edge tiene
// las mejores voces en español y el reconocimiento más fiable.
//
// Diseño anti-fallos del reconocimiento:
//  - El navegador corta el reconocimiento continuo cada pocos
//    segundos → se reinicia SIEMPRE que el usuario quiera escuchar.
//  - Los errores NO se tragan: se reportan al panel (consola y
//    texto de estado) para que el fallo sea visible y accionable.
//  - Mientras Jarvis habla, el micrófono se pausa (no se escucha
//    a sí mismo) y la música baja de volumen (ducking).
// ============================================================
'use strict';

const JarvisVoz = (() => {
  const Reconocimiento = window.SpeechRecognition || window.webkitSpeechRecognition;
  let rec = null;
  let escuchando = false;      // el motor está activo ahora mismo
  let deseaEscuchar = false;   // intención del usuario (persiste entre reinicios)
  let alComando = null;
  let alEstado = null;         // 'escuchando' | 'hablando' | 'inactivo'
  let alDiagnostico = null;    // mensajes de diagnóstico para la consola del HUD
  let erroresSeguidos = 0;
  let reinicioProgramado = null;
  let config = { idioma: 'es-MX', velocidad: 1.05, tono: 0.9, vozPreferida: '' };

  const soportaSTT = Boolean(Reconocimiento);
  const soportaTTS = 'speechSynthesis' in window;

  const EXPLICACION_ERROR = {
    'not-allowed': 'Micrófono denegado. Haz clic en el candado de la barra de direcciones → Permitir micrófono, y pulsa 🎙.',
    'service-not-allowed': 'El servicio de voz del navegador está bloqueado. Usa Microsoft Edge o Chrome.',
    'network': 'El reconocimiento de voz necesita internet (es un servicio en línea del navegador).',
    'audio-capture': 'No encuentro micrófono. Conecta uno y pulsa 🎙.',
    'language-not-supported': 'El idioma configurado no está disponible en este navegador.',
  };

  function configurar(cfg) {
    config = { ...config, ...(cfg || {}) };
  }

  function estado(s) {
    if (alEstado) alEstado(s);
  }

  function diagnostico(mensaje, esError) {
    if (alDiagnostico) alDiagnostico(mensaje, esError);
  }

  // ---------- Reconocimiento ----------

  function crearReconocedor() {
    rec = new Reconocimiento();
    rec.lang = config.idioma || 'es-MX';
    rec.continuous = true;
    rec.interimResults = false;
    rec.maxAlternatives = 1;

    rec.onstart = () => {
      escuchando = true;
      erroresSeguidos = 0;
      estado('escuchando');
    };

    rec.onresult = (evento) => {
      const resultado = evento.results[evento.results.length - 1];
      if (!resultado.isFinal) return;
      const texto = resultado[0].transcript.trim();
      if (texto && alComando) {
        diagnostico(`🎙 Escuché: "${texto}"`);
        alComando(texto);
      }
    };

    rec.onend = () => {
      escuchando = false;
      // Reinicio automático: el navegador corta la escucha continua
      // solo (por silencio o por tiempo). Si el usuario sigue
      // queriendo escuchar y Jarvis no está hablando, relanzamos.
      if (deseaEscuchar && !(soportaTTS && speechSynthesis.speaking)) {
        programarReinicio(300);
      } else if (!deseaEscuchar) {
        estado('inactivo');
      }
    };

    rec.onerror = (e) => {
      escuchando = false;
      const err = e.error || 'desconocido';
      if (err === 'no-speech' || err === 'aborted') {
        // Silencio prolongado o parada nuestra: no es un problema.
        return;
      }
      erroresSeguidos++;
      const explicacion = EXPLICACION_ERROR[err] || `Error de voz: ${err}.`;
      diagnostico(explicacion, true);

      if (err === 'not-allowed' || err === 'service-not-allowed') {
        deseaEscuchar = false; // no insistir sin permiso
        estado('inactivo');
        return;
      }
      // Errores transitorios (red, captura): reintentar con calma,
      // hasta 5 veces seguidas antes de rendirse.
      if (erroresSeguidos <= 5 && deseaEscuchar) {
        programarReinicio(1500 * erroresSeguidos);
      } else if (deseaEscuchar) {
        deseaEscuchar = false;
        estado('inactivo');
        diagnostico('El reconocimiento falló repetidamente. Pulsa 🎙 para reintentar.', true);
      }
    };
  }

  function programarReinicio(ms) {
    clearTimeout(reinicioProgramado);
    reinicioProgramado = setTimeout(() => {
      if (deseaEscuchar && !escuchando) iniciar();
    }, ms);
  }

  function iniciar() {
    if (!soportaSTT) {
      diagnostico('Este navegador no soporta reconocimiento de voz. Usa Microsoft Edge o Chrome.', true);
      return;
    }
    if (escuchando) return;
    if (!rec) crearReconocedor();
    try {
      rec.start();
    } catch {
      // start() lanza si ya estaba activo: reintento corto.
      programarReinicio(400);
    }
  }

  function escuchar(callback) {
    alComando = callback;
    deseaEscuchar = true;
    erroresSeguidos = 0;
    iniciar();
  }

  function silenciar() {
    deseaEscuchar = false;
    clearTimeout(reinicioProgramado);
    if (rec && escuchando) {
      try { rec.stop(); } catch { /* ya parado */ }
    }
    escuchando = false;
    estado('inactivo');
  }

  function estaEscuchando() {
    return deseaEscuchar;
  }

  // ---------- Síntesis ----------

  function elegirVoz() {
    const voces = speechSynthesis.getVoices();
    const idioma = (config.idioma || 'es').slice(0, 2);
    const preferida = config.vozPreferida
      ? voces.find((v) => v.name.toLowerCase().includes(config.vozPreferida.toLowerCase()))
      : null;
    return (
      preferida ||
      voces.find((v) => v.lang.startsWith(config.idioma)) ||
      voces.find((v) => v.lang.startsWith(idioma)) ||
      null
    );
  }

  /** Lee un texto en voz alta. Pausa STT/aplausos y baja la música. */
  function decir(texto) {
    return new Promise((resolve) => {
      if (!soportaTTS || !texto) return resolve();

      const estabaEscuchando = deseaEscuchar;
      clearTimeout(reinicioProgramado);
      if (rec && escuchando) {
        try { rec.stop(); } catch { /* ya parado */ }
      }
      JarvisAudio.pausarDeteccion();
      window.JarvisIntro?.duck(true);
      estado('hablando');

      const u = new SpeechSynthesisUtterance(texto);
      u.lang = config.idioma || 'es-MX';
      u.rate = config.velocidad ?? 1.05;
      u.pitch = config.tono ?? 0.9;
      const voz = elegirVoz();
      if (voz) u.voice = voz;

      // Sincronía real con el habla para el reactor HUD.
      u.onstart = () => window.JarvisReactor?.pulso(0.7);
      u.onboundary = () => window.JarvisReactor?.pulso(0.45);

      const terminar = () => {
        window.JarvisIntro?.duck(false);
        JarvisAudio.reanudarDeteccion();
        if (estabaEscuchando) {
          deseaEscuchar = true;
          programarReinicio(250);
          estado('escuchando');
        } else {
          estado('inactivo');
        }
        resolve();
      };
      u.onend = terminar;
      u.onerror = terminar;
      speechSynthesis.speak(u);
    });
  }

  // Algunas plataformas cargan las voces de forma asíncrona.
  if (soportaTTS) speechSynthesis.onvoiceschanged = () => {};

  return {
    soportaSTT,
    soportaTTS,
    configurar,
    escuchar,
    silenciar,
    estaEscuchando,
    decir,
    setEstadoCallback: (cb) => { alEstado = cb; },
    setDiagnosticoCallback: (cb) => { alDiagnostico = cb; },
  };
})();
