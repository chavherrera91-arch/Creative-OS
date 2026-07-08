import React, { useState } from "react";
import { Check, Download, ExternalLink, FileJson, FileText, Loader2, Star, Wand2, X, Zap } from "lucide-react";
import { useApp } from "../store";
import { Card, Chip, CopyBtn, Field, inputCls, SectionHeader, Stars } from "../components/ui";
import { analyzeIteration } from "../engine/generate";
import { getCategory } from "../engine/data";
import { campaignToMarkdown, download } from "../engine/exporter";
import { CREDIT_COSTS } from "../plans";

// ============ 13. Landing Copy ============
export function LandingView() {
  const { active: c } = useApp();
  if (!c) return null;
  const l = c.landing;

  return (
    <div>
      <SectionHeader
        title="Landing Copy Generator"
        subtitle="Copy completo de landing: headline, beneficios, FAQ, garantía, CTAs, comparativa y reviews — listo para pegar en Shopify o tu page builder."
        right={<CopyBtn label="Copiar todo" text={`${l.headline}\n${l.subheadline}\n\nBENEFICIOS:\n${l.benefits.map((b) => `- ${b.title}: ${b.text}`).join("\n")}\n\nFAQ:\n${l.faq.map((f) => `P: ${f.q}\nR: ${f.a}`).join("\n\n")}\n\nGARANTÍA: ${l.guarantee}\n\nCTAs: ${l.ctas.join(" | ")}`} />}
      />

      {/* Vista previa tipo landing */}
      <Card className="mb-5 text-center py-10 relative overflow-hidden"
      >
        <div className="absolute inset-0 pointer-events-none" style={{ background: "radial-gradient(600px 200px at 50% 0%, rgba(124,58,237,0.15), transparent)" }} />
        <h2 className="text-3xl font-extrabold tracking-tight max-w-2xl mx-auto leading-tight">{l.headline}</h2>
        <p className="text-zinc-400 mt-3 max-w-xl mx-auto text-sm leading-relaxed">{l.subheadline}</p>
        <div className="mt-6 flex justify-center gap-3 flex-wrap">
          {l.ctas.slice(0, 2).map((cta) => (
            <span key={cta} className="grad-btn rounded-xl px-6 py-3 text-sm font-bold text-white cursor-default">{cta}</span>
          ))}
        </div>
        <div className="mt-4 text-xs text-zinc-500">✓ Garantía 30 días · ✓ Envío con seguimiento · ✓ Pago seguro</div>
      </Card>

      <div className="grid grid-cols-2 gap-5">
        <Card>
          <h3 className="font-bold mb-3">💡 Bloques de beneficios</h3>
          <div className="space-y-3">
            {l.benefits.map((b, i) => (
              <div key={i} className="rounded-xl bg-white/[0.03] border border-white/5 p-3.5">
                <div className="text-sm font-semibold text-violet-300">{b.title}</div>
                <p className="text-xs text-zinc-400 mt-1 leading-relaxed">{b.text}</p>
              </div>
            ))}
          </div>
        </Card>

        <div className="space-y-5">
          <Card>
            <h3 className="font-bold mb-3">🛡️ Garantía</h3>
            <p className="text-sm text-zinc-300 leading-relaxed bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-4">{l.guarantee}</p>
          </Card>
          <Card>
            <h3 className="font-bold mb-3">👆 Variantes de CTA</h3>
            <div className="flex flex-wrap gap-2">
              {l.ctas.map((cta) => (
                <span key={cta} className="text-xs bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-zinc-300 flex items-center gap-2">
                  {cta} <CopyBtn text={cta} />
                </span>
              ))}
            </div>
          </Card>
        </div>
      </div>

      <Card className="mt-5">
        <h3 className="font-bold mb-3">⚖️ Comparativa "Nosotros vs. Ellos"</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wider text-zinc-600">
                <th className="pb-2 pr-4 font-bold">Característica</th>
                <th className="pb-2 pr-4 font-bold text-violet-300">Nuestro producto</th>
                <th className="pb-2 font-bold">La alternativa</th>
              </tr>
            </thead>
            <tbody>
              {l.comparison.map((row, i) => (
                <tr key={i} className="border-t border-white/5">
                  <td className="py-2.5 pr-4 text-zinc-300">{row.feature}</td>
                  <td className="py-2.5 pr-4 text-emerald-300">{row.us}</td>
                  <td className="py-2.5 text-zinc-500">{row.them}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid grid-cols-2 gap-5 mt-5">
        <Card>
          <h3 className="font-bold mb-3">❓ FAQ</h3>
          <div className="space-y-3">
            {l.faq.map((f, i) => (
              <div key={i}>
                <div className="text-sm font-semibold text-zinc-200">{f.q}</div>
                <p className="text-xs text-zinc-400 mt-1 leading-relaxed">{f.a}</p>
              </div>
            ))}
          </div>
        </Card>
        <Card>
          <h3 className="font-bold mb-3">⭐ Reviews de ejemplo</h3>
          <p className="text-[11px] text-zinc-600 mb-3">Plantillas del tono ideal — sustitúyelas por reseñas reales de tus clientes en cuanto las tengas.</p>
          <div className="space-y-3">
            {l.reviews.map((r, i) => (
              <div key={i} className="rounded-xl bg-white/[0.03] border border-white/5 p-3.5">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold">{r.name}</span>
                  <Stars n={r.stars} />
                </div>
                <p className="text-xs text-zinc-400 mt-1.5 leading-relaxed">{r.text}</p>
                <p className="text-[10px] text-zinc-600 mt-1.5">{r.detail}</p>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

// ============ 14. Offer Builder ============
export function OffersView() {
  const { active: c } = useApp();
  if (!c) return null;

  return (
    <div>
      <SectionHeader title="Offer Builder" subtitle="7 estructuras de oferta con matemática de margen, ejemplo de copy y cuándo usar cada una." />
      <div className="grid grid-cols-2 gap-5">
        {c.offers.map((o, i) => (
          <Card key={i}>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Chip tone="accent">{o.type}</Chip>
                <h3 className="font-bold text-sm">{o.name}</h3>
              </div>
              <CopyBtn text={`${o.type} — ${o.name}\n${o.description}\nEstructura: ${o.structure}\nEjemplo: ${o.example}`} />
            </div>
            <p className="text-xs text-zinc-400 leading-relaxed">{o.description}</p>
            <div className="mt-3 rounded-xl bg-white/[0.03] border border-white/5 p-3.5 text-xs text-zinc-300 leading-relaxed">
              <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-600 block mb-1">Estructura</span>
              {o.structure}
            </div>
            <div className="mt-2 rounded-xl bg-cyan-500/10 border border-cyan-500/20 p-3.5 text-xs text-cyan-100 leading-relaxed italic">
              {o.example}
            </div>
            <p className="text-[11px] text-zinc-500 mt-2.5"><strong className="text-zinc-400">Ideal para:</strong> {o.bestFor}</p>
          </Card>
        ))}
      </div>
    </div>
  );
}

// ============ 15. Creative Planner ============
export function PlannerView() {
  const { active: c } = useApp();
  if (!c) return null;
  const tone = (p: string): "bad" | "warn" | "default" => (p === "Alta" ? "bad" : p === "Media" ? "warn" : "default");

  return (
    <div>
      <SectionHeader title="Creative Planner" subtitle="Tu plan de producción exacto: qué crear, cuánto, en qué orden y para qué canal — semana a semana." />
      <div className="space-y-6">
        {c.planner.map((w, wi) => (
          <Card key={wi}>
            <h3 className="font-bold text-lg">{w.week}</h3>
            <p className="text-xs text-zinc-500 mt-1 mb-4 leading-relaxed">{w.goal}</p>
            <div className="space-y-2">
              {w.items.map((item, i) => (
                <div key={i} className="flex items-center gap-4 rounded-xl bg-white/[0.03] border border-white/5 p-3.5">
                  <div className="w-12 h-12 rounded-xl grad-btn flex items-center justify-center text-lg font-extrabold text-white shrink-0">
                    {item.count}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-sm">{item.type}</span>
                      <Chip>{item.platform}</Chip>
                      <Chip tone={tone(item.priority)}>Prioridad {item.priority}</Chip>
                    </div>
                    <p className="text-xs text-zinc-500 mt-1 leading-relaxed">{item.notes}</p>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

// ============ 18. A/B Testing Generator ============
export function AbTestingView() {
  const { active: c } = useApp();
  const [sel, setSel] = useState(0);
  if (!c) return null;
  const t = c.abTests[sel];

  return (
    <div>
      <SectionHeader title="A/B Testing Generator" subtitle={`${c.abTests.reduce((n, x) => n + x.variants.length, 0)} variantes listas para testear: hooks, CTAs, thumbnails, intros y finales — con la métrica que decide cada test.`} />

      <div className="flex gap-2 mb-5 flex-wrap">
        {c.abTests.map((x, i) => (
          <button key={x.element} onClick={() => setSel(i)}
            className={`rounded-xl px-4 py-2.5 text-sm font-semibold border transition-colors ${sel === i ? "bg-violet-500/15 border-violet-500/40 text-violet-200" : "bg-white/[0.03] border-white/10 text-zinc-400 hover:text-zinc-200"}`}>
            {x.emoji} {x.element} <span className="text-zinc-600">({x.variants.length})</span>
          </button>
        ))}
      </div>

      {t && (
        <Card className="fade-up" key={sel}>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-bold">{t.emoji} {t.element} — {t.variants.length} variantes</h3>
              <p className="text-xs text-zinc-500 mt-1">📊 Métrica de decisión: <span className="text-cyan-300">{t.metric}</span></p>
            </div>
            <CopyBtn label="Copiar variantes" text={t.variants.map((v, i) => `${i + 1}. ${v}`).join("\n")} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            {t.variants.map((v, i) => (
              <div key={i} className="group flex items-start gap-2.5 text-sm text-zinc-300 bg-white/[0.03] hover:bg-white/[0.06] rounded-lg px-3 py-2.5 transition-colors">
                <span className="text-[10px] font-bold text-zinc-600 mt-0.5 shrink-0 w-5">{String(i + 1).padStart(2, "0")}</span>
                <span className="leading-snug flex-1">{v}</span>
                <span className="opacity-0 group-hover:opacity-100 transition-opacity"><CopyBtn text={v} /></span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

// ============ 17. Creative Iteration ============
export function IterationView() {
  const { active: c, updateCampaign, spend, setView, account } = useApp();
  const [desc, setDesc] = useState(c?.iteration?.input ?? "");
  const [loading, setLoading] = useState(false);
  const [creditError, setCreditError] = useState(false);
  if (!c) return null;

  const analyze = () => {
    if (!desc.trim()) return;
    if (!spend("iteration")) {
      setCreditError(true);
      return;
    }
    setCreditError(false);
    setLoading(true);
    setTimeout(() => {
      const result = analyzeIteration(desc.trim(), getCategory(c.input.categoryId), c.input.name);
      updateCampaign({ ...c, iteration: result });
      setLoading(false);
    }, 900);
  };

  const it = c.iteration;

  return (
    <div>
      <SectionHeader title="Creative Iteration" subtitle="Describe un anuncio que ya tienes (o su rendimiento) y recibe el diagnóstico: qué está mal, qué eliminar, qué agregar y qué testear." />

      <Card className="space-y-4 mb-6">
        <Field label="Describe tu creativo actual" hint="Incluye: hook, duración, escenas, música, CTA y (si los tienes) datos de retención/CTR. Cuanto más detalle, mejor diagnóstico.">
          <textarea className={`${inputCls} min-h-28 resize-y`}
            placeholder={`Ej: Video de 40 segundos. Abre con el logo de la marca 3 segundos, luego muestro el producto girando con música de stock, explico 4 características, y termino con "compra ahora" y "síguenos". La retención cae al 40% en el segundo 5…`}
            value={desc} onChange={(e) => setDesc(e.target.value)} />
        </Field>
        <div className="flex items-center gap-3">
          <button onClick={analyze} disabled={!desc.trim() || loading} className="grad-btn rounded-xl px-5 py-2.5 text-sm font-bold text-white disabled:opacity-40 inline-flex items-center gap-2">
            {loading ? <Loader2 size={14} className="spinner" /> : <Wand2 size={15} />} Diagnosticar creativo
            <span className="text-[11px] font-semibold bg-white/20 rounded-full px-2 py-0.5 inline-flex items-center gap-1">
              <Zap size={10} /> {CREDIT_COSTS.iteration}
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

      {it && (
        <div className="grid grid-cols-2 gap-5 fade-up">
          <IterCard title="❌ Qué está mal" items={it.wrong} tone="bad" />
          <IterCard title="🗑️ Qué eliminar" items={it.remove} tone="bad" />
          <IterCard title="➕ Qué agregar" items={it.add} tone="ok" />
          <IterCard title="🧪 Qué probar" items={it.test} tone="accent" />
          <IterCard title="🪝 Cambios en el hook" items={it.hookChanges} tone="accent" />
          <IterCard title="👆 Cambios en el CTA" items={it.ctaChanges} tone="accent" />
          <IterCard title="⏱️ Cambios en el ritmo" items={it.pacingChanges} tone="ok" />
        </div>
      )}
    </div>
  );
}

function IterCard({ title, items, tone }: { title: string; items: string[]; tone: "ok" | "bad" | "accent" }) {
  const border = tone === "bad" ? "border-red-500/15" : tone === "ok" ? "border-emerald-500/15" : "border-violet-500/15";
  return (
    <Card className={border}>
      <h3 className="font-bold mb-3 text-sm">{title}</h3>
      <div className="space-y-2.5">
        {items.map((x, i) => (
          <div key={i} className="text-xs text-zinc-300 leading-relaxed flex gap-2">
            <span className={tone === "bad" ? "text-red-400" : tone === "ok" ? "text-emerald-400" : "text-violet-400"}>▸</span> {x}
          </div>
        ))}
      </div>
    </Card>
  );
}

// ============ 11. Creative Library ============
export function LibraryView() {
  const { active: c } = useApp();
  if (!c) return null;

  const platforms = [...new Set(c.library.map((l) => l.platform))];

  return (
    <div>
      <SectionHeader title="Creative Library" subtitle="Búsquedas pre-armadas en las bibliotecas de anuncios y plataformas — para estudiar lo que ya funciona con este producto antes de crear." />
      <div className="space-y-5">
        {platforms.map((p) => (
          <Card key={p}>
            <h3 className="font-bold mb-3">{p}</h3>
            <div className="space-y-2">
              {c.library.filter((l) => l.platform === p).map((l, i) => (
                <a key={i} href={l.url} target="_blank" rel="noreferrer"
                  className="flex items-start justify-between gap-3 rounded-xl bg-white/[0.03] border border-white/5 p-3.5 hover:border-cyan-500/40 transition-colors group">
                  <div>
                    <div className="text-sm font-semibold text-zinc-200 group-hover:text-cyan-300 transition-colors flex items-center gap-1.5">
                      {l.name} <ExternalLink size={12} className="opacity-50" />
                    </div>
                    <p className="text-xs text-zinc-500 mt-1 leading-relaxed">{l.note}</p>
                  </div>
                </a>
              ))}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

// ============ Exportar ============
export function ExportView() {
  const { active: c } = useApp();
  const [copied, setCopied] = useState(false);
  if (!c) return null;

  const md = campaignToMarkdown(c);
  const slug = c.input.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 40);

  return (
    <div>
      <SectionHeader title="Exportar campaña" subtitle="Lleva la campaña completa a tu equipo: Markdown para Notion/Docs, JSON para integraciones, o copia directa." />

      <div className="grid grid-cols-3 gap-4 mb-6">
        <button onClick={() => download(`campana-${slug}.md`, md, "text/markdown")}
          className="card p-6 text-left hover:border-violet-500/40 transition-colors">
          <FileText size={22} className="text-violet-300 mb-3" />
          <div className="font-bold text-sm">Descargar Markdown</div>
          <p className="text-xs text-zinc-500 mt-1">Perfecto para Notion, Google Docs u Obsidian. Todo el contenido formateado.</p>
        </button>
        <button onClick={() => download(`campana-${slug}.json`, JSON.stringify(c, null, 2), "application/json")}
          className="card p-6 text-left hover:border-violet-500/40 transition-colors">
          <FileJson size={22} className="text-cyan-300 mb-3" />
          <div className="font-bold text-sm">Descargar JSON</div>
          <p className="text-xs text-zinc-500 mt-1">Datos estructurados para integraciones, automatizaciones o backups.</p>
        </button>
        <button onClick={async () => { await navigator.clipboard.writeText(md); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
          className="card p-6 text-left hover:border-violet-500/40 transition-colors">
          {copied ? <Check size={22} className="text-emerald-400 mb-3" /> : <Download size={22} className="text-emerald-300 mb-3" />}
          <div className="font-bold text-sm">{copied ? "¡Copiado!" : "Copiar al portapapeles"}</div>
          <p className="text-xs text-zinc-500 mt-1">La campaña completa en Markdown, lista para pegar donde quieras.</p>
        </button>
      </div>

      <Card>
        <div className="text-xs font-bold uppercase tracking-wider text-zinc-500 mb-3">Vista previa del documento</div>
        <pre className="text-xs text-zinc-400 whitespace-pre-wrap leading-relaxed max-h-[28rem] overflow-y-auto bg-black/30 rounded-xl p-5 border border-white/5 font-mono">
          {md.slice(0, 6000)}{md.length > 6000 ? "\n\n… (el documento completo incluye todos los módulos)" : ""}
        </pre>
      </Card>
    </div>
  );
}
