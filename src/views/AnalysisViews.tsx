import React, { useState } from "react";
import { AlertTriangle, ArrowRight, CheckCircle2, Loader2, Minus, Plus, ScanSearch, ShieldQuestion, Swords, TrendingUp, Zap } from "lucide-react";
import { useApp } from "../store";
import { Bar, Card, Chip, CopyBtn, Field, inputCls, KV, ScoreRing, SectionHeader, Stars } from "../components/ui";
import { analyzeCompetitor, SOURCE_LABEL } from "../engine/generate";
import { getCategory } from "../engine/data";
import { CREDIT_COSTS } from "../plans";

// ============ Resumen de campaña ============
export function OverviewView() {
  const { active: c, setView } = useApp();
  if (!c) return null;

  const totalHooks = c.hooks.reduce((n, h) => n + h.items.length, 0);
  const shortcuts = [
    { id: "hooks", n: totalHooks, t: "Hooks" },
    { id: "scripts", n: c.scripts.length, t: "Guiones" },
    { id: "ads", n: c.ads.length, t: "Anuncios" },
    { id: "ugc", n: c.ugc.length, t: "Guiones UGC" },
    { id: "imageprompts", n: c.imagePrompts.reduce((n, g) => n + g.prompts.length, 0), t: "Prompts imagen" },
    { id: "videoprompts", n: c.videoPrompts.reduce((n, g) => n + g.prompts.length, 0), t: "Prompts video" },
    { id: "offers", n: c.offers.length, t: "Ofertas" },
    { id: "abtesting", n: c.abTests.reduce((n, t) => n + t.variants.length, 0), t: "Variantes A/B" },
  ] as const;

  return (
    <div>
      <SectionHeader
        title={c.input.name}
        subtitle={`Fuente: ${SOURCE_LABEL[c.input.sourceType]}${c.input.sourceUrl ? ` · ${c.input.sourceUrl.slice(0, 60)}` : ""} · Categoría: ${getCategory(c.input.categoryId).name}${c.generatedBy === "claude" ? " · ✨ Generado con Claude" : ""}`}
      />

      <div className="grid grid-cols-3 gap-4 mb-6">
        <Card className="flex flex-col items-center text-center gap-3">
          <ScoreRing value={c.score.total} label="Creative Score" />
          <div className="text-xs text-zinc-400 leading-relaxed">{c.score.verdict.split(".")[0]}.</div>
        </Card>
        <Card className="flex flex-col items-center text-center gap-3">
          <ScoreRing value={c.viral.probability} label="Viral" />
          <div className="text-xs text-zinc-400 leading-relaxed">{c.viral.verdict.split(".")[0]}.</div>
        </Card>
        <Card>
          <div className="text-xs font-bold uppercase tracking-wider text-zinc-500 mb-3">Plataformas</div>
          <div className="space-y-2.5">
            {c.score.platforms.slice(0, 4).map((p) => (
              <div key={p.name} className="flex items-center gap-3">
                <span className="text-xs w-20 text-zinc-400 shrink-0">{p.name}</span>
                <Bar value={p.score} />
                <span className="text-xs font-bold w-8 text-right">{p.score}/10</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card className="mb-6">
        <div className="text-xs font-bold uppercase tracking-wider text-zinc-500 mb-2">El problema que ataca</div>
        <p className="text-sm text-zinc-300 leading-relaxed">{c.intelligence.problem}</p>
        <div className="flex flex-wrap gap-1.5 mt-3">
          {c.intelligence.angles.slice(0, 6).map((a) => (
            <Chip key={a.name} tone="accent">{a.name}</Chip>
          ))}
        </div>
      </Card>

      <div className="grid grid-cols-4 gap-3">
        {shortcuts.map((s) => (
          <button
            key={s.id}
            onClick={() => setView(s.id as never)}
            className="card p-4 text-left hover:border-violet-500/40 transition-colors group"
          >
            <div className="text-2xl font-extrabold grad-text">{s.n}</div>
            <div className="text-xs text-zinc-400 mt-1 flex items-center gap-1">
              {s.t} <ArrowRight size={11} className="opacity-0 group-hover:opacity-100 transition-opacity" />
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

// ============ 1. Product Intelligence ============
export function IntelligenceView() {
  const { active: c } = useApp();
  if (!c) return null;
  const i = c.intelligence;

  return (
    <div>
      <SectionHeader title="Product Intelligence" subtitle="Análisis estratégico completo: problema, beneficios, audiencias, ángulos, objeciones y escalado." />

      <div className="space-y-5">
        <Card>
          <h3 className="font-bold mb-2 flex items-center gap-2">🎯 Problema que resuelve <CopyBtn text={i.problem} /></h3>
          <p className="text-sm text-zinc-300 leading-relaxed">{i.problem}</p>
          <div className="mt-4 grid grid-cols-2 gap-2">
            {i.secondaryProblems.map((p, idx) => (
              <div key={idx} className="text-xs text-zinc-400 bg-white/[0.03] rounded-lg px-3 py-2 border border-white/5">{p}</div>
            ))}
          </div>
        </Card>

        <Card>
          <h3 className="font-bold mb-3 flex items-center gap-2">✅ Beneficios <CopyBtn text={i.benefits.join("\n")} /></h3>
          <div className="grid grid-cols-2 gap-2">
            {i.benefits.map((b, idx) => (
              <div key={idx} className="flex items-start gap-2 text-sm text-zinc-300">
                <CheckCircle2 size={15} className="text-emerald-400 mt-0.5 shrink-0" /> {b}
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <h3 className="font-bold mb-3">👥 Público objetivo</h3>
          <div className="grid grid-cols-3 gap-3">
            {i.audiences.map((a) => (
              <div key={a.name} className="rounded-xl bg-white/[0.03] border border-white/5 p-4">
                <div className="font-bold text-sm text-violet-300">{a.name}</div>
                <p className="text-xs text-zinc-400 mt-1.5 leading-relaxed">{a.description}</p>
                <div className="mt-2.5 space-y-1">
                  {a.pains.map((p, idx) => (
                    <div key={idx} className="text-xs text-zinc-500 flex gap-1.5"><span className="text-red-400">•</span> {p}</div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <h3 className="font-bold mb-3">📐 Ángulos de venta</h3>
          <div className="space-y-3">
            {i.angles.map((a) => (
              <div key={a.name} className="flex gap-4 items-start rounded-xl bg-white/[0.03] border border-white/5 p-4">
                <Chip tone="accent">{a.emotion}</Chip>
                <div className="min-w-0">
                  <div className="font-bold text-sm">{a.name}</div>
                  <p className="text-xs text-zinc-400 mt-1 leading-relaxed">{a.description}</p>
                  <p className="text-xs text-cyan-300 mt-1.5 italic">{a.bigIdea}</p>
                </div>
                <CopyBtn text={`${a.name} (${a.emotion}): ${a.description} Big idea: ${a.bigIdea}`} />
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <h3 className="font-bold mb-3 flex items-center gap-2"><ShieldQuestion size={17} className="text-amber-400" /> Objeciones y cómo responderlas</h3>
          <div className="space-y-3">
            {i.objections.map((o, idx) => (
              <div key={idx} className="rounded-xl bg-white/[0.03] border border-white/5 p-4">
                <div className="text-sm font-semibold text-amber-300">{o.objection}</div>
                <p className="text-xs text-zinc-400 mt-1.5 leading-relaxed">→ {o.response}</p>
              </div>
            ))}
          </div>
        </Card>

        <div className="grid grid-cols-2 gap-5">
          <Card>
            <h3 className="font-bold mb-3">💎 Diferenciadores</h3>
            <div className="space-y-2">
              {i.differentiators.map((d, idx) => (
                <div key={idx} className="text-xs text-zinc-300 flex gap-2 leading-relaxed">
                  <span className="text-violet-400 font-bold shrink-0">{idx + 1}.</span> {d}
                </div>
              ))}
            </div>
          </Card>
          <div className="space-y-5">
            <Card>
              <h3 className="font-bold mb-2">💰 Precio recomendado</h3>
              <div className="text-2xl font-extrabold grad-text">{i.pricing.recommended}</div>
              <div className="text-xs text-zinc-500 mt-0.5">{i.pricing.range}</div>
              <p className="text-xs text-zinc-400 mt-3 leading-relaxed">{i.pricing.strategy}</p>
              <p className="text-xs text-zinc-500 mt-2 leading-relaxed">{i.pricing.marginNote}</p>
            </Card>
            <Card>
              <h3 className="font-bold mb-2 flex items-center gap-2"><TrendingUp size={16} className="text-emerald-400" /> Potencial de escalado: <span className="text-emerald-400">{i.scaling.level}</span></h3>
              <p className="text-xs text-zinc-400 leading-relaxed">{i.scaling.reasoning}</p>
              <div className="flex flex-wrap gap-1.5 mt-3">
                {i.scaling.channels.map((ch) => <Chip key={ch}>{ch}</Chip>)}
              </div>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}

// ============ 2. Creative Score ============
export function ScoreView() {
  const { active: c } = useApp();
  if (!c) return null;

  return (
    <div>
      <SectionHeader title="Creative Opportunity Score" subtitle="¿Cuánto potencial creativo tiene este producto antes de gastar un euro en ads?" />

      <Card className="flex items-center gap-8 mb-5">
        <ScoreRing value={c.score.total} size={150} label="de 100" />
        <div>
          <h3 className="font-bold text-lg mb-1">Veredicto</h3>
          <p className="text-sm text-zinc-400 leading-relaxed max-w-xl">{c.score.verdict}</p>
        </div>
      </Card>

      <div className="grid grid-cols-2 gap-5">
        <Card>
          <h3 className="font-bold mb-4">Métricas creativas</h3>
          <div className="space-y-4">
            {c.score.metrics.map((m) => (
              <div key={m.label}>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">{m.label}</span>
                  <Stars n={m.stars} />
                </div>
                <p className="text-xs text-zinc-500 mt-1">{m.note}</p>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <h3 className="font-bold mb-4">Puntuación por plataforma</h3>
          <div className="space-y-5">
            {c.score.platforms.map((p) => (
              <div key={p.name}>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-sm font-medium">{p.name}</span>
                  <span className="text-sm font-extrabold">{p.score}/10</span>
                </div>
                <Bar value={p.score} />
                <p className="text-xs text-zinc-500 mt-1.5">{p.note}</p>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

// ============ 16. Viral Predictor ============
export function ViralView() {
  const { active: c } = useApp();
  if (!c) return null;
  const v = c.viral;
  const impactIcon = (i: string) =>
    i === "Positivo" ? <Plus size={13} className="text-emerald-400" /> : i === "Negativo" ? <Minus size={13} className="text-red-400" /> : <Minus size={13} className="text-zinc-500" />;

  return (
    <div>
      <SectionHeader title="Viral Predictor" subtitle="Predicción del potencial viral del producto antes de invertir en anuncios." />

      <Card className="flex items-center gap-8 mb-5">
        <ScoreRing value={v.probability} size={150} label="probabilidad" />
        <div>
          <h3 className="font-bold text-lg mb-1">Predicción</h3>
          <p className="text-sm text-zinc-400 leading-relaxed max-w-xl">{v.verdict}</p>
        </div>
      </Card>

      <div className="grid grid-cols-2 gap-5">
        <Card>
          <h3 className="font-bold mb-4">Factores analizados</h3>
          <div className="space-y-3">
            {v.factors.map((f) => (
              <div key={f.factor} className="rounded-xl bg-white/[0.03] border border-white/5 p-3.5">
                <div className="flex items-center gap-2">
                  {impactIcon(f.impact)}
                  <span className="text-sm font-semibold">{f.factor}</span>
                  <Chip tone={f.impact === "Positivo" ? "ok" : f.impact === "Negativo" ? "bad" : "default"}>{f.impact}</Chip>
                </div>
                <p className="text-xs text-zinc-500 mt-1.5 leading-relaxed">{f.note}</p>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <h3 className="font-bold mb-4">Plan para maximizar viralidad</h3>
          <div className="space-y-3">
            {v.recommendations.map((r, idx) => (
              <div key={idx} className="flex gap-3 text-sm text-zinc-300 leading-relaxed">
                <span className="w-6 h-6 rounded-full bg-violet-500/15 text-violet-300 text-xs font-bold flex items-center justify-center shrink-0">{idx + 1}</span>
                {r}
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

// ============ 10. Competitor Analyzer ============
export function CompetitorView() {
  const { active: c, updateCampaign, spend, setView, account } = useApp();
  const [url, setUrl] = useState(c?.competitor?.url ?? "");
  const [copyText, setCopyText] = useState("");
  const [loading, setLoading] = useState(false);
  const [creditError, setCreditError] = useState(false);
  if (!c) return null;

  const analyze = () => {
    if (!url.trim()) return;
    if (!spend("competitor")) {
      setCreditError(true);
      return;
    }
    setCreditError(false);
    setLoading(true);
    setTimeout(() => {
      const result = analyzeCompetitor(url.trim(), copyText, getCategory(c.input.categoryId), c.input.name);
      updateCampaign({ ...c, competitor: result });
      setLoading(false);
    }, 900);
  };

  const comp = c.competitor;

  return (
    <div>
      <SectionHeader title="Competitor Analyzer" subtitle="Pega la URL de un competidor (y opcionalmente el texto de su landing o ads) para extraer su framework y encontrar cómo superarlo." />

      <Card className="space-y-4 mb-6">
        <Field label="URL del competidor">
          <input className={inputCls} placeholder="https://tienda-competidora.com/producto" value={url} onChange={(e) => setUrl(e.target.value)} />
        </Field>
        <Field label="Copy del competidor (opcional pero recomendado)" hint="Entra a su web, selecciona todo el texto visible (Ctrl+A, Ctrl+C) y pégalo aquí. El análisis detecta hooks, CTAs, ofertas y garantías reales.">
          <textarea className={`${inputCls} min-h-28 resize-y`} placeholder="Pega aquí el texto de su landing, sus anuncios o su página de producto…" value={copyText} onChange={(e) => setCopyText(e.target.value)} />
        </Field>
        <div className="flex items-center gap-3">
          <button onClick={analyze} disabled={!url.trim() || loading} className="grad-btn rounded-xl px-5 py-2.5 text-sm font-bold text-white disabled:opacity-40 inline-flex items-center gap-2">
            {loading ? <Loader2 size={14} className="spinner" /> : <ScanSearch size={15} />} Analizar competidor
            <span className="text-[11px] font-semibold bg-white/20 rounded-full px-2 py-0.5 inline-flex items-center gap-1">
              <Zap size={10} /> {CREDIT_COSTS.competitor}
            </span>
          </button>
          {creditError && (
            <span className="text-xs text-amber-300">
              Sin créditos suficientes ({account.credits} disponibles) ·{" "}
              <button onClick={() => setView("plans")} className="underline font-semibold">Ver planes</button>
            </span>
          )}
        </div>
      </Card>

      {comp && (
        <div className="space-y-5 fade-up">
          <div className="grid grid-cols-2 gap-5">
            <Card>
              <h3 className="font-bold mb-3">🪝 Hooks detectados</h3>
              <div className="space-y-2">
                {comp.hooks.map((h, i) => <div key={i} className="text-sm text-zinc-300 bg-white/[0.03] rounded-lg px-3 py-2">{h}</div>)}
              </div>
            </Card>
            <Card>
              <h3 className="font-bold mb-3">👆 CTAs detectados</h3>
              <div className="space-y-2">
                {comp.ctas.map((h, i) => <div key={i} className="text-sm text-zinc-300 bg-white/[0.03] rounded-lg px-3 py-2">{h}</div>)}
              </div>
              <h3 className="font-bold mb-2 mt-5">🛡️ Garantías</h3>
              {comp.guarantees.map((g, i) => <p key={i} className="text-xs text-zinc-400 leading-relaxed mb-1.5">{g}</p>)}
            </Card>
          </div>

          <Card>
            <h3 className="font-bold mb-2">📖 Storytelling y oferta</h3>
            <p className="text-sm text-zinc-300 leading-relaxed">{comp.storytelling}</p>
            <p className="text-sm text-zinc-400 leading-relaxed mt-3"><strong className="text-zinc-200">Oferta:</strong> {comp.offer}</p>
          </Card>

          <Card>
            <h3 className="font-bold mb-2">🧩 Framework del anuncio</h3>
            <p className="text-sm text-zinc-300 leading-relaxed">{comp.framework}</p>
          </Card>

          <div className="grid grid-cols-2 gap-5">
            <Card>
              <h3 className="font-bold mb-3 flex items-center gap-2"><AlertTriangle size={16} className="text-amber-400" /> Debilidades a explotar</h3>
              <div className="space-y-2.5">
                {comp.weaknesses.map((w, i) => <div key={i} className="text-xs text-zinc-400 leading-relaxed flex gap-2"><span className="text-amber-400">▸</span> {w}</div>)}
              </div>
            </Card>
            <Card>
              <h3 className="font-bold mb-3 flex items-center gap-2"><Swords size={16} className="text-emerald-400" /> Cómo ganarle</h3>
              <div className="space-y-2.5">
                {comp.howToBeat.map((w, i) => <div key={i} className="text-xs text-zinc-300 leading-relaxed flex gap-2"><span className="text-emerald-400">▸</span> {w}</div>)}
              </div>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
