// ============ Modelo de datos de Creative OS ============

export type SourceType =
  | "aliexpress"
  | "amazon"
  | "shopify"
  | "tiktok"
  | "tienda"
  | "imagen"
  | "manual";

export interface ProductInput {
  name: string;
  description: string;
  sourceUrl: string;
  sourceType: SourceType;
  price: string; // precio de coste u observado (texto libre)
  imageDataUrl: string | null;
  audienceHint: string;
  categoryId: string; // detectada o elegida
}

export interface Audience {
  name: string;
  description: string;
  pains: string[];
}

export interface Angle {
  name: string;
  emotion: string;
  description: string;
  bigIdea: string;
}

export interface Objection {
  objection: string;
  response: string;
}

export interface Intelligence {
  problem: string;
  secondaryProblems: string[];
  benefits: string[];
  audiences: Audience[];
  angles: Angle[];
  objections: Objection[];
  differentiators: string[];
  pricing: {
    recommended: string;
    range: string;
    strategy: string;
    marginNote: string;
  };
  scaling: {
    level: "Bajo" | "Medio" | "Alto" | "Muy alto";
    reasoning: string;
    channels: string[];
  };
}

export interface ScoreMetric {
  label: string;
  stars: number; // 0-5
  note: string;
}

export interface PlatformScore {
  name: string;
  score: number; // 0-10
  note: string;
}

export interface CreativeScore {
  total: number; // 0-100
  verdict: string;
  metrics: ScoreMetric[];
  platforms: PlatformScore[];
}

export interface HookGroup {
  category: string;
  emoji: string;
  items: string[];
}

export interface AdCreative {
  format: string;
  platform: string;
  title: string;
  primaryText: string;
  headline: string;
  description: string;
  cta: string;
  specs: string;
  notes: string;
}

export interface ScriptBeat {
  time: string;
  label: string;
  voiceover: string;
  visual: string;
}

export interface Script {
  duration: string;
  angle: string;
  title: string;
  hook: string;
  beats: ScriptBeat[];
  cta: string;
}

export interface Scene {
  n: number;
  shot: string;
  subject: string;
  expression: string;
  light: string;
  text: string;
  movement: string;
  duration: string;
  audio: string;
}

export interface VisualSet {
  title: string;
  concept: string;
  scenes: Scene[];
}

export interface PromptGroup {
  tool: string;
  prompts: { title: string; prompt: string; meta: string }[];
}

export interface UgcCreator {
  persona: string;
  emoji: string;
  profile: string;
  tone: string;
  setting: string;
  hook: string;
  script: string;
  wardrobe: string;
}

export interface CompetitorAnalysis {
  url: string;
  hooks: string[];
  ctas: string[];
  storytelling: string;
  colors: string[];
  offer: string;
  guarantees: string[];
  framework: string;
  weaknesses: string[];
  howToBeat: string[];
}

export interface LibraryLink {
  platform: string;
  name: string;
  url: string;
  note: string;
}

export interface ThumbnailConcept {
  concept: string;
  headline: string;
  style: string;
  colors: string[];
  layout: string;
  prompt: string;
}

export interface LandingCopy {
  headline: string;
  subheadline: string;
  benefits: { title: string; text: string }[];
  faq: { q: string; a: string }[];
  guarantee: string;
  ctas: string[];
  comparison: { feature: string; us: string; them: string }[];
  reviews: { name: string; stars: number; text: string; detail: string }[];
}

export interface Offer {
  type: string;
  name: string;
  description: string;
  structure: string;
  example: string;
  bestFor: string;
}

export interface PlannerItem {
  count: number;
  type: string;
  priority: "Alta" | "Media" | "Baja";
  notes: string;
  platform: string;
}

export interface PlannerWeek {
  week: string;
  goal: string;
  items: PlannerItem[];
}

export interface ViralFactor {
  factor: string;
  impact: "Positivo" | "Neutro" | "Negativo";
  note: string;
}

export interface ViralPrediction {
  probability: number; // 0-100
  verdict: string;
  factors: ViralFactor[];
  recommendations: string[];
}

export interface IterationAdvice {
  input: string;
  wrong: string[];
  remove: string[];
  add: string[];
  test: string[];
  hookChanges: string[];
  ctaChanges: string[];
  pacingChanges: string[];
}

export interface AbTestPlan {
  element: string;
  emoji: string;
  variants: string[];
  metric: string;
}

export interface Campaign {
  id: string;
  createdAt: number;
  generatedBy: "local" | "claude";
  input: ProductInput;
  intelligence: Intelligence;
  score: CreativeScore;
  hooks: HookGroup[];
  ads: AdCreative[];
  scripts: Script[];
  visualSets: VisualSet[];
  imagePrompts: PromptGroup[];
  videoPrompts: PromptGroup[];
  ugc: UgcCreator[];
  library: LibraryLink[];
  thumbnails: ThumbnailConcept[];
  landing: LandingCopy;
  offers: Offer[];
  planner: PlannerWeek[];
  viral: ViralPrediction;
  abTests: AbTestPlan[];
  // Herramientas bajo demanda (se rellenan al usarlas)
  competitor: CompetitorAnalysis | null;
  iteration: IterationAdvice | null;
}

export interface Settings {
  apiKey: string;
  model: string;
  useClaude: boolean;
}

export const MODULES = [
  { id: "overview", name: "Resumen de campaña", group: "Campaña" },
  { id: "intelligence", name: "Product Intelligence", group: "Análisis" },
  { id: "score", name: "Creative Score", group: "Análisis" },
  { id: "viral", name: "Viral Predictor", group: "Análisis" },
  { id: "competitor", name: "Competitor Analyzer", group: "Análisis" },
  { id: "hooks", name: "Hook Generator", group: "Generación" },
  { id: "ads", name: "Ad Generator", group: "Generación" },
  { id: "scripts", name: "Script Generator", group: "Generación" },
  { id: "visual", name: "Visual Generator", group: "Generación" },
  { id: "imageprompts", name: "AI Image Prompts", group: "Generación" },
  { id: "videoprompts", name: "AI Video Prompts", group: "Generación" },
  { id: "ugc", name: "UGC Generator", group: "Generación" },
  { id: "thumbnails", name: "Thumbnail Generator", group: "Generación" },
  { id: "landing", name: "Landing Copy", group: "Conversión" },
  { id: "offers", name: "Offer Builder", group: "Conversión" },
  { id: "planner", name: "Creative Planner", group: "Estrategia" },
  { id: "abtesting", name: "A/B Testing", group: "Estrategia" },
  { id: "iteration", name: "Creative Iteration", group: "Estrategia" },
  { id: "library", name: "Creative Library", group: "Estrategia" },
  { id: "export", name: "Exportar campaña", group: "Campaña" },
] as const;

export type ModuleId = (typeof MODULES)[number]["id"];
