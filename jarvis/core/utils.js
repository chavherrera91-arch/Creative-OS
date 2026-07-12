// ============================================================
// JARVIS · Utilidades del núcleo
// Helpers compartidos por todos los módulos del servidor.
// ============================================================
'use strict';

const fs = require('fs');
const path = require('path');

const RAIZ = path.resolve(__dirname, '..');          // carpeta jarvis/
const RAIZ_PROYECTO = path.resolve(RAIZ, '..');       // Creative OS/

/** Lee un JSON de disco; devuelve `porDefecto` si no existe o está corrupto. */
function leerJSON(ruta, porDefecto = null) {
  try {
    return JSON.parse(fs.readFileSync(ruta, 'utf8'));
  } catch {
    return porDefecto;
  }
}

/** Escribe un JSON con formato legible, creando carpetas intermedias. */
function escribirJSON(ruta, datos) {
  fs.mkdirSync(path.dirname(ruta), { recursive: true });
  fs.writeFileSync(ruta, JSON.stringify(datos, null, 2), 'utf8');
}

/**
 * Resuelve una ruta relativa DENTRO de una base y rechaza cualquier
 * intento de escape (../, rutas absolutas, enlaces). Sandbox de archivos.
 */
function rutaSegura(base, relativa) {
  const destino = path.resolve(base, relativa);
  if (destino !== base && !destino.startsWith(base + path.sep)) {
    throw new Error(`Ruta fuera del área permitida: ${relativa}`);
  }
  return destino;
}

/** Lee el cuerpo de una petición HTTP como JSON (con límite de tamaño). */
function cuerpoJSON(req, limite = 1024 * 1024) {
  return new Promise((resolve, reject) => {
    let total = 0;
    const trozos = [];
    req.on('data', (t) => {
      total += t.length;
      if (total > limite) {
        reject(new Error('Cuerpo demasiado grande'));
        req.destroy();
        return;
      }
      trozos.push(t);
    });
    req.on('end', () => {
      if (trozos.length === 0) return resolve({});
      try {
        resolve(JSON.parse(Buffer.concat(trozos).toString('utf8')));
      } catch {
        reject(new Error('JSON inválido'));
      }
    });
    req.on('error', reject);
  });
}

/** Responde JSON con el código indicado. */
function responderJSON(res, codigo, datos) {
  const cuerpo = JSON.stringify(datos);
  res.writeHead(codigo, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
  });
  res.end(cuerpo);
}

/** Prepara una respuesta Server-Sent Events y devuelve un emisor. */
function iniciarSSE(res) {
  res.writeHead(200, {
    'Content-Type': 'text/event-stream; charset=utf-8',
    'Cache-Control': 'no-store',
    Connection: 'keep-alive',
    'X-Accel-Buffering': 'no',
  });
  return {
    enviar(evento) {
      res.write(`data: ${JSON.stringify(evento)}\n\n`);
    },
    cerrar() {
      res.write('data: {"tipo":"fin"}\n\n');
      res.end();
    },
  };
}

/** Identificador corto único (suficiente para tareas/notificaciones locales). */
function idCorto() {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
}

/** Marca de tiempo ISO local. */
function ahora() {
  return new Date().toISOString();
}

const TIPOS_MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.mp3': 'audio/mpeg',
  '.wav': 'audio/wav',
  '.ogg': 'audio/ogg',
  '.woff2': 'font/woff2',
};

/** Sirve un archivo estático desde `base` (con sandbox). Devuelve true si respondió. */
function servirEstatico(res, base, relativa) {
  let destino;
  try {
    destino = rutaSegura(base, relativa);
  } catch {
    return false;
  }
  let stat;
  try {
    stat = fs.statSync(destino);
  } catch {
    return false;
  }
  if (stat.isDirectory()) {
    destino = path.join(destino, 'index.html');
    try {
      stat = fs.statSync(destino);
    } catch {
      return false;
    }
  }
  const mime = TIPOS_MIME[path.extname(destino).toLowerCase()] || 'application/octet-stream';
  res.writeHead(200, { 'Content-Type': mime, 'Content-Length': stat.size, 'Cache-Control': 'no-cache' });
  fs.createReadStream(destino).pipe(res);
  return true;
}

/**
 * Localiza la carpeta de Drop-Meta probando varias ubicaciones:
 * la configurada (p. ej. "../drop-meta" en Creative OS) y una copia
 * dentro de jarvis/ ("drop-meta"), útil en el repo independiente.
 */
function rutaDropMeta(rutaConfigurada) {
  const candidatas = [
    path.resolve(RAIZ, rutaConfigurada || '../drop-meta'),
    path.join(RAIZ, 'drop-meta'),
  ];
  for (const c of candidatas) {
    if (fs.existsSync(path.join(c, 'index.html'))) return c;
  }
  return candidatas[0];
}

module.exports = {
  RAIZ,
  RAIZ_PROYECTO,
  rutaDropMeta,
  leerJSON,
  escribirJSON,
  rutaSegura,
  cuerpoJSON,
  responderJSON,
  iniciarSSE,
  idCorto,
  ahora,
  servirEstatico,
};
