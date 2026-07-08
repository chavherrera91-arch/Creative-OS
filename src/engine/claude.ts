import Anthropic from "@anthropic-ai/sdk";
import type { Campaign, ProductInput, Settings } from "../types";

// Integración opcional con la API de Claude.
// El motor local genera la campaña completa; si el usuario configura su API key,
// Claude re-genera las partes de mayor valor estratégico (inteligencia de producto,
// hooks, ángulos, objeciones, landing y guiones UGC) con conocimiento real del producto,
// y se fusionan sobre la campaña local.

const ENHANCE_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: [
    "problem", "secondaryProblems", "benefits", "audiences", "angles", "objections",
    "differentiators", "pricing", "scoreVerdict", "scoreTotal", "hooks", "landing", "ugcScripts",
  ],
  properties: {
    problem: { type: "string", description: "El problema principal que resuelve el producto, en 2-3 frases con gancho de marketing" },
    secondaryProblems: { type: "array", items: { type: "string" } },
    benefits: { type: "array", items: { type: "string" }, description: "7 beneficios concretos y vendedores" },
    audiences: {
      type: "array",
      items: {
        type: "object", additionalProperties: false, required: ["name", "description", "pains"],
        properties: { name: { type: "string" }, description: { type: "string" }, pains: { type: "array", items: { type: "string" } } },
      },
    },
    angles: {
      type: "array",
      items: {
        type: "object", additionalProperties: false, required: ["name", "emotion", "description", "bigIdea"],
        properties: { name: { type: "string" }, emotion: { type: "string" }, description: { type: "string" }, bigIdea: { type: "string" } },
      },
    },
    objections: {
      type: "array",
      items: {
        type: "object", additionalProperties: false, required: ["objection", "response"],
        properties: { objection: { type: "string" }, response: { type: "string" } },
      },
    },
    differentiators: { type: "array", items: { type: "string" } },
    pricing: {
      type: "object", additionalProperties: false, required: ["recommended", "range", "strategy", "marginNote"],
      properties: { recommended: { type: "string" }, range: { type: "string" }, strategy: { type: "string" }, marginNote: { type: "string" } },
    },
    scoreVerdict: { type: "string" },
    scoreTotal: { type: "integer", description: "Creative Score de 0 a 100" },
    hooks: {
      type: "array",
      description: "14 categorías: Curiosidad, Miedo, Dolor, Humor, Storytelling, ASMR, Comparación, Error común, Antes vs Después, POV, Shock, Datos, Estadísticas, Testimonio. 8 hooks por categoría.",
      items: {
        type: "object", additionalProperties: false, required: ["category", "items"],
        properties: { category: { type: "string" }, items: { type: "array", items: { type: "string" } } },
      },
    },
    landing: {
      type: "object", additionalProperties: false, required: ["headline", "subheadline", "guarantee"],
      properties: { headline: { type: "string" }, subheadline: { type: "string" }, guarantee: { type: "string" } },
    },
    ugcScripts: {
      type: "array",
      description: "7 guiones UGC: Mamá, Doctor/especialista, Deportista, Estudiante, CEO/emprendedor, Pareja, Abuelo/a",
      items: {
        type: "object", additionalProperties: false, required: ["persona", "hook", "script"],
        properties: { persona: { type: "string" }, hook: { type: "string" }, script: { type: "string" } },
      },
    },
  },
} as const;

export async function enhanceWithClaude(
  input: ProductInput,
  base: Campaign,
  settings: Settings,
  onStatus: (msg: string) => void
): Promise<Campaign> {
  const client = new Anthropic({
    apiKey: settings.apiKey,
    dangerouslyAllowBrowser: true,
  });

  onStatus("Analizando el producto con Claude…");

  const productContext = [
    `Producto: ${input.name}`,
    input.description ? `Descripción: ${input.description}` : "",
    input.sourceUrl ? `URL de origen: ${input.sourceUrl}` : "",
    input.price ? `Precio observado/coste: ${input.price}` : "",
    input.audienceHint ? `Pista de audiencia del usuario: ${input.audienceHint}` : "",
  ].filter(Boolean).join("\n");

  const stream = client.messages.stream({
    model: settings.model || "claude-opus-4-8",
    max_tokens: 32000,
    system: `Eres el mejor estratega de marketing de respuesta directa y creativos virales del mundo (nivel: los mejores media buyers de TikTok/Meta). Generas material de campaña listo para producir, en español neutro, específico para el producto dado — nunca genérico. Cada hook debe poder usarse tal cual en un video. Usa números concretos, tiempos y situaciones reales. Devuelve exactamente el JSON pedido.`,
    messages: [
      {
        role: "user",
        content: `Genera la estrategia creativa completa para este producto de e-commerce:\n\n${productContext}\n\nRequisitos:\n- 4 problemas secundarios\n- 7 beneficios\n- 3 audiencias con 3 dolores cada una\n- 6 ángulos de venta (emociones variadas)\n- 6 objeciones con respuesta accionable\n- 5 diferenciadores\n- Estrategia de precio con anclas y bundles\n- 14 categorías de hooks (Curiosidad, Miedo, Dolor, Humor, Storytelling, ASMR, Comparación, Error común, Antes vs Después, POV, Shock, Datos, Estadísticas, Testimonio) con 8 hooks cada una\n- Headline, subheadline y garantía de landing\n- 7 guiones UGC completos (Mamá, Doctor, Deportista, Estudiante, CEO, Pareja, Abuelo/a) de 30-45 segundos hablados en primera persona`,
      },
    ],
    output_config: {
      format: {
        type: "json_schema",
        schema: ENHANCE_SCHEMA as unknown as Record<string, unknown>,
      },
    },
  });

  const message = await stream.finalMessage();

  if (message.stop_reason === "refusal") {
    throw new Error("Claude rechazó la solicitud. Se usará el motor local.");
  }

  const textBlock = message.content.find((b) => b.type === "text");
  if (!textBlock || textBlock.type !== "text") {
    throw new Error("Respuesta vacía de Claude.");
  }

  onStatus("Fusionando la estrategia de Claude con la campaña…");
  const data = JSON.parse(textBlock.text);

  // Fusionar sobre la campaña local (la campaña local ya tiene todo lo demás)
  const merged: Campaign = {
    ...base,
    generatedBy: "claude",
    intelligence: {
      ...base.intelligence,
      problem: data.problem ?? base.intelligence.problem,
      secondaryProblems: arr(data.secondaryProblems) ?? base.intelligence.secondaryProblems,
      benefits: arr(data.benefits) ?? base.intelligence.benefits,
      audiences: arr(data.audiences) ?? base.intelligence.audiences,
      angles: arr(data.angles) ?? base.intelligence.angles,
      objections: arr(data.objections) ?? base.intelligence.objections,
      differentiators: arr(data.differentiators) ?? base.intelligence.differentiators,
      pricing: data.pricing ?? base.intelligence.pricing,
    },
    score: {
      ...base.score,
      total: typeof data.scoreTotal === "number" ? Math.max(0, Math.min(100, data.scoreTotal)) : base.score.total,
      verdict: data.scoreVerdict ?? base.score.verdict,
    },
    hooks: arr(data.hooks)
      ? data.hooks.map((h: { category: string; items: string[] }) => ({
          category: h.category,
          emoji: base.hooks.find((bh) => bh.category.toLowerCase() === h.category.toLowerCase())?.emoji ?? "✨",
          items: h.items,
        }))
      : base.hooks,
    landing: {
      ...base.landing,
      headline: data.landing?.headline ?? base.landing.headline,
      subheadline: data.landing?.subheadline ?? base.landing.subheadline,
      guarantee: data.landing?.guarantee ?? base.landing.guarantee,
    },
    ugc: arr(data.ugcScripts)
      ? base.ugc.map((u, i) => {
          const match =
            data.ugcScripts.find((s: { persona: string }) => s.persona.toLowerCase().includes(u.persona.toLowerCase().slice(0, 4))) ??
            data.ugcScripts[i];
          return match ? { ...u, hook: match.hook, script: match.script } : u;
        })
      : base.ugc,
  };
  return merged;
}

function arr(v: unknown): any | null {
  return Array.isArray(v) && v.length > 0 ? (v as any) : null;
}

export async function testApiKey(settings: Settings): Promise<string> {
  const client = new Anthropic({ apiKey: settings.apiKey, dangerouslyAllowBrowser: true });
  const res = await client.messages.create({
    model: settings.model || "claude-opus-4-8",
    max_tokens: 32,
    messages: [{ role: "user", content: "Responde solo: OK" }],
  });
  const t = res.content.find((b) => b.type === "text");
  return t && t.type === "text" ? t.text : "OK";
}
