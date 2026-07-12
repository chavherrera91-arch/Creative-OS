// ============================================================
// JARVIS · Voz: reconocimiento (STT) y síntesis (TTS)
//
// Usa la Web Speech API del navegador. En Windows, Microsoft Edge
// ofrece las mejores voces en español (neuronales) y el mejor
// reconocimiento. Mientras Jarvis habla, el reconocimiento y la
// detección de aplausos se pausan para no escucharse a sí mismo.
// ============================================================
'use strict';

const JarvisVoz = (() => {
  const Reconocimiento = window.SpeechRecognition || window.webkitSpeechRecognition;
  let rec = null;
  let escuchando = false;
  let deseaEscuchar = false; // intención del usuario (persiste entre reinicios)
  let alComando = null;
  let alEstado = null; // callback de estado: 'escuchando' | 'hablando' | 'inactivo'
  let config = { idioma: 'es-MX', velocidad: 1.05, tono: 0.9, vozPreferida: '' };

  const soportaSTT = Boolean(Reconocimiento);
  const soportaTTS = 'speechSynthesis' in window;

  function configurar(cfg) {
    config = { ...config, ...(cfg || {}) };
  }

  function estado(s) {
    if (alEstado) alEstado(s);
  }

  // ---------- Reconocimiento ----------

  function crearReconocedor() {
    rec = new Reconocimiento();
    rec.lang = config.idioma || 'es-MX';
    rec.continuous = true;
    rec.interimResults = false;

    rec.onresult = (evento) => {
      const resultado = evento.results[evento.results.length - 1];
      if (!resultado.isFinal) return;
      const texto = resultado[0].transcript.trim();
      if (texto && alComando) alComando(texto);
    };

    rec.onend = () => {
      escuchando = false;
      // El navegador corta el reconocimiento continuo cada cierto
      // tiempo: si el usuario sigue queriendo escuchar, reiniciamos.
      if (deseaEscuchar && !speechSynthesis.speaking) {
        setTimeout(() => { try { iniciar(); } catch { /* ya activo */ } }, 250);
      } else {
        estado('inactivo');
      }
    };

    rec.onerror = (e) => {
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
        deseaEscuchar = false;
        estado('inactivo');
      }
    };
  }

  function iniciar() {
    if (!soportaSTT || escuchando) return;
    if (!rec) crearReconocedor();
    try {
      rec.start();
      escuchando = true;
      estado('escuchando');
    } catch {
      // start() lanza si ya está activo; lo ignoramos.
    }
  }

  function escuchar(callback) {
    alComando = callback;
    deseaEscuchar = true;
    iniciar();
  }

  function silenciar() {
    deseaEscuchar = false;
    if (rec && escuchando) rec.stop();
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

  /** Lee un texto en voz alta. Pausa STT y aplausos mientras habla. */
  function decir(texto) {
    return new Promise((resolve) => {
      if (!soportaTTS || !texto) return resolve();

      // No escucharnos a nosotros mismos.
      const estabaEscuchando = deseaEscuchar;
      if (rec && escuchando) rec.stop();
      JarvisAudio.pausarDeteccion();
      window.JarvisIntro?.duck(true); // baja la música mientras habla
      estado('hablando');

      const u = new SpeechSynthesisUtterance(texto);
      u.lang = config.idioma || 'es-MX';
      u.rate = config.velocidad ?? 1.05;
      u.pitch = config.tono ?? 0.9;
      const voz = elegirVoz();
      if (voz) u.voice = voz;

      // Sincronía real con el habla: el TTS emite un evento por palabra;
      // cada palabra dispara un pulso en el reactor HUD.
      u.onstart = () => window.JarvisReactor?.pulso(0.7);
      u.onboundary = () => window.JarvisReactor?.pulso(0.45);

      const terminar = () => {
        window.JarvisIntro?.duck(false); // restaura el volumen de la música
        JarvisAudio.reanudarDeteccion();
        if (estabaEscuchando) {
          deseaEscuchar = true;
          setTimeout(iniciar, 200);
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
  };
})();
