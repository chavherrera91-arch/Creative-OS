// ============================================================
// JARVIS · UI: renderizado de paneles
// Reloj, sistema, clima, calendario, agentes, tareas,
// notificaciones, consola de acciones e historial.
// ============================================================
'use strict';

const JarvisUI = (() => {
  const $ = (id) => document.getElementById(id);

  function esc(s) {
    return String(s ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ---------- Reloj ----------
  function iniciarReloj(zona) {
    const pinta = () => {
      const ahora = new Date();
      $('reloj').textContent = ahora.toLocaleTimeString('es-MX', {
        hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZone: zona || undefined,
      });
      $('fecha').textContent = ahora.toLocaleDateString('es-MX', {
        weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: zona || undefined,
      });
    };
    pinta();
    setInterval(pinta, 1000);
  }

  // ---------- Estado del sistema ----------
  function pintarSistema(est) {
    const filas = [
      ['Sistema', est.sistema.plataforma],
      ['CPUs', est.sistema.cpus],
      ['RAM libre', `${est.sistema.memoriaLibreMB} / ${est.sistema.memoriaTotalMB} MB`],
      ['Proceso Jarvis', `${est.sistema.cargaProceso} MB`],
      ['Activo desde', new Date(est.encendidoDesde).toLocaleTimeString('es-MX')],
      ['Motor IA', est.ia.disponible ? `${est.ia.proveedor} · ${est.ia.modelo}` : 'ninguno (modo básico)'],
      ['Agentes', est.agentes],
    ];
    $('sistema-cuerpo').innerHTML = filas
      .map(([e, v]) => `<div class="dato"><span class="etq">${esc(e)}</span><span class="val">${esc(v)}</span></div>`)
      .join('');

    const chip = (id, ok, textoOk, textoMal, esAviso) => {
      const el = $(id);
      el.className = 'chip ' + (ok ? 'ok' : esAviso ? 'aviso' : 'mal');
      el.textContent = ok ? textoOk : textoMal;
    };
    chip('ind-internet', est.internet, 'RED ONLINE', 'SIN RED');
    chip(
      'ind-ia',
      est.ia.disponible,
      `IA ${(est.ia.proveedor || '').toUpperCase()}`,
      'SIN IA',
      true,
    );
    chip('ind-dropmeta', est.dropMeta.disponible, 'DROP-META OK', 'DROP-META ?');
  }

  // ---------- Clima ----------
  function pintarClima(c) {
    $('clima-cuerpo').innerHTML = `
      <div class="clima-principal">
        <span class="clima-temp">${esc(c.temperatura)}°</span>
        <span class="clima-desc">${esc(c.descripcion)}</span>
      </div>
      <div class="clima-extra">
        ${esc(c.ciudad)}<br>
        Máx ${esc(c.maxima)}° · Mín ${esc(c.minima)}°<br>
        Humedad ${esc(c.humedad)}% · Viento ${esc(c.viento)} km/h
      </div>`;
  }

  function pintarClimaError() {
    $('clima-cuerpo').innerHTML = '<div class="clima-extra">Sin datos de clima (¿sin internet?).</div>';
  }

  // ---------- Calendario ----------
  function pintarCalendario(tareas) {
    const hoy = new Date();
    const año = hoy.getFullYear();
    const mes = hoy.getMonth();
    const primerDia = new Date(año, mes, 1);
    const diasEnMes = new Date(año, mes + 1, 0).getDate();
    // Lunes = 0
    const offset = (primerDia.getDay() + 6) % 7;

    const conEvento = new Set(
      (tareas || [])
        .filter((t) => t.fecha && !t.hecha)
        .map((t) => t.fecha),
    );

    $('cal-titulo').textContent = hoy
      .toLocaleDateString('es-MX', { month: 'long', year: 'numeric' })
      .toUpperCase();

    let html = '<div class="cal-mes">';
    for (const d of ['L', 'M', 'X', 'J', 'V', 'S', 'D']) html += `<span class="cal-dow">${d}</span>`;
    for (let i = 0; i < offset; i++) html += '<span class="cal-dia fuera"></span>';
    for (let d = 1; d <= diasEnMes; d++) {
      const fecha = `${año}-${String(mes + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      const clases = ['cal-dia'];
      if (d === hoy.getDate()) clases.push('hoy');
      if (conEvento.has(fecha)) clases.push('evento');
      html += `<span class="${clases.join(' ')}" title="${fecha}">${d}</span>`;
    }
    html += '</div>';
    $('calendario-cuerpo').innerHTML = html;
  }

  // ---------- Agentes ----------
  const estadoAgentes = new Map(); // id -> 'activo' | 'trabajando'

  function pintarAgentes(lista) {
    $('agentes-cuerpo').innerHTML = lista
      .map((a) => {
        const estado = estadoAgentes.get(a.id) || 'activo';
        return `<div class="agente ${estado}" data-agente="${esc(a.id)}">
          <span class="estado-punto"></span>
          <span class="agente-nombre">${esc(a.emoji)} ${esc(a.nombre)}</span>
          <span class="agente-rol">${estado === 'trabajando' ? 'TRABAJANDO' : 'LISTO'}</span>
        </div>`;
      })
      .join('');
  }

  function marcarAgente(id, trabajando) {
    estadoAgentes.set(id, trabajando ? 'trabajando' : 'activo');
    const el = document.querySelector(`.agente[data-agente="${id}"]`);
    if (el) {
      el.className = `agente ${trabajando ? 'trabajando' : 'activo'}`;
      el.querySelector('.agente-rol').textContent = trabajando ? 'TRABAJANDO' : 'LISTO';
    }
  }

  // ---------- Tareas ----------
  function pintarTareas(tareas, acciones) {
    const cuerpo = $('tareas-cuerpo');
    if (!tareas.length) {
      cuerpo.innerHTML = '<div class="clima-extra">Sin tareas. Diga: "agrega tarea …"</div>';
      return;
    }
    const orden = [...tareas].sort((a, b) => Number(a.hecha) - Number(b.hecha));
    cuerpo.innerHTML = orden
      .map(
        (t) => `<div class="tarea ${t.hecha ? 'hecha' : ''} prioridad-${esc(t.prioridad)}" data-id="${esc(t.id)}">
          <input type="checkbox" ${t.hecha ? 'checked' : ''} title="Completar">
          <span class="tarea-titulo">${esc(t.titulo)}</span>
          ${t.fecha ? `<span class="tarea-fecha">${esc(t.fecha.slice(5))}</span>` : ''}
          <button class="tarea-borrar" title="Borrar">✕</button>
        </div>`,
      )
      .join('');

    cuerpo.querySelectorAll('.tarea').forEach((fila) => {
      const id = fila.dataset.id;
      fila.querySelector('input').addEventListener('change', (e) => acciones.alternar(id, e.target.checked));
      fila.querySelector('.tarea-borrar').addEventListener('click', () => acciones.borrar(id));
    });
  }

  // ---------- Notificaciones ----------
  function pintarNotificaciones(lista) {
    const cuerpo = $('notif-cuerpo');
    if (!lista.length) {
      cuerpo.innerHTML = '<div class="clima-extra">Sin notificaciones.</div>';
      return;
    }
    cuerpo.innerHTML = lista
      .slice(0, 20)
      .map(
        (n) => `<div class="notif nivel-${esc(n.nivel)}">
          ${esc(n.texto)}
          <span class="notif-hora">${new Date(n.creada).toLocaleString('es-MX')}</span>
        </div>`,
      )
      .join('');
  }

  // ---------- Consola ----------
  function consola(mensaje, clase = '') {
    const cuerpo = $('consola-cuerpo');
    const hora = new Date().toLocaleTimeString('es-MX', { hour12: false });
    const linea = document.createElement('div');
    linea.className = `linea ${clase}`;
    linea.innerHTML = `<span class="t">[${hora}]</span> ${esc(mensaje)}`;
    cuerpo.appendChild(linea);
    while (cuerpo.children.length > 80) cuerpo.removeChild(cuerpo.firstChild);
    cuerpo.scrollTop = cuerpo.scrollHeight;
  }

  // ---------- Historial ----------
  function pintarHistorial(lista) {
    const cuerpo = $('historial-cuerpo');
    if (!lista.length) {
      cuerpo.innerHTML = '<div class="clima-extra">Aún no hay comandos.</div>';
      return;
    }
    cuerpo.innerHTML = lista
      .slice(0, 25)
      .map(
        (h) => `<div class="hitem">
          <div class="hcmd">▸ ${esc(h.comando)}</div>
          <div class="hmeta">${esc(h.origen)} · ${esc(h.agente || '—')} · ${new Date(h.creada).toLocaleTimeString('es-MX')}</div>
        </div>`,
      )
      .join('');
  }

  // ---------- Conversación ----------
  function agregarMensaje(rol, texto, agente) {
    const cont = $('conversacion');
    const div = document.createElement('div');
    div.className = `msg ${rol}`;
    if (rol === 'jarvis' && agente) {
      const etiqueta = document.createElement('span');
      etiqueta.className = 'msg-agente';
      etiqueta.textContent = agente;
      div.appendChild(etiqueta);
    }
    const cuerpo = document.createElement('span');
    cuerpo.textContent = texto;
    div.appendChild(cuerpo);
    cont.appendChild(div);
    cont.scrollTop = cont.scrollHeight;
    return {
      añadir(delta) {
        cuerpo.textContent += delta;
        cont.scrollTop = cont.scrollHeight;
      },
      fijar(t) {
        cuerpo.textContent = t;
        cont.scrollTop = cont.scrollHeight;
      },
      etiquetar(nombre) {
        if (rol !== 'jarvis') return;
        let etiqueta = div.querySelector('.msg-agente');
        if (!etiqueta) {
          etiqueta = document.createElement('span');
          etiqueta.className = 'msg-agente';
          div.insertBefore(etiqueta, cuerpo);
        }
        etiqueta.textContent = nombre;
      },
    };
  }

  // ---------- Indicador de voz ----------
  function estadoVoz(estado) {
    const ind = $('voz-indicador');
    const txt = $('voz-texto');
    ind.classList.remove('escuchando', 'hablando');
    if (estado === 'escuchando') {
      ind.classList.add('escuchando');
      txt.textContent = 'Escuchando…';
    } else if (estado === 'hablando') {
      ind.classList.add('hablando');
      txt.textContent = 'Jarvis hablando…';
    } else if (estado === 'pensando') {
      ind.classList.add('hablando');
      txt.textContent = 'Procesando…';
    } else {
      txt.textContent = 'Micrófono en pausa';
    }
    // El reactor del panel refleja el mismo estado.
    window.JarvisReactor?.setModo(
      ['escuchando', 'hablando', 'pensando'].includes(estado) ? estado : 'inactivo',
      'reactor-hud',
    );
  }

  function mensajePie(texto) {
    $('pie-mensaje').textContent = texto;
  }

  return {
    iniciarReloj,
    pintarSistema,
    pintarClima,
    pintarClimaError,
    pintarCalendario,
    pintarAgentes,
    marcarAgente,
    pintarTareas,
    pintarNotificaciones,
    consola,
    pintarHistorial,
    agregarMensaje,
    estadoVoz,
    mensajePie,
  };
})();
