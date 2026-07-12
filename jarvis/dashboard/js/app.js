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

  async function activar(origen) {
    if (activado) return;
    activado = true;

    // 1) Música de bienvenida.
    JarvisAudio.pausarDeteccion();
    await JarvisAudio.bienvenida(CONFIG.musicaBienvenida);

    // 2) Mostrar el centro de mando.
    $('standby').classList.add('oculto');
    $('hud').classList.remove('oculto');
    JarvisUI.consola(`Activación por ${origen === 'aplausos' ? 'doble aplauso' : 'botón'}.`, 'ok');

    // 3) Saludo por voz.
    await JarvisVoz.decir(CONFIG.saludo || 'Bienvenido a casa, señor.');

    // 4) Abrir Drop-Meta.
    if (CONFIG.dropMeta?.abrirAlActivar) {
      abrirDropMeta(true);
    }

    // 5) Escucha continua de comandos.
    if (JarvisVoz.soportaSTT) {
      JarvisVoz.escuchar(procesarComando);
      $('btn-mic').classList.add('activo');
    } else {
      JarvisUI.consola('Este navegador no soporta reconocimiento de voz. Use Edge o Chrome.', 'error');
      JarvisUI.estadoVoz('inactivo');
    }

    refrescarTodo();
  }

  // ---------- Drop-Meta ----------

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
    window.open('/drop-meta/', 'dropmeta');
    JarvisUI.consola('Drop-Meta abierto en una pestaña.', 'accion');
  }

  // ---------- Comandos (voz o texto) ----------

  async function procesarComando(texto, origen = 'voz') {
    if (ocupado) return;
    ocupado = true;
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
      JarvisUI.pintarSistema(await (await fetch('/api/status')).json());
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

  async function refrescarNotificaciones() {
    try {
      JarvisUI.pintarNotificaciones(await (await fetch('/api/notifications')).json());
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
    // Los paneles se cargan aunque siga en standby (útiles al activar).
    refrescarTodo();
    setInterval(refrescarEstado, 30_000);
    setInterval(refrescarClima, 10 * 60_000);
    setInterval(refrescarTareas, 60_000);
    setInterval(refrescarNotificaciones, 45_000);
  }

  principal();
})();
