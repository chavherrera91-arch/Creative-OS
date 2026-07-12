// ============================================================
// JARVIS · Orquestador del dashboard
// Flujo: standby → (doble aplauso | botón) → secuencia de
// activación (música + saludo + Drop-Meta) → escucha continua.
// ============================================================
'use strict';

(() => {
  const $ = (id) => document.getElementById(id);
  let CONFIG = {};
  let activado = false;
  let ocupado = false; // evita comandos superpuestos

  window.JARVIS_CONFIG = CONFIG;

  // ---------- Arranque ----------

  async function cargarConfig() {
    const r = await fetch('/api/config');
    CONFIG = await r.json();
    window.JARVIS_CONFIG = CONFIG;
    JarvisVoz.configurar(CONFIG.voz);
    JarvisIntro.configurar(CONFIG.musicaIntro);
  }

  async function prepararSistemas() {
    // Botón inicial: desbloquea audio + micrófono (requisito del navegador).
    $('btn-iniciar').disabled = true;
    $('standby-estado').textContent = 'Solicitando acceso al micrófono…';
    try {
      await JarvisAudio.iniciarDeteccion(CONFIG.aplausos, () => {
        if (!activado) activar('aplausos');
      });
      $('standby-estado').textContent = '🎙 Escuchando… dé DOS APLAUSOS para activar a Jarvis.';
      $('reactor').classList.add('escuchando');
      JarvisReactor.setModo('escuchando', 'reactor-standby');
      $('btn-activar-manual').classList.remove('oculto');
      $('btn-iniciar').classList.add('oculto');
    } catch (e) {
      $('standby-estado').textContent =
        'Sin acceso al micrófono. Puede activar manualmente (la voz quedará limitada).';
      $('btn-activar-manual').classList.remove('oculto');
      $('btn-iniciar').classList.add('oculto');
    }
  }

  // ---------- Secuencia de activación ----------
  // Dos aplausos → canción + pantalla "INICIANDO JARVIS" → saludo por
  // voz → y SOLO entonces aparece la interfaz principal.

  /** Pantalla de arranque: log de sistema con datos reales + progreso. */
  async function secuenciaArranque() {
    let est = null;
    try {
      est = await (await fetch('/api/status')).json();
    } catch { /* sin datos: el log usa valores genéricos */ }

    const lineas = [
      ['Núcleo Jarvis', 'v1.0 cargado'],
      ['Memoria permanente', est ? `${(await (await fetch('/api/memory')).json()).length} archivos` : 'cargada'],
      ['Motor de IA', est?.ia?.disponible ? `${est.ia.proveedor} (${est.ia.modelo})` : 'modo básico'],
      ['Agentes especializados', est ? `${est.agentes} en línea` : 'en línea'],
      ['Drop-Meta', est?.dropMeta?.disponible ? 'disponible' : 'no encontrada'],
      ['Red', est?.internet ? 'conectada' : 'sin internet'],
      ['Sistemas de voz', JarvisVoz.soportaSTT ? 'listos' : 'no soportados'],
    ];

    const log = $('arranque-log');
    const progreso = $('arranque-progreso');
    const estado = $('arranque-estado');
    log.innerHTML = '';

    for (let i = 0; i < lineas.length; i++) {
      const [etiqueta, valor] = lineas[i];
      // La línea anterior deja de tener cursor.
      log.querySelector('.cursor')?.classList.remove('cursor');
      const div = document.createElement('div');
      div.className = 'linea-boot cursor';
      div.innerHTML = `<span class="ok">[ OK ]</span> ${etiqueta} <span class="dato">— ${valor}</span>`;
      log.appendChild(div);
      progreso.style.width = `${Math.round(((i + 1) / lineas.length) * 100)}%`;
      estado.textContent = `${etiqueta}…`;
      await new Promise((r) => setTimeout(r, 480));
    }
    log.querySelector('.cursor')?.classList.remove('cursor');
    estado.textContent = 'Sistemas en línea';
    await new Promise((r) => setTimeout(r, 400));
  }

  async function activar(origen) {
    if (activado) return;
    activado = true;
    JarvisAudio.pausarDeteccion();

    // 1) Canción de entrada EN PARALELO (no bloquea el arranque):
    //    YouTube si está configurada; si falla, respaldo local.
    const musicaPromesa = JarvisIntro.reproducir().then((ok) => {
      if (!ok) return JarvisAudio.bienvenida(CONFIG.musicaBienvenida);
      return true;
    });

    // 2) Pantalla "INICIANDO JARVIS" mientras suena la música.
    $('standby').classList.add('oculto');
    $('arranque').classList.remove('oculto');
    await secuenciaArranque();

    // 3) Saludo por voz (la música baja sola). La interfaz espera.
    await JarvisVoz.decir(CONFIG.saludo || 'Bienvenido a casa, señor. ¿Qué puedo hacer por usted?');

    // 4) AHORA sí: interfaz principal.
    $('arranque').classList.add('oculto');
    $('hud').classList.remove('oculto');
    JarvisUI.consola(`Activación por ${origen === 'aplausos' ? 'doble aplauso' : 'botón'}.`, 'ok');

    // 5) Drop-Meta: verificar que está lista (no se abre encima del HUD;
    //    el botón ⬢ la trae al frente cuando quieras).
    if (CONFIG.dropMeta?.abrirAlActivar) {
      try {
        const r = await fetch('/drop-meta/', { method: 'HEAD' });
        JarvisUI.consola(r.ok ? 'Drop-Meta verificada y lista (⬢ para abrir).' : 'Drop-Meta no responde.', r.ok ? 'ok' : 'error');
      } catch {
        JarvisUI.consola('No pude verificar Drop-Meta.', 'error');
      }
    }

    // 6) Escucha continua de comandos.
    if (JarvisVoz.soportaSTT) {
      JarvisVoz.escuchar(procesarComando);
      $('btn-mic').classList.add('activo');
    } else {
      JarvisUI.consola('Este navegador no soporta reconocimiento de voz. Use Edge o Chrome.', 'error');
      JarvisUI.estadoVoz('inactivo');
    }

    refrescarTodo();
    void musicaPromesa; // sigue sonando de fondo con sus controles
  }

  // ---------- Drop-Meta (overlay integrado, sin popups) ----------

  async function abrirDropMeta(comprobar) {
    if (comprobar) {
      try {
        const r = await fetch('/drop-meta/', { method: 'HEAD' });
        if (!r.ok) throw new Error();
        JarvisUI.consola('Drop-Meta verificado y en línea.', 'ok');
      } catch {
        JarvisUI.consola('No pude verificar Drop-Meta.', 'error');
        return;
      }
    }
    const iframe = $('iframe-dropmeta');
    if (!iframe.src || iframe.src === 'about:blank' || !iframe.src.includes('/drop-meta/')) {
      iframe.src = '/drop-meta/';
    }
    $('overlay-dropmeta').classList.remove('oculto');
    JarvisUI.consola('Drop-Meta abierto (✕ para volver a Jarvis).', 'accion');
  }

  function cerrarDropMeta() {
    $('overlay-dropmeta').classList.add('oculto');
  }

  // ---------- Vistas del panel central (NÚCLEO / CHAT) ----------

  function verVista(cual) {
    const nucleo = cual === 'nucleo';
    $('vista-nucleo').classList.toggle('oculto', !nucleo);
    $('vista-chat').classList.toggle('oculto', nucleo);
    $('tab-nucleo').classList.toggle('activo', nucleo);
    $('tab-chat').classList.toggle('activo', !nucleo);
  }

  // ---------- Comandos (voz o texto) ----------

  async function procesarComando(texto, origen = 'voz') {
    if (ocupado) return;
    ocupado = true;
    if (origen === 'texto') verVista('chat'); // por voz, el reactor sigue al frente
    JarvisUI.estadoVoz('pensando');
    JarvisUI.agregarMensaje('usuario', texto);
    JarvisUI.consola(`Comando (${origen}): ${texto}`);

    const agenteId = $('sel-agente').value;
    const burbuja = JarvisUI.agregarMensaje('jarvis', '', agenteId || 'jarvis');

    try {
      const resultado = await JarvisChat.enviar({
        mensaje: texto,
        agenteId,
        origen,
        alTexto: (delta) => burbuja.añadir(delta),
        alEvento: manejarEvento,
      });

      if (!resultado.texto) burbuja.fijar('(acción ejecutada)');
      else burbuja.fijar(resultado.texto);
      burbuja.etiquetar(resultado.agente === 'local' ? 'motor local' : resultado.agente);

      // Leer la respuesta en voz alta (solo si vino de voz, o es corta).
      const paraVoz = resultado.texto || '';
      if (paraVoz && (origen === 'voz' || paraVoz.length < 400)) {
        await JarvisVoz.decir(recortarParaVoz(paraVoz));
      }
      refrescarHistorial();
      refrescarTareas();
      refrescarNotificaciones();
    } catch (e) {
      burbuja.fijar(`Error: ${e.message}`);
      JarvisUI.consola(`Error del chat: ${e.message}`, 'error');
    } finally {
      ocupado = false;
      JarvisUI.estadoVoz(JarvisVoz.estaEscuchando() ? 'escuchando' : 'inactivo');
    }
  }

  /** No dictar documentos enteros: en voz, tope prudente. */
  function recortarParaVoz(texto) {
    const limpio = texto.replace(/[#*_`>|-]+/g, ' ').replace(/\s+/g, ' ').trim();
    return limpio.length > 600 ? limpio.slice(0, 600) + '. El resto está en pantalla, señor.' : limpio;
  }

  async function manejarEvento(ev) {
    if (ev.tipo === 'herramienta') {
      JarvisUI.consola(`⚙ ${ev.agente} → ${ev.nombre}`, 'accion');
    } else if (ev.tipo === 'delegacion') {
      JarvisUI.consola(`↳ CEO delega en ${ev.nombre}`, 'accion');
      JarvisUI.marcarAgente(ev.agente, true);
      setTimeout(() => JarvisUI.marcarAgente(ev.agente, false), 15000);
    } else if (ev.tipo === 'error') {
      JarvisUI.consola(ev.mensaje, 'error');
    } else if (ev.tipo === 'accion') {
      await ejecutarAccionLocal(ev.accion);
    }
  }

  async function ejecutarAccionLocal(accion) {
    switch (accion?.tipo) {
      case 'abrir_dropmeta':
        abrirDropMeta(true);
        break;
      case 'refrescar_tareas':
        refrescarTareas();
        break;
      case 'decir_clima': {
        try {
          const c = await (await fetch('/api/weather')).json();
          const frase = `En ${c.ciudad} hay ${c.temperatura} grados, ${c.descripcion.toLowerCase()}. Máxima de ${c.maxima} y mínima de ${c.minima}.`;
          JarvisUI.agregarMensaje('jarvis', frase, 'clima');
          await JarvisVoz.decir(frase);
        } catch {
          await JarvisVoz.decir('No pude consultar el clima, señor.');
        }
        break;
      }
      case 'decir_estado': {
        try {
          const est = await (await fetch('/api/status')).json();
          const frase = `Sistemas nominales. ${est.internet ? 'Con conexión a internet' : 'Sin internet'}. Motor de inteligencia ${est.ia.disponible ? 'activo' : 'en modo local'}. ${est.agentes} agentes listos.`;
          JarvisUI.agregarMensaje('jarvis', frase, 'sistema');
          await JarvisVoz.decir(frase);
        } catch {
          /* silencio */
        }
        break;
      }
    }
  }

  // ---------- Refrescos periódicos ----------

  async function refrescarEstado() {
    try {
      const est = await (await fetch('/api/status')).json();
      JarvisUI.pintarSistema(est);
      if (est.urlLan) {
        JarvisUI.mensajePie(`Sistemas nominales. 📱 En tu teléfono (misma WiFi): ${est.urlLan}`);
      }
    } catch {
      JarvisUI.mensajePie('Servidor de Jarvis inaccesible.');
    }
  }

  async function refrescarClima() {
    try {
      JarvisUI.pintarClima(await (await fetch('/api/weather')).json());
    } catch {
      JarvisUI.pintarClimaError();
    }
  }

  let cacheTareas = [];
  async function refrescarTareas() {
    try {
      cacheTareas = await (await fetch('/api/tasks')).json();
      JarvisUI.pintarTareas(cacheTareas, {
        alternar: async (id, hecha) => {
          await fetch(`/api/tasks/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ hecha }),
          });
          refrescarTareas();
        },
        borrar: async (id) => {
          await fetch(`/api/tasks/${id}`, { method: 'DELETE' });
          refrescarTareas();
        },
      });
      JarvisUI.pintarCalendario(cacheTareas);
    } catch {
      /* siguiente ciclo */
    }
  }

  // Notificaciones con hablar=true se leen en voz alta UNA vez
  // (el programador marca así el reporte diario y las emergencias).
  const habladas = new Set(JSON.parse(localStorage.getItem('jarvis_habladas') || '[]'));

  async function refrescarNotificaciones() {
    try {
      const lista = await (await fetch('/api/notifications')).json();
      JarvisUI.pintarNotificaciones(lista);

      if (activado) {
        const pendientesVoz = lista.filter((n) => n.hablar && !n.leida && !habladas.has(n.id)).reverse();
        for (const n of pendientesVoz) {
          habladas.add(n.id);
          JarvisUI.consola(`🔔 Anuncio: ${n.texto}`, 'accion');
          // El detalle (p. ej. el reporte CEO completo) se muestra en el chat;
          // por voz solo el titular + primeras líneas del detalle.
          if (n.detalle) JarvisUI.agregarMensaje('jarvis', n.detalle, 'programador');
          await JarvisVoz.decir(recortarParaVoz(n.detalle ? n.detalle : n.texto));
        }
        if (pendientesVoz.length) {
          localStorage.setItem('jarvis_habladas', JSON.stringify([...habladas].slice(-100)));
        }
      }
    } catch { /* siguiente ciclo */ }
  }

  async function refrescarHistorial() {
    try {
      JarvisUI.pintarHistorial(await (await fetch('/api/history')).json());
    } catch { /* siguiente ciclo */ }
  }

  async function refrescarAgentes() {
    try {
      const lista = await (await fetch('/api/agents')).json();
      JarvisUI.pintarAgentes(lista);
      // Rellenar el selector de agente (solo la primera vez).
      const sel = $('sel-agente');
      if (sel.options.length <= 1) {
        for (const a of lista) {
          if (a.id === 'ceo') continue; // el CEO es la opción por defecto
          const op = document.createElement('option');
          op.value = a.id;
          op.textContent = `${a.emoji} ${a.nombre}`;
          sel.appendChild(op);
        }
      }
    } catch { /* siguiente ciclo */ }
  }

  function refrescarTodo() {
    refrescarEstado();
    refrescarClima();
    refrescarTareas();
    refrescarNotificaciones();
    refrescarHistorial();
    refrescarAgentes();
  }

  // ---------- Cableado de la interfaz ----------

  function cablear() {
    $('btn-iniciar').addEventListener('click', prepararSistemas);
    $('btn-activar-manual').addEventListener('click', () => activar('manual'));
    $('btn-abrir-dropmeta').addEventListener('click', () => abrirDropMeta(false));
    $('btn-dropmeta-cerrar').addEventListener('click', cerrarDropMeta);
    $('tab-nucleo').addEventListener('click', () => verVista('nucleo'));
    $('tab-chat').addEventListener('click', () => verVista('chat'));

    // Diagnóstico de voz SIEMPRE visible: si el reconocimiento falla,
    // la causa aparece en la consola y en el estado (nunca en silencio).
    JarvisVoz.setDiagnosticoCallback((mensaje, esError) => {
      JarvisUI.consola(mensaje, esError ? 'error' : '');
      if (esError) document.getElementById('voz-texto').textContent = '⚠ Voz con problemas (ver consola)';
    });

    $('form-comando').addEventListener('submit', (e) => {
      e.preventDefault();
      const texto = $('in-comando').value.trim();
      if (!texto) return;
      $('in-comando').value = '';
      procesarComando(texto, 'texto');
    });

    $('btn-mic').addEventListener('click', () => {
      if (JarvisVoz.estaEscuchando()) {
        JarvisVoz.silenciar();
        $('btn-mic').classList.remove('activo');
      } else {
        JarvisVoz.escuchar(procesarComando);
        $('btn-mic').classList.add('activo');
      }
    });

    $('btn-musica-pausa').addEventListener('click', () => JarvisIntro.alternarPausa());
    $('btn-musica-stop').addEventListener('click', () => JarvisIntro.detener());
    $('btn-musica-cambiar').addEventListener('click', () => JarvisIntro.cambiarCancion());

    $('btn-nueva-tarea').addEventListener('click', async () => {
      const titulo = prompt('Nueva tarea:');
      if (!titulo) return;
      await fetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ titulo }),
      });
      refrescarTareas();
    });

    JarvisVoz.setEstadoCallback((estado) => JarvisUI.estadoVoz(estado));
  }

  async function principal() {
    await cargarConfig();
    cablear();
    // Reactores HUD (standby grande + panel de IA).
    JarvisReactor.crear('reactor-standby', { mostrarTexto: false });
    JarvisReactor.crear('reactor-hud');
    JarvisUI.iniciarReloj();

    // Si el micrófono ya fue autorizado antes, Jarvis se arma solo al
    // abrir la página: queda esperando los dos aplausos sin clics.
    try {
      const permiso = await navigator.permissions.query({ name: 'microphone' });
      if (permiso.state === 'granted') prepararSistemas();
    } catch { /* navegador sin Permissions API: queda el botón */ }
    // Los paneles se cargan aunque siga en standby (útiles al activar).
    refrescarTodo();
    setInterval(refrescarEstado, 30_000);
    setInterval(refrescarClima, 10 * 60_000);
    setInterval(refrescarTareas, 60_000);
    setInterval(refrescarNotificaciones, 45_000);
  }

  principal();
})();
