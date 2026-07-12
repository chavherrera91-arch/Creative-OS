// ============================================================
// JARVIS · Herramientas de los agentes
// Definiciones (esquema JSON para la API de Claude) +
// implementaciones locales. Agrupadas por familia para que
// cada agente reciba solo las que le corresponden.
// ============================================================
'use strict';

const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');
const { RAIZ, RAIZ_PROYECTO, rutaSegura, ahora } = require('../core/utils');
const memoria = require('../core/memory');
const store = require('../core/store');
const logger = require('../core/logger');
const shopify = require('../integrations/shopify');

const DIR_DOCS = path.join(RAIZ, 'docs', 'generados');
const DIR_AUTOMATIZACIONES = path.join(RAIZ, 'automations');

// ---------- Definiciones (por familia) ----------

const FAMILIAS = {
  memoria: [
    {
      name: 'leer_memoria',
      description:
        'Lee un archivo de memoria completo. Úsalo si necesitas releer un archivo con detalle (la memoria ya está resumida en tu contexto).',
      input_schema: {
        type: 'object',
        properties: {
          archivo: {
            type: 'string',
            description: 'Nombre del archivo: usuario, negocio, objetivos, estrategias, proveedores, productos, anuncios, errores o aprendizajes',
          },
        },
        required: ['archivo'],
      },
    },
    {
      name: 'guardar_en_memoria',
      description:
        'Anexa información nueva y duradera a un archivo de memoria. Úsalo cuando aprendas algo que deba influir en decisiones futuras.',
      input_schema: {
        type: 'object',
        properties: {
          archivo: { type: 'string', description: 'Archivo destino (p. ej. productos, errores, aprendizajes)' },
          texto: { type: 'string', description: 'Contenido en Markdown a anexar (conciso, un hecho por entrada)' },
        },
        required: ['archivo', 'texto'],
      },
    },
  ],
  tareas: [
    {
      name: 'listar_tareas',
      description: 'Devuelve la lista de tareas actual (pendientes y hechas).',
      input_schema: { type: 'object', properties: {} },
    },
    {
      name: 'crear_tarea',
      description: 'Crea una tarea nueva. Si tiene fecha (YYYY-MM-DD) aparecerá también en el calendario.',
      input_schema: {
        type: 'object',
        properties: {
          titulo: { type: 'string' },
          fecha: { type: 'string', description: 'Fecha objetivo YYYY-MM-DD (opcional)' },
          prioridad: { type: 'string', enum: ['alta', 'media', 'baja'] },
        },
        required: ['titulo'],
      },
    },
    {
      name: 'completar_tarea',
      description: 'Marca una tarea como hecha (por id, o por coincidencia de título si no conoces el id).',
      input_schema: {
        type: 'object',
        properties: {
          id: { type: 'string', description: 'Id exacto de la tarea (opcional)' },
          titulo: { type: 'string', description: 'Parte del título para buscarla (opcional)' },
        },
      },
    },
  ],
  documentos: [
    {
      name: 'crear_documento',
      description:
        'Crea un documento Markdown en jarvis/docs/generados (reportes, guiones, páginas de producto, análisis). Devuelve la ruta creada.',
      input_schema: {
        type: 'object',
        properties: {
          nombre: { type: 'string', description: 'Nombre del archivo sin extensión, en kebab-case' },
          contenido: { type: 'string', description: 'Contenido Markdown completo' },
        },
        required: ['nombre', 'contenido'],
      },
    },
  ],
  archivos: [
    {
      name: 'listar_carpeta',
      description: 'Lista archivos de una carpeta dentro del proyecto Creative OS (solo lectura).',
      input_schema: {
        type: 'object',
        properties: {
          ruta: { type: 'string', description: 'Ruta relativa a la raíz del proyecto, p. ej. "drop-meta" o "jarvis/docs"' },
        },
        required: ['ruta'],
      },
    },
    {
      name: 'leer_archivo',
      description: 'Lee un archivo de texto dentro del proyecto (máximo 50 KB).',
      input_schema: {
        type: 'object',
        properties: {
          ruta: { type: 'string', description: 'Ruta relativa a la raíz del proyecto' },
        },
        required: ['ruta'],
      },
    },
  ],
  automatizaciones: [
    {
      name: 'ejecutar_automatizacion',
      description:
        'Ejecuta un script registrado en jarvis/automations (solo scripts .js de esa carpeta; nada externo). Devuelve su salida.',
      input_schema: {
        type: 'object',
        properties: {
          nombre: { type: 'string', description: 'Nombre del script sin extensión, p. ej. "briefing-diario"' },
        },
        required: ['nombre'],
      },
    },
  ],
  notificaciones: [
    {
      name: 'notificar',
      description: 'Publica una notificación en el panel del dashboard.',
      input_schema: {
        type: 'object',
        properties: {
          texto: { type: 'string' },
          nivel: { type: 'string', enum: ['info', 'exito', 'alerta'] },
        },
        required: ['texto'],
      },
    },
  ],
  shopify: [
    {
      name: 'ventas_de_hoy',
      description:
        'Consulta en Shopify los pedidos y el total facturado de hoy. Úsala cuando pregunten por ventas, ingresos o pedidos del día.',
      input_schema: { type: 'object', properties: {} },
    },
    {
      name: 'pedidos_recientes',
      description: 'Lista los últimos pedidos de la tienda Shopify (número, total y estado de pago).',
      input_schema: {
        type: 'object',
        properties: {
          cantidad: { type: 'integer', description: 'Cuántos pedidos (máx 20, por defecto 5)' },
        },
      },
    },
    {
      name: 'inventario_agotado',
      description: 'Lista los productos/variantes de Shopify con inventario en cero o negativo.',
      input_schema: { type: 'object', properties: {} },
    },
  ],
  laboratorio: [
    {
      name: 'laboratorio_producto',
      description:
        'Product Lab: pipeline completo para evaluar un producto candidato con UN solo comando. Delega en cadena: Market Analyst (viabilidad) → Creative Director (hooks) → Copywriter (página) → Media Buyer (campaña), compila un dossier en docs/generados, registra el candidato en la memoria y crea la tarea de revisión. Úsala cuando pidan "analiza este producto" o "haz el laboratorio de X".',
      input_schema: {
        type: 'object',
        properties: {
          producto: { type: 'string', description: 'Nombre/descripción corta del producto' },
          costo_estimado: { type: 'string', description: 'Costo unitario estimado si se conoce (opcional)' },
          notas: { type: 'string', description: 'Contexto extra: público, ángulo, dónde se vio (opcional)' },
        },
        required: ['producto'],
      },
    },
  ],
};

/** Devuelve las definiciones de herramientas para un agente. */
function definicionesPara(agente, incluirDelegacion) {
  let defs = [];
  if (agente.herramientas.includes('*')) {
    defs = Object.values(FAMILIAS).flat();
  } else {
    for (const familia of agente.herramientas) {
      defs = defs.concat(FAMILIAS[familia] || []);
    }
  }
  if (incluirDelegacion) {
    defs = defs.concat([
      {
        name: 'consultar_agente',
        description:
          'Delega una tarea a un agente especializado y devuelve su respuesta. Agentes: product_hunter, market_analyst, creative_director, copywriter, media_buyer, data_analyst, research, automation, seo.',
        input_schema: {
          type: 'object',
          properties: {
            agente: { type: 'string', description: 'Id del agente' },
            encargo: { type: 'string', description: 'Instrucción completa y autónoma para el agente' },
          },
          required: ['agente', 'encargo'],
        },
      },
    ]);
  }
  return defs;
}

// ---------- Implementaciones ----------

function ejecutarAutomatizacion(nombre) {
  return new Promise((resolve) => {
    const limpio = String(nombre).replace(/[^a-z0-9\-_]/gi, '');
    const script = path.join(DIR_AUTOMATIZACIONES, `${limpio}.js`);
    if (!fs.existsSync(script)) {
      resolve(`No existe la automatización "${limpio}". Disponibles: ${listarAutomatizaciones().join(', ') || '(ninguna)'}`);
      return;
    }
    execFile(process.execPath, [script], { timeout: 60_000, cwd: RAIZ }, (err, stdout, stderr) => {
      if (err) resolve(`Error al ejecutar ${limpio}: ${err.message}\n${stderr || ''}`.trim());
      else resolve(stdout.trim() || '(sin salida)');
    });
  });
}

function listarAutomatizaciones() {
  try {
    return fs
      .readdirSync(DIR_AUTOMATIZACIONES)
      .filter((n) => n.endsWith('.js'))
      .map((n) => n.replace(/\.js$/, ''));
  } catch {
    return [];
  }
}

/**
 * Ejecuta una herramienta por nombre. `delegar` la aporta el motor de
 * chat (claude.js) para resolver consultar_agente sin ciclo de imports.
 */
async function ejecutar(nombre, entrada, { delegar } = {}) {
  switch (nombre) {
    case 'leer_memoria':
      return memoria.leer(entrada.archivo);

    case 'guardar_en_memoria':
      memoria.anexar(entrada.archivo, entrada.texto);
      logger.info('memoria', `Anexado a ${entrada.archivo}`);
      return `Guardado en ${entrada.archivo}.`;

    case 'listar_tareas':
      return JSON.stringify(store.listarTareas(), null, 2);

    case 'crear_tarea': {
      const tarea = store.crearTarea(entrada);
      return `Tarea creada: "${tarea.titulo}" (id ${tarea.id}${tarea.fecha ? `, fecha ${tarea.fecha}` : ''}).`;
    }

    case 'completar_tarea': {
      let objetivo = null;
      const tareas = store.listarTareas();
      if (entrada.id) objetivo = tareas.find((t) => t.id === entrada.id);
      if (!objetivo && entrada.titulo) {
        const busqueda = entrada.titulo.toLowerCase();
        objetivo = tareas.find((t) => !t.hecha && t.titulo.toLowerCase().includes(busqueda));
      }
      if (!objetivo) return 'No encontré esa tarea.';
      store.actualizarTarea(objetivo.id, { hecha: true });
      return `Tarea completada: "${objetivo.titulo}".`;
    }

    case 'crear_documento': {
      fs.mkdirSync(DIR_DOCS, { recursive: true });
      const nombreLimpio = String(entrada.nombre).replace(/[^a-z0-9\-_]/gi, '-').toLowerCase() || 'documento';
      const d = new Date();
      const fecha = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
      const ruta = rutaSegura(DIR_DOCS, `${fecha}-${nombreLimpio}.md`);
      fs.writeFileSync(ruta, entrada.contenido, 'utf8');
      const relativa = path.relative(RAIZ_PROYECTO, ruta);
      logger.info('documentos', `Documento creado: ${relativa}`);
      return `Documento creado en ${relativa}`;
    }

    case 'listar_carpeta': {
      const dir = rutaSegura(RAIZ_PROYECTO, entrada.ruta);
      const items = fs.readdirSync(dir, { withFileTypes: true }).map((d) => (d.isDirectory() ? d.name + '/' : d.name));
      return items.join('\n') || '(carpeta vacía)';
    }

    case 'leer_archivo': {
      const archivo = rutaSegura(RAIZ_PROYECTO, entrada.ruta);
      const stat = fs.statSync(archivo);
      if (stat.size > 50 * 1024) return `Archivo demasiado grande (${stat.size} bytes). Pide un fragmento específico.`;
      return fs.readFileSync(archivo, 'utf8');
    }

    case 'ejecutar_automatizacion':
      return ejecutarAutomatizacion(entrada.nombre);

    case 'notificar':
      store.notificar(entrada.texto, entrada.nivel || 'info');
      return 'Notificación publicada.';

    case 'consultar_agente': {
      if (!delegar) return 'La delegación no está disponible en este contexto.';
      return delegar(entrada.agente, entrada.encargo);
    }

    case 'ventas_de_hoy': {
      if (!shopify.disponible()) return 'Shopify no está configurado (secrets.json → shopify).';
      const v = await shopify.ventasDeHoy();
      return `Hoy: ${v.pedidos} pedido(s), ${v.total} ${v.moneda} facturados.`;
    }

    case 'pedidos_recientes': {
      if (!shopify.disponible()) return 'Shopify no está configurado (secrets.json → shopify).';
      const pedidos = await shopify.pedidosRecientes(entrada.cantidad || 5);
      if (!pedidos.length) return 'No hay pedidos registrados.';
      return pedidos
        .map((p) => `${p.numero}: ${p.total} ${p.moneda} (${p.estado}) — ${p.creado.slice(0, 16).replace('T', ' ')}`)
        .join('\n');
    }

    case 'inventario_agotado': {
      if (!shopify.disponible()) return 'Shopify no está configurado (secrets.json → shopify).';
      const agotados = await shopify.productosSinStock();
      if (!agotados.length) return 'Todo el inventario tiene existencias.';
      return `Sin stock (${agotados.length}):\n` + agotados.map((p) => `- ${p.titulo} (${p.cantidad})`).join('\n');
    }

    case 'laboratorio_producto': {
      if (!delegar) return 'El laboratorio requiere delegación: pídeselo al CEO.';
      const producto = entrada.producto;
      const contexto = [
        entrada.costo_estimado ? `Costo unitario estimado: ${entrada.costo_estimado}.` : '',
        entrada.notas ? `Contexto: ${entrada.notas}.` : '',
      ]
        .filter(Boolean)
        .join(' ');

      const pasos = [
        ['market_analyst', 'Análisis de mercado',
          `Evalúa la viabilidad de "${producto}" para dropshipping. ${contexto} Cubre: demanda, competencia, precios de mercado, diferenciación posible, riesgos y veredicto (entrar / no entrar / entrar con condiciones).`],
        ['creative_director', 'Hooks y conceptos',
          `Genera 5 hooks numerados y 2 conceptos de video (formato Reels/TikTok) para "${producto}". ${contexto}`],
        ['copywriter', 'Página de producto',
          `Escribe la página de producto completa de "${producto}": titular de beneficio, subtítulo, bullets, manejo de objeciones, garantía y CTA. ${contexto}`],
        ['media_buyer', 'Campaña inicial',
          `Diseña la campaña Meta Ads de validación para "${producto}" con 50 USD/día: estructura, públicos, evento de optimización y kill rules. ${contexto}`],
      ];

      const secciones = [`# Dossier · ${producto}`, contexto ? `> ${contexto}` : ''];
      for (const [agenteId, titulo, encargo] of pasos) {
        const resultado = await delegar(agenteId, encargo);
        secciones.push(`\n## ${titulo}\n\n${resultado}`);
      }

      const rutaDoc = await ejecutar(
        'crear_documento',
        { nombre: `dossier-${producto.slice(0, 40)}`, contenido: secciones.join('\n') },
        {},
      );
      memoria.anexar(
        'productos',
        `**Candidato (Product Lab):** ${producto}. ${contexto} Dossier: ${String(rutaDoc).replace('Documento creado en ', '')}`,
      );
      store.crearTarea({ titulo: `Revisar dossier de ${producto}`, prioridad: 'alta' });
      store.notificar(`🧪 Product Lab completado: ${producto}`, 'exito');

      return `Laboratorio completado para "${producto}". ${rutaDoc}. Candidato registrado en memoria y tarea de revisión creada. Resume al operador el veredicto del análisis en 2-3 frases.`;
    }

    default:
      return `Herramienta desconocida: ${nombre}`;
  }
}

module.exports = { definicionesPara, ejecutar, listarAutomatizaciones };
