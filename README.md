# ⚡ Creative OS

**El sistema operativo creativo para campañas de marketing.** Pega un producto (link de AliExpress, Amazon, Shopify, TikTok, cualquier tienda — o una imagen) y sal con una campaña completa lista para producir y testear.

## Cómo arrancarlo

```bash
npm install
npm run dev
```

Abre http://localhost:5173

> Node.js está instalado en `%LOCALAPPDATA%\nodejs-portable` y agregado a tu PATH de usuario. Si `npm` no se reconoce, abre una terminal nueva.

## Los 18 módulos

| Módulo | Qué hace |
|---|---|
| **Product Intelligence** | Problema, beneficios, audiencias, ángulos, objeciones, diferenciadores, precio y escalado |
| **Creative Score** | Puntuación 0-100 con métricas por estrellas y score por plataforma (TikTok, Meta, Shorts, Pinterest) |
| **Hook Generator** | 116+ hooks en 14 categorías emocionales, con buscador y filtros |
| **Ad Generator** | 10 anuncios completos: Meta, TikTok, Shorts, Reels, UGC, VSL, carrusel, imagen, GIF y banner |
| **Script Generator** | 36 guiones (15s → 3 min) con timing, voz en off y dirección visual por escena |
| **Visual Generator** | 3 storyboards completos: plano, sujeto, expresión, luz, texto, movimiento, duración y audio |
| **AI Image Prompts** | Prompts para GPT Image, Midjourney, Flux, Nano Banana, Hailuo y Kling |
| **AI Video Prompts** | Prompts para Veo, Kling, Hailuo, Runway y Pika |
| **UGC Generator** | 7 personalidades (Mamá, Doctor, Deportista, Estudiante, CEO, Pareja, Abuelo) con guion completo |
| **Competitor Analyzer** | Pega URL + copy del competidor → hooks, CTAs, framework, debilidades y cómo ganarle |
| **Creative Library** | Búsquedas pre-armadas en TikTok Creative Center, Meta Ad Library, Pinterest, YouTube y Google Trends |
| **Thumbnail Generator** | 6 conceptos de miniatura con preview, paleta, layout y prompt de IA |
| **Landing Copy** | Headline, beneficios, FAQ, garantía, CTAs, comparativa y reviews |
| **Offer Builder** | 2x1, bundle, regalo, descuento progresivo, urgencia y escasez — con matemática de margen |
| **Creative Planner** | Plan de producción de 4 semanas: qué crear, cuánto y para qué canal |
| **Viral Predictor** | Probabilidad viral con factores y plan de maximización |
| **Creative Iteration** | Describe tu anuncio → diagnóstico: qué eliminar, agregar, testear y cambiar |
| **A/B Testing** | 115+ variantes: 50 hooks, 20 CTAs, 20 thumbnails, 15 intros, 10 finales |

## Motor de generación

- **Motor local** (por defecto): funciona al instante, sin API keys. Base de conocimiento de marketing con 12 categorías de producto (cocina, hogar, belleza, fitness, mascotas, tech, bebé, moda, salud, auto, oficina) y generación combinatoria con semilla determinista.
- **Modo Claude** (opcional): en *Configuración*, pega tu API key de Anthropic. La estrategia (problema, ángulos, objeciones, 112 hooks, landing y guiones UGC) se regenera con IA real usando los datos del producto. La key se guarda solo en tu navegador.

## Exportar

Cada campaña se exporta como **Markdown** (Notion/Docs), **JSON** (integraciones) o copia directa al portapapeles. Las campañas se guardan automáticamente en el navegador.

## Suscripciones y créditos

Tres planes mensuales — **Gratis** ($0: 1 campaña, análisis), **Premium** ($10: 10 campañas, producción de contenido) y **Max** ($20: 50 campañas, arsenal completo) — con sistema de créditos por acción (campaña 10, competidor 5, diagnóstico 5) que se renuevan el día 1 de cada mes.

**Cuentas y pagos reales:** el código de Supabase (auth + validación de créditos en servidor) y Stripe (checkout + webhooks + portal de facturación) ya está integrado. Sigue **[SETUP.md](SETUP.md)** (~15 min) para conectar tus claves y activarlo. Sin claves, la app funciona en modo demo local.

## Stack

React 18 · TypeScript · Vite 6 · Tailwind CSS 4 · Supabase · Stripe · Vercel Functions · Anthropic SDK · lucide-react
