// ============================================================
// JARVIS · Reactor HUD (canvas)
// Visualización circular estilo interfaz de alta tecnología:
// anillos concéntricos, aspas de turbina, arcos laterales,
// hexágonos y lecturas de porcentaje.
//
// Es AUDIO-REACTIVO:
//  - modo "hablando":   envolvente de voz simulada (sílabas ~5 Hz)
//                       + pulsos reales por palabra del TTS (onboundary)
//  - modo "escuchando": nivel real del micrófono (JarvisAudio.getNivel)
//  - modo "pensando":   barrido rápido de procesamiento
//  - modo "inactivo":   respiración lenta en reposo
// ============================================================
'use strict';

const JarvisReactor = (() => {
  const instancias = new Map();

  // Utilidad: ruido suave determinista (para variación orgánica).
  function ruido(t, semilla) {
    return (
      Math.sin(t * 1.7 + semilla) * 0.5 +
      Math.sin(t * 3.1 + semilla * 2.7) * 0.3 +
      Math.sin(t * 5.3 + semilla * 1.3) * 0.2
    ) * 0.5 + 0.5;
  }

  class Reactor {
    constructor(canvas, opciones = {}) {
      this.canvas = canvas;
      this.ctx = canvas.getContext('2d');
      this.modo = 'inactivo';
      this.nivel = 0;        // nivel visual actual (suavizado)
      this.objetivo = 0;     // nivel al que tiende
      this.pulsoExtra = 0;   // pico por palabra (decae solo)
      this.rot = { lenta: 0, media: 0, rapida: 0, barrido: 0 };
      this.t0 = performance.now();
      this.mostrarTexto = opciones.mostrarTexto !== false;
      this.animar = this.animar.bind(this);
      requestAnimationFrame(this.animar);
    }

    setModo(modo) {
      this.modo = modo;
    }

    pulso(fuerza = 0.55) {
      this.pulsoExtra = Math.min(1, this.pulsoExtra + fuerza);
    }

    // --- Fuente del nivel según el modo ---
    calcularObjetivo(t) {
      switch (this.modo) {
        case 'hablando': {
          // Envolvente de habla: modulación silábica (~5 Hz) con
          // micro-pausas, más el pulso real de cada palabra.
          const silaba = ruido(t * 5.2, 3.7);
          const frase = ruido(t * 0.7, 9.1);           // respiración de frase
          const pausa = frase < 0.18 ? 0.12 : 1;        // micro-silencios
          return Math.min(1, (0.25 + silaba * 0.55) * pausa + this.pulsoExtra * 0.6);
        }
        case 'escuchando': {
          const mic = (window.JarvisAudio && JarvisAudio.getNivel) ? JarvisAudio.getNivel() : 0;
          // Ganancia para que una voz normal se vea viva.
          return Math.min(1, mic * 4.5 + 0.06);
        }
        case 'pensando':
          return 0.35 + ruido(t * 2.2, 5.5) * 0.25;
        default:
          return 0.07 + ruido(t * 0.5, 1.1) * 0.06; // reposo, respiración lenta
      }
    }

    animar(ahora) {
      const t = (ahora - this.t0) / 1000;
      const dt = Math.min(0.05, (ahora - (this.prev || ahora)) / 1000 || 0.016);
      this.prev = ahora;

      // Suavizado asimétrico: sube rápido (ataque), baja lento (caída).
      this.objetivo = this.calcularObjetivo(t);
      const k = this.objetivo > this.nivel ? 14 : 5;
      this.nivel += (this.objetivo - this.nivel) * Math.min(1, k * dt);
      this.pulsoExtra = Math.max(0, this.pulsoExtra - dt * 2.4);

      // Velocidades de giro según actividad.
      const actividad = 0.25 + this.nivel * 1.6 + (this.modo === 'pensando' ? 1.2 : 0);
      this.rot.lenta += dt * 0.15 * actividad;
      this.rot.media -= dt * 0.4 * actividad;
      this.rot.rapida += dt * 0.9 * actividad;
      this.rot.barrido += dt * (this.modo === 'pensando' ? 3.4 : 0.8 + this.nivel * 2.2);

      this.dibujar(t);
      requestAnimationFrame(this.animar);
    }

    dibujar(t) {
      const { ctx, canvas } = this;
      const W = canvas.width;
      const H = canvas.height;
      const cx = W / 2;
      const cy = H / 2;
      const R = Math.min(W, H) / 2 - 12;
      const n = this.nivel;

      ctx.clearRect(0, 0, W, H);

      const CIAN = '#40d0ff';
      const CIAN_VIVO = '#9ef1ff';
      const alfa = (a) => `rgba(64, 208, 255, ${a})`;

      // ── Arcos laterales (como los soportes de la imagen) ──
      ctx.lineWidth = 2;
      for (const lado of [-1, 1]) {
        ctx.beginPath();
        ctx.strokeStyle = alfa(0.35 + n * 0.3);
        ctx.arc(cx, cy, R * 0.99, lado === 1 ? -0.55 : Math.PI - 0.55, lado === 1 ? 0.55 : Math.PI + 0.55);
        ctx.stroke();
        // marcas cortas sobre el arco
        for (let i = -3; i <= 3; i++) {
          const ang = (lado === 1 ? 0 : Math.PI) + i * 0.16;
          const r1 = R * 1.02, r2 = R * (1.02 + 0.035 * (i % 2 === 0 ? 1.6 : 1));
          ctx.beginPath();
          ctx.strokeStyle = alfa(0.25 + n * 0.35);
          ctx.moveTo(cx + Math.cos(ang) * r1, cy + Math.sin(ang) * r1);
          ctx.lineTo(cx + Math.cos(ang) * r2, cy + Math.sin(ang) * r2);
          ctx.stroke();
        }
      }

      // ── Anillo exterior fino ──
      ctx.beginPath();
      ctx.strokeStyle = alfa(0.22);
      ctx.lineWidth = 1;
      ctx.arc(cx, cy, R * 0.92, 0, Math.PI * 2);
      ctx.stroke();

      // ── Turbina: aspas radiales (reaccionan al nivel) ──
      const aspas = 48;
      for (let i = 0; i < aspas; i++) {
        const ang = (i / aspas) * Math.PI * 2 + this.rot.lenta;
        const individual = ruido(t * 3 + i * 0.6, i); // cada aspa vibra distinto
        const largo = 0.06 + n * 0.085 * (0.5 + individual);
        const r1 = R * 0.78;
        const r2 = R * (0.78 + largo);
        const brillo = 0.35 + n * 0.55 * individual;
        ctx.beginPath();
        ctx.strokeStyle = alfa(Math.min(0.95, brillo));
        ctx.lineWidth = 3.2;
        ctx.shadowColor = CIAN;
        ctx.shadowBlur = 6 + n * 14;
        ctx.moveTo(cx + Math.cos(ang) * r1, cy + Math.sin(ang) * r1);
        ctx.lineTo(cx + Math.cos(ang) * r2, cy + Math.sin(ang) * r2);
        ctx.stroke();
      }
      ctx.shadowBlur = 0;

      // ── Barrido brillante (segmento que recorre la turbina) ──
      ctx.beginPath();
      ctx.strokeStyle = alfa(0.55 + n * 0.4);
      ctx.lineWidth = 5;
      ctx.shadowColor = CIAN;
      ctx.shadowBlur = 18;
      ctx.arc(cx, cy, R * 0.845, this.rot.barrido, this.rot.barrido + 0.9 + n * 0.8);
      ctx.stroke();
      ctx.shadowBlur = 0;

      // ── Anillo discontinuo medio (gira al revés) ──
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(this.rot.media);
      ctx.beginPath();
      ctx.setLineDash([10, 7]);
      ctx.strokeStyle = alfa(0.4 + n * 0.3);
      ctx.lineWidth = 2;
      ctx.arc(0, 0, R * 0.66, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.restore();

      // ── Dientes internos (sierra fina, giro rápido) ──
      const dientes = 36;
      for (let i = 0; i < dientes; i++) {
        const ang = (i / dientes) * Math.PI * 2 + this.rot.rapida;
        const r1 = R * 0.52;
        const r2 = R * (0.52 + (i % 3 === 0 ? 0.06 : 0.035));
        ctx.beginPath();
        ctx.strokeStyle = alfa(0.4 + n * 0.4);
        ctx.lineWidth = 2;
        ctx.moveTo(cx + Math.cos(ang) * r1, cy + Math.sin(ang) * r1);
        ctx.lineTo(cx + Math.cos(ang) * r2, cy + Math.sin(ang) * r2);
        ctx.stroke();
      }

      // ── Anillo del núcleo ──
      ctx.beginPath();
      ctx.strokeStyle = alfa(0.6 + n * 0.35);
      ctx.lineWidth = 2.5;
      ctx.shadowColor = CIAN;
      ctx.shadowBlur = 10 + n * 20;
      ctx.arc(cx, cy, R * 0.42, 0, Math.PI * 2);
      ctx.stroke();
      ctx.shadowBlur = 0;

      // ── Núcleo brillante (pulsa con la voz) ──
      const rNucleo = R * (0.16 + n * 0.16 + Math.sin(t * 2.1) * 0.01);
      const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, rNucleo * 2.6);
      grad.addColorStop(0, `rgba(230, 253, 255, ${0.85 + n * 0.15})`);
      grad.addColorStop(0.25, `rgba(158, 241, 255, ${0.55 + n * 0.4})`);
      grad.addColorStop(0.6, alfa(0.25 + n * 0.35));
      grad.addColorStop(1, 'rgba(64, 208, 255, 0)');
      ctx.beginPath();
      ctx.fillStyle = grad;
      ctx.arc(cx, cy, rNucleo * 2.6, 0, Math.PI * 2);
      ctx.fill();

      // Iris central (arco segmentado pequeño que gira)
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(-this.rot.rapida * 1.4);
      ctx.beginPath();
      ctx.setLineDash([5, 4]);
      ctx.strokeStyle = `rgba(230, 253, 255, ${0.6 + n * 0.4})`;
      ctx.lineWidth = 2;
      ctx.arc(0, 0, R * 0.1, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.restore();

      // ── Hexágonos decorativos (esquina inferior izquierda) ──
      this.hexCluster(cx - R * 1.18, cy + R * 0.62, 9, 0.2 + n * 0.25, t);
      this.hexCluster(cx + R * 1.12, cy - R * 0.7, 7, 0.16 + n * 0.2, t + 3);

      // ── Lecturas de porcentaje (dinámicas, estilo HUD) ──
      if (this.mostrarTexto) {
        const pct = Math.round(this.nivel * 100);
        ctx.font = '600 13px "Share Tech Mono", monospace';
        ctx.fillStyle = alfa(0.85);
        ctx.textAlign = 'left';
        ctx.fillText(`${pct}%`, 8, 18);
        ctx.strokeStyle = alfa(0.5);
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(4, 24); ctx.lineTo(34, 24); ctx.lineTo(46, 36);
        ctx.stroke();

        const etiquetas = { inactivo: 'STANDBY', escuchando: 'AUDIO IN', hablando: 'VOZ OUT', pensando: 'PROCESO' };
        ctx.textAlign = 'right';
        ctx.fillStyle = alfa(0.7);
        ctx.fillText(etiquetas[this.modo] || '—', W - 8, H - 10);
        ctx.beginPath();
        ctx.moveTo(W - 4, H - 24); ctx.lineTo(W - 40, H - 24); ctx.lineTo(W - 52, H - 36);
        ctx.stroke();

        // mini barras (nivel espectral falso pero coherente con el nivel)
        ctx.textAlign = 'left';
        for (let i = 0; i < 6; i++) {
          const h = 3 + ruido(t * 6 + i, i * 2.2) * 14 * (0.25 + n);
          ctx.fillStyle = alfa(0.5 + n * 0.4);
          ctx.fillRect(W - 60 + i * 7, 20 - h, 4, h);
        }
      }
    }

    hexCluster(x, y, r, alfaBase, t) {
      const { ctx } = this;
      const offsets = [[0, 0], [1.8, 0], [0.9, 1.55], [-0.9, 1.55]];
      offsets.forEach(([dx, dy], i) => {
        const brillo = alfaBase * (0.5 + ruido(t * 1.5 + i, i * 4) * 0.8);
        ctx.beginPath();
        ctx.strokeStyle = `rgba(64, 208, 255, ${Math.min(0.7, brillo)})`;
        ctx.lineWidth = 1;
        for (let k = 0; k <= 6; k++) {
          const ang = (k / 6) * Math.PI * 2 + Math.PI / 6;
          const px = x + dx * r + Math.cos(ang) * r;
          const py = y + dy * r + Math.sin(ang) * r;
          if (k === 0) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);
        }
        ctx.stroke();
      });
    }
  }

  function crear(canvasId, opciones) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;
    const r = new Reactor(canvas, opciones);
    instancias.set(canvasId, r);
    return r;
  }

  function setModo(modo, canvasId) {
    if (canvasId) {
      const r = instancias.get(canvasId);
      if (r) r.setModo(modo);
    } else {
      for (const r of instancias.values()) r.setModo(modo);
    }
  }

  function pulso(fuerza) {
    for (const r of instancias.values()) r.pulso(fuerza);
  }

  return { crear, setModo, pulso };
})();

// Referencia global explícita (const de nivel superior no toca window).
window.JarvisReactor = JarvisReactor;
