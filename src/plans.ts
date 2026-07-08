import type { ModuleId } from "./types";

// ============ Sistema de suscripciones y créditos ============

export type PlanId = "free" | "premium" | "max";

export interface Plan {
  id: PlanId;
  name: string;
  price: number; // USD / mes
  tagline: string;
  credits: number; // créditos mensuales
  campaignLimit: number; // campañas nuevas por mes
  highlight?: boolean;
  cta: string;
  features: { text: string; included: boolean }[];
}

// Coste en créditos de cada acción generativa (estilo IA de imágenes)
export const CREDIT_COSTS = {
  campaign: 10, // generar una campaña completa
  competitor: 5, // análisis de competidor
  iteration: 5, // diagnóstico de creativo
} as const;

export type CreditAction = keyof typeof CREDIT_COSTS;

export const ACTION_LABEL: Record<CreditAction, string> = {
  campaign: "Generar campaña",
  competitor: "Análisis de competidor",
  iteration: "Diagnóstico de creativo",
};

// Plan mínimo necesario para cada módulo.
// Estrategia: Gratis = probar el valor (análisis). Premium = producir contenido.
// Max = escalar y optimizar (herramientas de agencia/media buyer).
export const MODULE_MIN_PLAN: Record<ModuleId, PlanId> = {
  overview: "free",
  intelligence: "free",
  score: "free",
  hooks: "free",
  library: "free",
  // Producción de contenido → Premium
  viral: "premium",
  scripts: "premium",
  ads: "premium",
  ugc: "premium",
  landing: "premium",
  offers: "premium",
  thumbnails: "premium",
  export: "premium",
  // Escala y optimización → Max
  visual: "max",
  imageprompts: "max",
  videoprompts: "max",
  competitor: "max",
  planner: "max",
  abtesting: "max",
  iteration: "max",
};

const PLAN_RANK: Record<PlanId, number> = { free: 0, premium: 1, max: 2 };

export function planIncludes(plan: PlanId, moduleId: ModuleId): boolean {
  return PLAN_RANK[plan] >= PLAN_RANK[MODULE_MIN_PLAN[moduleId]];
}

export function isUpgrade(from: PlanId, to: PlanId): boolean {
  return PLAN_RANK[to] > PLAN_RANK[from];
}

export const PLANS: Plan[] = [
  {
    id: "free",
    name: "Gratis",
    price: 0,
    tagline: "Prueba el poder del análisis con tu primer producto.",
    credits: 10,
    campaignLimit: 1,
    cta: "Empezar gratis",
    features: [
      { text: "1 campaña al mes (10 créditos)", included: true },
      { text: "Product Intelligence completo", included: true },
      { text: "Creative Score 0-100", included: true },
      { text: "Hook Generator — 140+ hooks", included: true },
      { text: "Creative Library (búsquedas pre-armadas)", included: true },
      { text: "Guiones, anuncios y UGC", included: false },
      { text: "Landing Copy y Offer Builder", included: false },
      { text: "Exportar campaña (Markdown/JSON)", included: false },
      { text: "Prompts de IA, A/B Testing y Planner", included: false },
    ],
  },
  {
    id: "premium",
    name: "Premium",
    price: 10,
    tagline: "Todo lo necesario para producir contenido que vende.",
    credits: 100,
    campaignLimit: 10,
    highlight: true,
    cta: "Pasar a Premium",
    features: [
      { text: "10 campañas al mes (100 créditos)", included: true },
      { text: "Todo lo del plan Gratis", included: true },
      { text: "Script Generator — 36 guiones (15s a 3 min)", included: true },
      { text: "Ad Generator — 10 formatos y plataformas", included: true },
      { text: "UGC Generator — 7 personalidades", included: true },
      { text: "Landing Copy + Offer Builder", included: true },
      { text: "Thumbnail Generator + Viral Predictor", included: true },
      { text: "Exportar campaña (Markdown/JSON)", included: true },
      { text: "Prompts de IA, Competitor y A/B Testing", included: false },
    ],
  },
  {
    id: "max",
    name: "Max",
    price: 20,
    tagline: "El arsenal completo para escalar como una agencia.",
    credits: 500,
    campaignLimit: 50,
    cta: "Pasar a Max",
    features: [
      { text: "50 campañas al mes (500 créditos)", included: true },
      { text: "Todo lo de Premium", included: true },
      { text: "Visual Generator — storyboards escena a escena", included: true },
      { text: "AI Image Prompts (Midjourney, Flux, GPT Image…)", included: true },
      { text: "AI Video Prompts (Veo, Kling, Runway…)", included: true },
      { text: "Competitor Analyzer ilimitado*", included: true },
      { text: "Creative Planner — plan de producción 4 semanas", included: true },
      { text: "A/B Testing — 115+ variantes", included: true },
      { text: "Creative Iteration — diagnóstico de tus anuncios", included: true },
    ],
  },
];

export function getPlan(id: PlanId): Plan {
  return PLANS.find((p) => p.id === id) ?? PLANS[0];
}

// ============ Cuenta del usuario ============

export interface Account {
  planId: PlanId;
  credits: number;
  period: string; // "YYYY-MM" — mes de facturación actual
  campaignsThisMonth: number;
}

export function currentPeriod(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function freshAccount(planId: PlanId = "free"): Account {
  return {
    planId,
    credits: getPlan(planId).credits,
    period: currentPeriod(),
    campaignsThisMonth: 0,
  };
}

// Renueva créditos si empezó un nuevo mes
export function rolloverIfNeeded(acc: Account): Account {
  if (acc.period === currentPeriod()) return acc;
  return { ...acc, period: currentPeriod(), credits: getPlan(acc.planId).credits, campaignsThisMonth: 0 };
}

export interface SpendCheck {
  ok: boolean;
  reason: "" | "credits" | "limit";
}

export function canSpend(acc: Account, action: CreditAction): SpendCheck {
  if (action === "campaign" && acc.campaignsThisMonth >= getPlan(acc.planId).campaignLimit) {
    return { ok: false, reason: "limit" };
  }
  if (acc.credits < CREDIT_COSTS[action]) {
    return { ok: false, reason: "credits" };
  }
  return { ok: true, reason: "" };
}
