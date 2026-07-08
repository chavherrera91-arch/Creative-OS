import React, { useRef, useState } from "react";
import { ImagePlus, Link2, Loader2, Rocket, Sparkles, X } from "lucide-react";
import { useApp } from "../store";
import { Card, Field, inputCls, SectionHeader } from "../components/ui";
import { CATEGORIES, detectCategory } from "../engine/data";
import { detectSourceType, generateCampaign, guessNameFromUrl, SOURCE_LABEL } from "../engine/generate";
import { enhanceWithClaude } from "../engine/claude";
import type { ProductInput } from "../types";

const STEPS = [
  "Analizando el producto…",
  "Detectando ángulos de venta…",
  "Calculando Creative Score…",
  "Generando 140+ hooks…",
  "Escribiendo guiones (15s a 3 min)…",
  "Creando storyboards y prompts de IA…",
  "Diseñando UGC, landing y ofertas…",
  "Armando el plan de testeo A/B…",
];

export default function NewCampaignView() {
  const { addCampaign, setView, settings } = useApp();
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [price, setPrice] = useState("");
  const [audience, setAudience] = useState("");
  const [category, setCategory] = useState("");
  const [image, setImage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState(0);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const sourceType = image && !url ? "imagen" : detectSourceType(url);
  const detectedCat = detectCategory(`${name} ${desc} ${url}`);

  const onUrlChange = (v: string) => {
    setUrl(v);
    if (!name.trim()) {
      const guessed = guessNameFromUrl(v);
      if (guessed) setName(guessed);
    }
  };

  const onFile = (f: File | null) => {
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => setImage(reader.result as string);
    reader.readAsDataURL(f);
  };

  const generate = async () => {
    const finalName = name.trim() || guessNameFromUrl(url) || "";
    if (!finalName) {
      setError("Escribe el nombre del producto (o pega una URL de la que se pueda deducir).");
      return;
    }
    setError("");
    setLoading(true);
    setStep(0);

    const input: ProductInput = {
      name: finalName,
      description: desc.trim(),
      sourceUrl: url.trim(),
      sourceType,
      price: price.trim(),
      imageDataUrl: image,
      audienceHint: audience.trim(),
      categoryId: category || detectedCat.id,
    };

    // Animación de pasos mientras genera
    const timer = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), settings.useClaude && settings.apiKey ? 4500 : 350);

    try {
      let campaign = generateCampaign(input);
      if (settings.useClaude && settings.apiKey) {
        try {
          campaign = await enhanceWithClaude(input, campaign, settings, setStatus);
        } catch (e) {
          console.error("Claude enhancement failed, using local engine:", e);
          setStatus("La API de Claude falló — usando el motor local.");
          await new Promise((r) => setTimeout(r, 1200));
        }
      } else {
        // Pequeña pausa para que la animación se aprecie
        await new Promise((r) => setTimeout(r, 2800));
      }
      addCampaign(campaign);
      setView("overview");
    } finally {
      clearInterval(timer);
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] fade-up">
        <div className="w-16 h-16 rounded-2xl grad-btn flex items-center justify-center mb-6">
          <Loader2 size={28} className="text-white spinner" />
        </div>
        <h2 className="text-xl font-bold mb-1">Construyendo tu campaña</h2>
        <p className="text-sm text-zinc-500 mb-8">{status || "Esto toma unos segundos…"}</p>
        <div className="space-y-2.5 w-80">
          {STEPS.map((s, i) => (
            <div key={i} className={`flex items-center gap-2.5 text-sm transition-opacity ${i <= step ? "opacity-100" : "opacity-25"}`}>
              <div className={`w-1.5 h-1.5 rounded-full ${i < step ? "bg-emerald-400" : i === step ? "bg-cyan-400 pulse-glow" : "bg-zinc-700"}`} />
              <span className={i < step ? "text-zinc-500 line-through decoration-zinc-700" : "text-zinc-300"}>{s}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="fade-up max-w-3xl mx-auto">
      <SectionHeader
        title="Nueva campaña"
        subtitle="Pega un link de AliExpress, Amazon, Shopify, TikTok o cualquier tienda — o sube una imagen. La IA construye todo lo demás."
      />

      <Card className="space-y-5">
        <Field label="Link del producto" hint={url ? `Fuente detectada: ${SOURCE_LABEL[sourceType]}` : "AliExpress · Amazon · Shopify · TikTok · Cualquier tienda"}>
          <div className="relative">
            <Link2 size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-600" />
            <input
              className={`${inputCls} pl-10`}
              placeholder="https://es.aliexpress.com/item/…"
              value={url}
              onChange={(e) => onUrlChange(e.target.value)}
            />
          </div>
        </Field>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Nombre del producto" hint="Se deduce de la URL, pero puedes ajustarlo — mejora todo el resultado">
            <input className={inputCls} placeholder="Ej: Cortador de verduras 14 en 1" value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Precio observado (opcional)">
            <input className={inputCls} placeholder="Ej: $12.99 coste / $39.95 venta" value={price} onChange={(e) => setPrice(e.target.value)} />
          </Field>
        </div>

        <Field label="Descripción (opcional)" hint="Pega la descripción del listing: cuanto más contexto, más precisa la campaña">
          <textarea className={`${inputCls} min-h-20 resize-y`} placeholder="Qué hace, materiales, características…" value={desc} onChange={(e) => setDesc(e.target.value)} />
        </Field>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Categoría" hint={!category ? `Auto-detectada: ${detectedCat.name}` : undefined}>
            <select className={inputCls} value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">Auto-detectar</option>
              {CATEGORIES.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </Field>
          <Field label="Audiencia objetivo (opcional)">
            <input className={inputCls} placeholder="Ej: madres 28-40, España y LATAM" value={audience} onChange={(e) => setAudience(e.target.value)} />
          </Field>
        </div>

        <Field label="Imagen del producto (opcional)">
          {image ? (
            <div className="relative inline-block">
              <img src={image} alt="Producto" className="h-32 rounded-xl border border-white/10 object-cover" />
              <button onClick={() => setImage(null)} className="absolute -top-2 -right-2 bg-zinc-800 rounded-full p-1 border border-white/10 hover:bg-red-500/80 transition-colors">
                <X size={12} />
              </button>
            </div>
          ) : (
            <button
              onClick={() => fileRef.current?.click()}
              className="w-full border border-dashed border-white/15 rounded-xl py-8 text-zinc-500 hover:border-violet-500/50 hover:text-zinc-300 transition-colors flex flex-col items-center gap-2"
            >
              <ImagePlus size={22} />
              <span className="text-sm">Arrastra o haz clic para subir una imagen</span>
            </button>
          )}
          <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={(e) => onFile(e.target.files?.[0] ?? null)} />
        </Field>

        {error && <p className="text-sm text-red-400">{error}</p>}

        <div className="flex items-center justify-between pt-2">
          <div className="text-xs text-zinc-500 flex items-center gap-1.5">
            <Sparkles size={13} className={settings.useClaude && settings.apiKey ? "text-cyan-300" : "text-zinc-600"} />
            {settings.useClaude && settings.apiKey
              ? `Generación con Claude (${settings.model}) activada`
              : "Motor local activo — conecta la API de Claude en Configuración para resultados con IA real"}
          </div>
          <button onClick={generate} className="grad-btn inline-flex items-center gap-2 rounded-xl px-6 py-3 font-bold text-white">
            <Rocket size={16} /> Generar campaña
          </button>
        </div>
      </Card>
    </div>
  );
}
