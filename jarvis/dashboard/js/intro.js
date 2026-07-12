// ============================================================
// JARVIS · Intro musical (YouTube)
// Reproduce la canción de entrada al activarse (doble aplauso)
// usando el reproductor oficial embebido de YouTube — sin
// descargar audio (los términos de YouTube no lo permiten).
//
// - Config: config.json → musicaIntro { tipo:"youtube", url, volumen }
// - Controles flotantes: pausar/reanudar, detener y cambiar canción
//   (el cambio se guarda en el servidor vía POST /api/config/musica).
// - "Ducking": baja el volumen cuando Jarvis habla y lo restaura.
// - Sin internet o si el video no permite embebido → devuelve false
//   y la activación usa el respaldo local (welcome.mp3 o fanfarria).
// ============================================================
'use strict';

const JarvisIntro = (() => {
  let player = null;
  let apiLista = false;
  let cargandoAPI = null;
  let config = { tipo: 'youtube', url: '', volumen: 80 };
  let sonando = false;
  let volumenBase = 80;

  const $ = (id) => document.getElementById(id);

  /** Extrae el ID de cualquier formato de URL de YouTube. */
  function extraerId(url) {
    if (!url) return null;
    const m = String(url).match(
      /(?:youtu\.be\/|youtube\.com\/(?:watch\?v=|embed\/|shorts\/))([A-Za-z0-9_-]{11})/,
    );
    return m ? m[1] : /^[A-Za-z0-9_-]{11}$/.test(url.trim()) ? url.trim() : null;
  }

  /** Carga la IFrame API de YouTube una sola vez. */
  function cargarAPI() {
    if (apiLista) return Promise.resolve(true);
    if (cargandoAPI) return cargandoAPI;
    cargandoAPI = new Promise((resolve) => {
      const temporizador = setTimeout(() => resolve(false), 6000); // sin internet
      window.onYouTubeIframeAPIReady = () => {
        apiLista = true;
        clearTimeout(temporizador);
        resolve(true);
      };
      const s = document.createElement('script');
      s.src = 'https://www.youtube.com/iframe_api';
      s.onerror = () => {
        clearTimeout(temporizador);
        resolve(false);
      };
      document.head.appendChild(s);
    });
    return cargandoAPI;
  }

  function configurar(cfg) {
    config = { ...config, ...(cfg || {}) };
    volumenBase = config.volumen ?? 80;
  }

  // ---------- Barra de controles ----------

  function barra() {
    return $('barra-musica');
  }

  function mostrarBarra(titulo) {
    const b = barra();
    if (!b) return;
    b.classList.remove('oculto');
    $('musica-titulo').textContent = titulo || '♪ Intro';
    actualizarBotonPausa();
  }

  function ocultarBarra() {
    barra()?.classList.add('oculto');
  }

  function actualizarBotonPausa() {
    const btn = $('btn-musica-pausa');
    if (btn) btn.textContent = sonando ? '⏸' : '▶';
  }

  // ---------- Reproducción ----------

  /**
   * Intenta reproducir la intro. Resuelve `true` si la música arrancó
   * (y sigue sonando de fondo), `false` para que el llamador use el
   * respaldo local. Nunca lanza.
   */
  async function reproducir() {
    try {
      const id = extraerId(config.url);
      if (config.tipo !== 'youtube' || !id) return false;
      if (!(await cargarAPI())) return false;

      return await new Promise((resolve) => {
        const rendicion = setTimeout(() => resolve(false), 8000);
        let resuelto = false;
        const arranco = () => {
          if (resuelto) return;
          resuelto = true;
          clearTimeout(rendicion);
          resolve(true);
        };
        const fallo = () => {
          if (resuelto) return;
          resuelto = true;
          clearTimeout(rendicion);
          resolve(false);
        };

        const crear = () => {
          player = new YT.Player('youtube-player', {
            width: 1,
            height: 1,
            videoId: id,
            playerVars: { autoplay: 1, controls: 0, disablekb: 1, rel: 0 },
            events: {
              onReady: (e) => {
                e.target.setVolume(volumenBase);
                e.target.playVideo();
              },
              onStateChange: (e) => {
                if (e.data === YT.PlayerState.PLAYING) {
                  sonando = true;
                  mostrarBarra('♪ Canción de entrada');
                  arranco();
                } else if (e.data === YT.PlayerState.PAUSED) {
                  sonando = false;
                  actualizarBotonPausa();
                } else if (e.data === YT.PlayerState.ENDED) {
                  sonando = false;
                  ocultarBarra();
                }
              },
              onError: fallo, // video no embebible / no existe
            },
          });
        };

        if (player) {
          // Cambio de canción con el reproductor ya creado.
          player.loadVideoById(id);
          player.setVolume(volumenBase);
          arranco();
        } else {
          crear();
        }
      });
    } catch {
      return false;
    }
  }

  function alternarPausa() {
    if (!player) return;
    if (sonando) player.pauseVideo();
    else player.playVideo();
  }

  function detener() {
    if (!player) return;
    try {
      player.stopVideo();
    } catch { /* ya detenido */ }
    sonando = false;
    ocultarBarra();
  }

  /** Baja el volumen mientras Jarvis habla y lo restaura al terminar. */
  function duck(activar) {
    if (!player || !sonando) return;
    try {
      player.setVolume(activar ? Math.round(volumenBase * 0.25) : volumenBase);
    } catch { /* reproductor no listo */ }
  }

  /** Cambia la canción: valida, guarda en el servidor y la deja lista. */
  async function cambiarCancion() {
    const actual = config.url || '';
    const nueva = prompt('URL de YouTube para la canción de entrada:', actual);
    if (nueva === null) return; // canceló
    const id = extraerId(nueva);
    if (nueva.trim() && !id) {
      alert('No parece una URL de YouTube válida (youtu.be/... o youtube.com/watch?v=...).');
      return;
    }
    const r = await fetch('/api/config/musica', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: nueva.trim() }),
    });
    if (r.ok) {
      config.url = nueva.trim();
      if (player && id && sonando) player.loadVideoById(id); // cambia al vuelo
      else if (!nueva.trim()) detener();
    }
  }

  return { configurar, reproducir, alternarPausa, detener, duck, cambiarCancion, extraerId };
})();

window.JarvisIntro = JarvisIntro;
