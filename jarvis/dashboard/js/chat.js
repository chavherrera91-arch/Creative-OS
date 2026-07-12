// ============================================================
// JARVIS · Cliente de chat (streaming SSE sobre fetch)
// Envía comandos al servidor y recibe la respuesta en tiempo
// real: texto incremental, eventos de herramientas/delegación
// y acciones para el dashboard.
// ============================================================
'use strict';

const JarvisChat = (() => {
  // Sesión estable mientras la pestaña viva (contexto de conversación).
  const sesion = 'ses-' + Math.random().toString(36).slice(2, 10);

  /**
   * Envía un mensaje. Callbacks:
   *  - alTexto(delta)          texto incremental
   *  - alEvento(ev)            {tipo:'herramienta'|'delegacion'|'accion'|'error', ...}
   * Devuelve { texto, agente } al terminar.
   */
  async function enviar({ mensaje, agenteId = '', origen = 'texto', alTexto, alEvento }) {
    const respuesta = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mensaje, agenteId: agenteId || undefined, sesion, origen }),
    });
    if (!respuesta.ok || !respuesta.body) {
      throw new Error(`El servidor respondió ${respuesta.status}`);
    }

    const lector = respuesta.body.getReader();
    const decodificador = new TextDecoder();
    let bufer = '';
    let final = { texto: '', agente: 'ceo' };

    for (;;) {
      const { done, value } = await lector.read();
      if (done) break;
      bufer += decodificador.decode(value, { stream: true });

      let corte;
      while ((corte = bufer.indexOf('\n\n')) >= 0) {
        const bloque = bufer.slice(0, corte);
        bufer = bufer.slice(corte + 2);
        if (!bloque.startsWith('data: ')) continue;
        let evento;
        try {
          evento = JSON.parse(bloque.slice(6));
        } catch {
          continue;
        }
        if (evento.tipo === 'texto' && alTexto) alTexto(evento.delta);
        else if (evento.tipo === 'listo') final = { texto: evento.texto, agente: evento.agente };
        else if (evento.tipo === 'fin') { /* cierre */ }
        else if (alEvento) alEvento(evento);
      }
    }
    return final;
  }

  return { enviar, sesion };
})();
