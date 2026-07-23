# Guía de instalación — quantos

Todo esto se hace **en tu computadora** (no en la nube). El código ya está
listo; aquí están los pasos para pasar de "modo demo" a "en serio".

> Recordatorio: quantos es una plataforma de **investigación**. Nunca opera con
> dinero real — te ayuda a decidir y validar. Todo es en papel.

---

## 1. Instalar (una sola vez)

Necesitas Python 3.10 o más nuevo.

```bash
cd Creative-OS/quant
python -m venv .venv           # crea un entorno aislado
source .venv/bin/activate      # en Windows: .venv\Scripts\activate
pip install -e ".[data,dashboard]"
```

- `[data]` = conectores de datos reales (ccxt, duckdb, pyarrow).
- `[dashboard]` = la app visual (Streamlit).

Comprueba que quedó bien:

```bash
python -m pytest        # deberían pasar todos
```

---

## 2. Abrir la app (como Jarvis)

Un solo comando y se abre en el navegador:

```bash
quantos-app
```

Eliges un escenario y una semilla en la barra lateral, das **Run**, y ves todo:
el rendimiento, la decisión del Comité de Inversión con su explicación, el
histórico por régimen y la calibración de confianza. Funciona de inmediato con
datos sintéticos — no hay que cargar nada primero.

Si prefieres la terminal:

```bash
python examples/quickstart.py         # el recorrido completo de un tirón
python -m quantos.cli decide          # una decisión del comité
python -m quantos.cli backtest        # backtest + prueba de realidad (Sharpe deflactado)
```

---

## 3. Conectar datos reales de un exchange

Por defecto usa datos sintéticos (sin red). Para usar precios reales de un
exchange, instala ccxt (ya viene con `[data]`) y pásale un símbolo real:

```bash
# sin --synthetic, intenta bajar datos reales del exchange público
python -m quantos.cli decide --symbol BTC/USDT --bars 500
python -m quantos.cli backtest --symbol BTC/USDT --bars 1000
```

- Precios públicos (OHLCV) **no necesitan llave** — ccxt los baja del exchange.
- Solo lee datos; **nunca** coloca órdenes (invariante I1).
- Si el exchange no responde, cae automáticamente a modo sintético y lo dice
  (`data source: synthetic`).

Para llenar el Data Lake (histórico + noticias/macro/on-chain) y que la app lo
use:

```bash
python -m quantos.cli ingest --symbol BTC/USDT   # baja e indexa todo
python -m quantos.cli health                     # revisa frescura y estado
```

---

## 4. Encender la IA (Ollama gratis, o Claude)

quantos elige el mejor backend disponible **solo**, en este orden:

1. **Claude** (el más potente) — si defines tu llave:
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   ```
2. **OpenRouter** — si defines `OPENROUTER_API_KEY`.
3. **Ollama** (local, gratis, sin llave) — si tienes el servidor corriendo.
4. **Mock** — determinista y offline, para pruebas.

### Opción gratis: Ollama en tu máquina

1. Instala Ollama desde https://ollama.com
2. Descarga un modelo y déjalo corriendo:
   ```bash
   ollama pull llama3.2
   ollama serve        # normalmente ya queda corriendo solo
   ```
3. Listo — quantos lo detecta en `http://localhost:11434` y lo usa
   automáticamente. No hay que configurar nada más.

¿Otro modelo o dirección? Variables opcionales:

```bash
export QUANTOS_OLLAMA_URL=http://localhost:11434
export QUANTOS_LLM_MODEL=llama3.2      # o el que prefieras
export QUANTOS_LLM_BACKEND=auto        # auto | claude | openrouter | ollama | mock
```

> Las llaves y URLs solo se leen del entorno — **nunca** se guardan en el código.

---

## 5. (Opcional) Publicarla en internet con un link

Abrir la app localmente (`quantos-app`) es lo normal para investigar. Si además
quieres un **link público** para verla desde el teléfono o compartirla, hay que
alojar el servidor de Streamlit en algún lado (por ejemplo Streamlit Community
Cloud, un VPS, o un contenedor Docker). Eso ya depende de tu cuenta/servidor;
avísame y te dejo los pasos para el que prefieras.

---

## Resumen

| Quiero… | Comando |
|---|---|
| Abrir la app visual | `quantos-app` |
| El recorrido completo en terminal | `python examples/quickstart.py` |
| Una decisión del comité | `python -m quantos.cli decide --symbol BTC/USDT` |
| Un backtest honesto | `python -m quantos.cli backtest --symbol BTC/USDT` |
| Bajar datos reales | `python -m quantos.cli ingest --symbol BTC/USDT` |
| Usar Claude | `export ANTHROPIC_API_KEY=...` |
| Usar IA gratis | instalar Ollama + `ollama pull llama3.2` |
