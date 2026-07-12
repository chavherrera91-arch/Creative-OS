# JARVIS · Director de operaciones para dropshipping

Asistente personal local inspirado en Jarvis: se activa con **dos aplausos**,
conversa **por voz en español**, tiene **memoria permanente en archivos**,
coordina **10 agentes especializados** con Claude (Opus 4.8) y abre
**Drop-Meta** automáticamente al despertar.

```
Dashboard  →  http://localhost:8200
Drop-Meta  →  http://localhost:8200/drop-meta/
```

---

## 1. Instalación

No hay nada que instalar: Jarvis usa el Node.js portable que ya existe en tu
equipo y **cero dependencias externas** propias (el SDK de Anthropic ya está en
`node_modules/` de Creative OS).

**Arrancar el servidor:**

```powershell
& "C:\Users\PC\AppData\Local\nodejs-portable\node.exe" "jarvis\core\server.js"
```

(o desde Claude Code: el servidor `jarvis` ya está registrado en
`.claude/launch.json`).

**Abrir el dashboard:** navega a `http://localhost:8200` en **Microsoft Edge**
(recomendado: tiene las mejores voces neuronales en español y el mejor
reconocimiento de voz) o Chrome.

**Primer uso:**

1. Pulsa **INICIAR SISTEMAS** (el navegador exige un clic antes de dar acceso
   a micrófono y audio — es una regla de seguridad de todos los navegadores).
2. Acepta el permiso de micrófono.
3. Da **dos aplausos**. Jarvis reproduce la música de bienvenida, dice
   *"Bienvenido a casa, señor."*, abre Drop-Meta y queda escuchando.

Desde la segunda vez, **ya no hace falta el clic**: si el permiso de micrófono
quedó concedido, la página se arma sola al abrirse y queda esperando los
aplausos.

### Modo aplicación y segundo plano

- **Escritorio**: el acceso directo **JARVIS** abre el centro de mando como
  aplicación propia (ventana sin pestañas, con Edge `--app`).
- **Arranque con Windows**: el acceso directo *Jarvis Servidor* de la carpeta
  Inicio lanza el servidor **oculto en segundo plano** al iniciar sesión
  (usa `herramientas/servidor-oculto.vbs`). Para desactivarlo: bórralo de
  `shell:startup`.
- Flujo diario: enciendes la PC → el servidor ya está corriendo → doble clic
  en JARVIS (o abre el navegador) → dos aplausos → a trabajar.

### Desde el teléfono (misma WiFi)

El servidor escucha en toda tu red local. El pie del dashboard muestra la
dirección exacta (p. ej. `http://192.168.100.14:8200`) — ábrela en el
navegador del teléfono y tendrás el dashboard completo, chat con los agentes,
tareas y Drop-Meta.

- La primera vez, Windows puede preguntar si permites conexiones de red para
  Node.js: marca **Redes privadas → Permitir** (ese cuadro lo debes aceptar
  tú; si no apareció, agrega tú mismo la regla del puerto 8200 en el
  Firewall de Windows).
- **Límite técnico**: la voz (micrófono/TTS) en el teléfono requiere HTTPS —
  los navegadores bloquean el micrófono en HTTP que no sea localhost. Por
  eso desde el móvil se usa por texto; la voz remota (túnel HTTPS con
  Tailscale/Cloudflare) está en la hoja de ruta.

### La interfaz central: NÚCLEO y CHAT

El panel central tiene dos vistas con botones: **◉ NÚCLEO** (el reactor
animado a pantalla completa, reactivo a la voz) y **💬 CHAT** (la
conversación). Al escribir un comando salta al chat solo; por voz se queda
en el núcleo, como Iron Man. **⬢ ABRIR DROP-META** abre la app integrada
encima del HUD (✕ VOLVER A JARVIS para regresar, ↗ para pestaña aparte).

## 2. Configuración

### Motor de IA: Ollama por defecto, Claude opcional (el "interruptor")

Jarvis funciona con **dos proveedores de IA intercambiables** sin tocar código.
La selección vive en `config.json` → `ia.proveedor`:

| Valor | Comportamiento |
|---|---|
| `"auto"` (por defecto) | Si hay clave de Claude en `secrets.json` → usa **Claude**. Si no hay clave → usa **Ollama** local automáticamente. |
| `"ollama"` | Fuerza Ollama aunque exista clave. |
| `"claude"` | Fuerza Claude (requiere clave). |

**Opción A — Ollama (gratis, local, privado):**

1. Instala Ollama desde [ollama.com](https://ollama.com) (Windows).
2. Descarga un modelo: `ollama pull llama3.1` (o `qwen2.5:14b`, `mistral`…).
3. Listo — Jarvis lo detecta solo en `http://127.0.0.1:11434`. El modelo se
   cambia en `config.json` → `ia.ollama.modelo`.

**Opción B — Claude (máxima calidad, de pago):**

```powershell
Copy-Item jarvis\config\secrets.example.json jarvis\config\secrets.json
# edita secrets.json y pega tu clave sk-ant-...
```

`secrets.json` está en `.gitignore`: nunca se sube al repositorio. También
sirve la variable de entorno `ANTHROPIC_API_KEY`. En modo `auto`, **agregar la
clave es todo lo que hace falta para subir de Ollama a Claude** — y borrarla
te devuelve a Ollama. Los agentes, la memoria, la voz y el dashboard funcionan
igual con ambos.

**Sin ninguno de los dos**, Jarvis sigue operativo en modo básico: hora,
fecha, clima, tareas, Drop-Meta y lectura de memoria.

Diferencias prácticas entre proveedores: con Claude hay *streaming* palabra a
palabra y *prompt caching* de la memoria; con Ollama la respuesta llega en un
bloque (el tool calling en streaming es frágil entre versiones de Ollama) y la
calidad depende del modelo que descargues.

### `jarvis/config/config.json`

| Clave | Qué controla |
|---|---|
| `puerto` | Puerto del servidor (8200) |
| `modelo` | Modelo de Claude (`claude-opus-4-8`) |
| `ciudad`, `latitud`, `longitud`, `zonaHoraria` | Clima y reloj |
| `saludo` | Frase que dice al activarse |
| `musicaIntro` | Canción de entrada de YouTube: `{ tipo: "youtube", url, volumen }`. Se reproduce con el reproductor oficial embebido al activar; controles flotantes para pausar ⏸, detener ⏹ o cambiarla ✏ (el cambio se guarda solo). La música baja automáticamente cuando Jarvis habla. |
| `musicaBienvenida` | Respaldo local si YouTube falla o no hay internet (pon tu `welcome.mp3` en `dashboard/assets/`); si tampoco existe, suena la fanfarria sintetizada |
| `voz` | Idioma, velocidad, tono y voz preferida del TTS |
| `aplausos.umbral` | Sensibilidad del detector (baja a 0.25 si no te detecta; sube a 0.4 si se activa solo) |
| `dropMeta.abrirAlActivar` | Abrir Drop-Meta al despertar |

## 3. Arquitectura

```
jarvis/
├── core/            Núcleo del servidor
│   ├── server.js      HTTP + API + estáticos (dashboard y Drop-Meta)
│   ├── ia.js          Fachada de IA: interruptor de proveedor, agentes, delegación
│   ├── claude.js      Proveedor Claude (SDK oficial, streaming, prompt caching)
│   ├── ollama.js      Proveedor Ollama (local, sin dependencias, tool calling)
│   ├── localbrain.js  Motor local sin IA (intenciones en español)
│   ├── memory.js      Memoria permanente (Markdown)
│   ├── store.js       Tareas, notificaciones, historial (JSON)
│   ├── logger.js      Logs diarios (JSON Lines)
│   └── utils.js       Helpers compartidos
├── memory/          usuario.md, negocio.md, objetivos.md, estrategias.md,
│                    proveedores.md, productos.md, anuncios.md, errores.md,
│                    aprendizajes.md  ← Jarvis los lee SIEMPRE antes de responder
├── agents/          10 agentes (CEO coordina y delega en los otros 9)
├── tools/           Herramientas de los agentes (memoria, tareas, documentos,
│                    archivos, automatizaciones, notificaciones)
├── automations/     Scripts ejecutables por el Automation Agent
├── integrations/    Clima (Open-Meteo, sin clave)
├── dashboard/       Interfaz HUD (HTML/CSS/JS puro, sin build)
├── config/          config.json + secrets.json (ignorado por git)
├── data/            Datos generados (ignorado por git)
├── docs/generados/  Documentos que crean los agentes
└── logs/            Un log por día
```

**Decisiones técnicas y por qué:**

- **Node puro sin dependencias** — tu Node es portable y la carpeta vive en
  OneDrive; evitar `npm install` elimina la mayor fuente de fallos y hace el
  proyecto trivial de mover/respaldar. El único paquete usado
  (`@anthropic-ai/sdk`) ya estaba instalado en la raíz.
- **Voz en el navegador (Web Speech API)** — en Windows, Edge trae voces
  neuronales en español y STT de alta calidad sin instalar nada ni pagar API
  de voz. Alternativas (Whisper local, Azure TTS) quedan como mejora futura.
- **Memoria en Markdown** — legible, editable a mano, versionable con git, y
  se inyecta al modelo con *prompt caching* (solo se re-procesa si cambió).
- **Agentes = prompts + herramientas, no procesos** — el CEO delega mediante
  la herramienta `consultar_agente`; simple, depurable y barato. Escalar a
  sub-agentes reales (Claude Agent SDK) es una mejora futura documentada.
- **JSON como almacenamiento** — para volúmenes de asistente personal, una
  base de datos sería complejidad sin beneficio. El módulo `store.js` aísla el
  acceso: si algún día hace falta SQLite, se cambia en un solo archivo.

## 4. Uso diario

**Por voz** (tras activar): habla con naturalidad.

- «¿Qué hora es?» · «¿Qué día es hoy?» · «¿Cómo está el clima?»
- «Agrega tarea revisar creativos de LUMBRA» · «¿Qué tengo pendiente?» ·
  «Completa tarea revisar creativos»
- «Abre Drop-Meta» · «Estado del sistema»
- Con IA: «Analiza si conviene subir el precio de la lámpara a 45 dólares»,
  «Dame cinco hooks para un video de TikTok del candle warmer», «Escribe la
  página de producto», «Diseña la campaña de Meta con 50 dólares diarios»…

**Por texto**: el campo inferior del Panel de IA. El selector elige agente
directo o deja que el CEO coordine.

**Memoria**: pide «guarda en memoria que…» y el agente escribirá en el archivo
correcto. También puedes editar los `.md` de `jarvis/memory/` a mano.

## 5. Fase 2 · Operaciones automáticas

### Daily CEO Report (8:00 AM)

El **programador** interno (`core/scheduler.js`) ejecuta cada mañana la
automatización `reporte-ceo`: ventas de Shopify (si está conectado), tareas
pendientes y de hoy, objetivos vigentes, candidatos de producto y foco
sugerido del día. El reporte se guarda en `docs/generados/`, aparece como
notificación y **Jarvis lo lee en voz alta** si el dashboard está activo.

La hora y las tareas programadas se editan en `config.json` → `programador`.
Puedes programar cualquier script de `automations/` con el mismo formato.

### Conexión con Shopify (opcional, solo lectura)

1. En Shopify: Configuración → Apps y canales de venta → Desarrollar apps →
   crear app → Admin API → permisos `read_orders` y `read_products` → instalar
   y copiar el token `shpat_...`.
2. En `config/secrets.json` agrega el bloque `shopify` (ver
   `secrets.example.json`).

Con eso se activan: ventas reales en el reporte diario, la vigilancia de
inventario, y las herramientas `ventas_de_hoy`, `pedidos_recientes` e
`inventario_agotado` para el CEO, el Data Analyst y el Automation Agent
(«Jarvis, ¿cuánto vendimos hoy?»).

### Agente de emergencias (vigilancia)

Cada 5 minutos Jarvis comprueba: Drop-Meta presente, Shopify accesible y
productos sin inventario. Cada condición avisa **una sola vez** al fallar
(notificación de alerta + voz) y otra al recuperarse. Las automatizaciones
programadas que fallen también disparan alerta.

### Product Lab (un comando → dossier completo)

Dile al CEO: **«Jarvis, analiza este producto: <producto>»** (o «haz el
laboratorio de X»). La herramienta `laboratorio_producto` encadena:

1. **Market Analyst** — viabilidad, competencia, veredicto.
2. **Creative Director** — 5 hooks + 2 conceptos de video.
3. **Copywriter** — página de producto completa.
4. **Media Buyer** — campaña Meta de validación (50 USD/día + kill rules).

y termina con: dossier en `docs/generados/`, candidato anotado en
`memory/productos.md` y tarea «Revisar dossier…» de prioridad alta.
Requiere motor de IA activo (Ollama o Claude); tarda varios minutos con
modelos locales — el progreso se ve en la Consola de Acciones.

### Webhooks para n8n (u otros sistemas)

Jarvis expone `POST /api/hooks/<nombre>` con cuerpo
`{ "texto": "...", "nivel": "info|exito|alerta", "hablar": true }` →
notificación en el dashboard (y por voz si `hablar`). En n8n basta un nodo
**HTTP Request** apuntando a `http://localhost:8200/api/hooks/meta-ads`, por
ejemplo, para que cualquier flujo externo le hable a Jarvis. Los flujos que
requieren APIs con app aprobada (Meta Ads, TikTok) conviene montarlos en n8n
cuando tengas esas credenciales; mientras tanto el Media Buyer puede analizar
un CSV exportado de Meta con `leer_archivo`.

## 6. Mantenimiento

| Tarea | Cómo |
|---|---|
| Ver logs | `jarvis/logs/jarvis-AAAA-MM-DD.log` (JSON Lines) |
| Respaldar | Copiar `jarvis/memory/`, `jarvis/data/` y `jarvis/config/` |
| Limpiar historial | Borrar `jarvis/data/history.json` |
| Reiniciar | Cortar el proceso de Node y volver a arrancar (los datos persisten) |
| Añadir automatización | Crear `jarvis/automations/mi-script.js` (Node); el Automation Agent la puede ejecutar por nombre |
| Añadir agente | Añadir entrada en `jarvis/agents/agents.js` (id, prompt, familias de herramientas) |
| Añadir herramienta | Definición + implementación en `jarvis/tools/tools.js`, asignar familia a los agentes |

## 7. Mejoras futuras (hoja de ruta)

**Corto plazo**
- [ ] Panel de edición de memoria dentro del dashboard (la API `PUT /api/memory/:archivo` ya existe).
- [ ] Palabra clave de activación por voz («Jarvis, …») además de los aplausos.
- [ ] Notificaciones del navegador (Web Notifications) además del panel.
- [ ] Recordatorios con hora que disparen TTS («recuérdame a las 5…»).

**Medio plazo**
- [x] Integración con Shopify (ventas, pedidos, inventario) — hecho en Fase 2.
- [x] Programador de tareas + Daily CEO Report + agente de emergencias — hecho en Fase 2.
- [x] Product Lab (pipeline idea → dossier completo) — hecho en Fase 2.
- [ ] Búsqueda web real para el Research Agent (herramienta `web_search` del lado del servidor con la API de Anthropic).
- [ ] Meta Ads Monitor con API oficial (requiere app aprobada por Meta); mientras tanto, análisis de CSV exportado.
- [ ] n8n como orquestador externo usando los webhooks `/api/hooks/*` (Telegram/Discord, correo, noticias).

**Largo plazo**
- [ ] Migrar agentes a Claude Agent SDK o Managed Agents para sub-agentes con contexto propio y ejecución más larga.
- [ ] Voz premium (TTS neuronal vía API) y STT con Whisper local para privacidad total.
- [ ] Arranque automático con Windows (Tarea programada que lance el servidor al iniciar sesión).
- [ ] App de escritorio (empaquetar con Electron o usar modo kiosco de Edge: `msedge --app=http://localhost:8200`).

## 8. Solución de problemas

| Síntoma | Causa probable / arreglo |
|---|---|
| No detecta los aplausos | Baja `aplausos.umbral` a 0.22–0.28. Aplaude fuerte y seco, cerca del micrófono. |
| Se activa solo con ruidos | Sube el umbral a 0.38–0.45. |
| No habla / voz robótica | Usa Edge. Ajusta `voz.vozPreferida` (p. ej. "Microsoft Dalia", "Microsoft Jorge"). |
| No me entiende / no escucha | El fallo exacto aparece ahora en la **Consola de Acciones** (permiso denegado, sin internet, sin micrófono…). Lo más común: permiso de micrófono denegado → candado de la barra de direcciones → Permitir → pulsa 🎙. El STT necesita internet. Usa Edge o Chrome. |
| «SIN IA» en el header | Ni Ollama corriendo ni clave de Claude. Instala Ollama (`ollama pull llama3.1`) o agrega la clave en `secrets.json`. |
| Ollama responde lento | Prueba un modelo más pequeño (`llama3.2:3b`) en `ia.ollama.modelo`, o cierra apps que usen GPU/RAM. |
| Ollama no usa herramientas | Algunos modelos no soportan *tools*; Jarvis reintenta sin ellas automáticamente. Usa `llama3.2:3b`, `llama3.1`, `qwen2.5` o `mistral-nemo` para tener herramientas. |
| La canción de entrada no suena | Necesita internet y que el video permita embeberse. Si falla, suena el respaldo local automáticamente. Cambia la canción con el botón ✏ de la barra de música. |
| Puerto ocupado | Cambia `puerto` en config.json o `JARVIS_PORT=8300` como variable de entorno. |
