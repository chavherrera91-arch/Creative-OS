import React, { useMemo, useState } from "react";
import { Camera, ChevronDown, Clock, Film, Search } from "lucide-react";
import { useApp } from "../store";
import { Card, Chip, CopyBtn, inputCls, SectionHeader } from "../components/ui";

// ============ 3. Hook Generator ============
export function HooksView() {
  const { active: c } = useApp();
  const [filter, setFilter] = useState("");
  const [cat, setCat] = useState<string | null>(null);
  if (!c) return null;

  const total = c.hooks.reduce((n, h) => n + h.items.length, 0);
  const groups = c.hooks
    .filter((g) => !cat || g.category === cat)
    .map((g) => ({ ...g, items: g.items.filter((i) => !filter || i.toLowerCase().includes(filter.toLowerCase())) }))
    .filter((g) => g.items.length > 0);

  return (
    <div>
      <SectionHeader
        title="Hook Generator"
        subtitle={`${total} hooks en ${c.hooks.length} categorías emocionales. Copia cualquiera y úsalo tal cual en tu próximo video.`}
        right={<CopyBtn text={c.hooks.flatMap((g) => g.items).join("\n")} label="Copiar todos" />}
      />

      <div className="flex gap-3 mb-5 items-center">
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-600" />
          <input className={`${inputCls} pl-9 py-2`} placeholder="Buscar hooks…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        </div>
        <div className="flex gap-1.5 flex-wrap">
          <button onClick={() => setCat(null)} className={`chip ${!cat ? "bg-violet-500/20 text-violet-200" : "bg-white/5 text-zinc-400 hover:text-zinc-200"}`}>Todas</button>
          {c.hooks.map((g) => (
            <button key={g.category} onClick={() => setCat(cat === g.category ? null : g.category)}
              className={`chip ${cat === g.category ? "bg-violet-500/20 text-violet-200" : "bg-white/5 text-zinc-400 hover:text-zinc-200"}`}>
              {g.emoji} {g.category}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-5">
        {groups.map((g) => (
          <Card key={g.category}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-bold">{g.emoji} {g.category} <span className="text-zinc-600 text-sm font-normal">({g.items.length})</span></h3>
              <CopyBtn text={g.items.join("\n")} label="Copiar categoría" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              {g.items.map((h, i) => (
                <div key={i} className="group flex items-start justify-between gap-2 text-sm text-zinc-300 bg-white/[0.03] hover:bg-white/[0.06] rounded-lg px-3 py-2.5 transition-colors">
                  <span className="leading-snug">{h}</span>
                  <span className="opacity-0 group-hover:opacity-100 transition-opacity"><CopyBtn text={h} /></span>
                </div>
              ))}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

// ============ 4. Ad Generator ============
export function AdsView() {
  const { active: c } = useApp();
  if (!c) return null;

  return (
    <div>
      <SectionHeader title="Ad Generator" subtitle="Anuncios completos con copy, headline, CTA, especificaciones técnicas y notas de producción para cada formato y plataforma." />
      <div className="space-y-5">
        {c.ads.map((a, i) => (
          <Card key={i}>
            <div className="flex items-start justify-between gap-3 mb-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="font-bold">{a.title}</h3>
                </div>
                <div className="flex gap-1.5 mt-1.5">
                  <Chip tone="accent">{a.platform}</Chip>
                  <Chip>{a.format}</Chip>
                </div>
              </div>
              <CopyBtn label="Copiar anuncio" text={`${a.title}\n\nTEXTO PRINCIPAL:\n${a.primaryText}\n\nHEADLINE: ${a.headline}\nDESCRIPCIÓN: ${a.description}\nCTA: ${a.cta}\nSPECS: ${a.specs}\nNOTAS: ${a.notes}`} />
            </div>
            <div className="grid grid-cols-5 gap-4">
              <div className="col-span-3">
                <div className="text-[10px] font-bold uppercase tracking-widest text-zinc-600 mb-1.5">Texto principal</div>
                <p className="text-sm text-zinc-300 whitespace-pre-line leading-relaxed bg-white/[0.03] rounded-xl p-4 border border-white/5">{a.primaryText}</p>
              </div>
              <div className="col-span-2 space-y-3 text-sm">
                <div>
                  <div className="text-[10px] font-bold uppercase tracking-widest text-zinc-600 mb-1">Headline</div>
                  <p className="text-zinc-200 font-semibold">{a.headline}</p>
                </div>
                <div>
                  <div className="text-[10px] font-bold uppercase tracking-widest text-zinc-600 mb-1">CTA</div>
                  <span className="grad-btn text-xs font-bold text-white rounded-lg px-3 py-1.5 inline-block">{a.cta}</span>
                </div>
                <div>
                  <div className="text-[10px] font-bold uppercase tracking-widest text-zinc-600 mb-1">Specs</div>
                  <p className="text-xs text-zinc-400 leading-relaxed">{a.specs}</p>
                </div>
                <div>
                  <div className="text-[10px] font-bold uppercase tracking-widest text-zinc-600 mb-1">Notas de producción</div>
                  <p className="text-xs text-zinc-400 leading-relaxed">{a.notes}</p>
                </div>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

// ============ 5. Script Generator ============
export function ScriptsView() {
  const { active: c } = useApp();
  const [duration, setDuration] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(0);
  if (!c) return null;

  const durations = [...new Set(c.scripts.map((s) => s.duration))];
  const scripts = c.scripts.filter((s) => !duration || s.duration === duration);

  return (
    <div>
      <SectionHeader title="Script Generator" subtitle={`${c.scripts.length} guiones completos con timing, voz en off y dirección visual — clasificados por duración y ángulo.`} />

      <div className="flex gap-1.5 mb-5">
        <button onClick={() => setDuration(null)} className={`chip ${!duration ? "bg-violet-500/20 text-violet-200" : "bg-white/5 text-zinc-400 hover:text-zinc-200"}`}>
          <Clock size={11} /> Todas
        </button>
        {durations.map((d) => (
          <button key={d} onClick={() => { setDuration(duration === d ? null : d); setOpen(0); }}
            className={`chip ${duration === d ? "bg-violet-500/20 text-violet-200" : "bg-white/5 text-zinc-400 hover:text-zinc-200"}`}>
            {d}
          </button>
        ))}
      </div>

      <div className="space-y-3">
        {scripts.map((s, i) => (
          <Card key={i} className="!p-0 overflow-hidden">
            <button onClick={() => setOpen(open === i ? null : i)} className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-white/[0.02] transition-colors">
              <div className="flex items-center gap-3 min-w-0">
                <Chip tone="accent">{s.duration}</Chip>
                <div className="min-w-0">
                  <div className="font-bold text-sm truncate">{s.title}</div>
                  <div className="text-xs text-zinc-500 truncate mt-0.5">Hook: {s.hook}</div>
                </div>
              </div>
              <ChevronDown size={16} className={`text-zinc-500 transition-transform shrink-0 ${open === i ? "rotate-180" : ""}`} />
            </button>
            {open === i && (
              <div className="px-5 pb-5 fade-up">
                <div className="flex justify-end mb-2">
                  <CopyBtn label="Copiar guion" text={`${s.title} [${s.duration}]\nHOOK: ${s.hook}\n\n${s.beats.map((b) => `[${b.time}] ${b.label}\nVOZ: ${b.voiceover}\nVISUAL: ${b.visual}`).join("\n\n")}\n\nCTA: ${s.cta}`} />
                </div>
                <div className="space-y-2">
                  {s.beats.map((b, bi) => (
                    <div key={bi} className="grid grid-cols-12 gap-3 rounded-xl bg-white/[0.03] border border-white/5 p-3.5">
                      <div className="col-span-2">
                        <div className="text-xs font-bold text-cyan-300">{b.time}</div>
                        <div className="text-[10px] uppercase tracking-wider text-zinc-600 font-bold mt-0.5">{b.label}</div>
                      </div>
                      <div className="col-span-5">
                        <div className="text-[10px] font-bold uppercase tracking-widest text-zinc-600 mb-1">🎙 Voz</div>
                        <p className="text-sm text-zinc-300 leading-snug">{b.voiceover}</p>
                      </div>
                      <div className="col-span-5">
                        <div className="text-[10px] font-bold uppercase tracking-widest text-zinc-600 mb-1">🎥 Visual</div>
                        <p className="text-xs text-zinc-400 leading-snug">{b.visual}</p>
                      </div>
                    </div>
                  ))}
                  <div className="rounded-xl bg-violet-500/10 border border-violet-500/20 p-3.5 text-sm">
                    <span className="text-[10px] font-bold uppercase tracking-widest text-violet-300 block mb-1">CTA final</span>
                    <span className="text-zinc-200">{s.cta}</span>
                  </div>
                </div>
              </div>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}

// ============ 6. Visual Generator ============
export function VisualView() {
  const { active: c } = useApp();
  if (!c) return null;

  return (
    <div>
      <SectionHeader title="Visual Generator" subtitle="Storyboards escena por escena: plano, sujeto, expresión, luz, texto en pantalla, movimiento de cámara, duración y audio." />
      <div className="space-y-6">
        {c.visualSets.map((set, si) => (
          <Card key={si}>
            <div className="flex items-start justify-between mb-1">
              <h3 className="font-bold flex items-center gap-2"><Film size={17} className="text-violet-300" /> {set.title}</h3>
              <CopyBtn label="Copiar storyboard" text={`${set.title}\n${set.concept}\n\n${set.scenes.map((s) => `ESCENA ${s.n}\nPlano: ${s.shot}\nSujeto: ${s.subject}\nExpresión: ${s.expression}\nLuz: ${s.light}\nTexto: ${s.text}\nMovimiento: ${s.movement}\nDuración: ${s.duration}\nAudio: ${s.audio}`).join("\n\n")}`} />
            </div>
            <p className="text-xs text-zinc-500 mb-4">{set.concept}</p>
            <div className="grid grid-cols-3 gap-3">
              {set.scenes.map((s) => (
                <div key={s.n} className="rounded-xl bg-white/[0.03] border border-white/5 p-4">
                  <div className="flex items-center justify-between mb-2.5">
                    <span className="text-xs font-extrabold text-cyan-300">ESCENA {s.n}</span>
                    <Chip>{s.duration}</Chip>
                  </div>
                  <div className="space-y-1.5 text-xs">
                    <Row k="Plano" v={s.shot} />
                    <Row k="Sujeto" v={s.subject} />
                    <Row k="Expresión" v={s.expression} />
                    <Row k="Luz" v={s.light} />
                    {s.text && <Row k="Texto" v={`"${s.text}"`} accent />}
                    <Row k="Movimiento" v={s.movement} />
                    <Row k="Audio" v={s.audio} />
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

function Row({ k, v, accent }: { k: string; v: string; accent?: boolean }) {
  return (
    <div className="flex gap-2">
      <span className="text-zinc-600 w-[70px] shrink-0 font-semibold">{k}</span>
      <span className={accent ? "text-cyan-300" : "text-zinc-300"}>{v}</span>
    </div>
  );
}

// ============ 7-8. AI Prompts ============
function PromptsView({ title, subtitle, groups }: { title: string; subtitle: string; groups: { tool: string; prompts: { title: string; prompt: string; meta: string }[] }[] }) {
  const [tool, setTool] = useState<string | null>(null);
  const shown = groups.filter((g) => !tool || g.tool === tool);

  return (
    <div>
      <SectionHeader title={title} subtitle={subtitle} />
      <div className="flex gap-1.5 mb-5 flex-wrap">
        <button onClick={() => setTool(null)} className={`chip ${!tool ? "bg-violet-500/20 text-violet-200" : "bg-white/5 text-zinc-400 hover:text-zinc-200"}`}>Todas</button>
        {groups.map((g) => (
          <button key={g.tool} onClick={() => setTool(tool === g.tool ? null : g.tool)}
            className={`chip ${tool === g.tool ? "bg-violet-500/20 text-violet-200" : "bg-white/5 text-zinc-400 hover:text-zinc-200"}`}>
            {g.tool}
          </button>
        ))}
      </div>
      <div className="space-y-5">
        {shown.map((g) => (
          <Card key={g.tool}>
            <h3 className="font-bold mb-3 flex items-center gap-2"><Camera size={16} className="text-violet-300" /> {g.tool}</h3>
            <div className="space-y-3">
              {g.prompts.map((p, i) => (
                <div key={i} className="rounded-xl bg-white/[0.03] border border-white/5 p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold">{p.title}</span>
                      <Chip>{p.meta}</Chip>
                    </div>
                    <CopyBtn text={p.prompt} label="Copiar prompt" />
                  </div>
                  <p className="text-xs text-zinc-400 font-mono leading-relaxed bg-black/30 rounded-lg p-3 border border-white/5">{p.prompt}</p>
                </div>
              ))}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

export function ImagePromptsView() {
  const { active: c } = useApp();
  if (!c) return null;
  return <PromptsView title="AI Image Prompts" subtitle="Prompts optimizados por herramienta: GPT Image, Midjourney, Flux, Nano Banana, Hailuo y Kling. En inglés porque los modelos rinden mejor así." groups={c.imagePrompts} />;
}

export function VideoPromptsView() {
  const { active: c } = useApp();
  if (!c) return null;
  return <PromptsView title="AI Video Prompts" subtitle="Prompts de video para Veo, Kling, Hailuo, Runway y Pika — con movimiento de cámara, luz y duración especificados." groups={c.videoPrompts} />;
}

// ============ 9. UGC Generator ============
export function UgcView() {
  const { active: c } = useApp();
  const [sel, setSel] = useState(0);
  if (!c) return null;
  const u = c.ugc[sel];

  return (
    <div>
      <SectionHeader title="UGC Generator" subtitle="Anuncios estilo influencer con 7 personalidades distintas: guion completo, tono, setting y vestuario para cada creador." />

      <div className="flex gap-2 mb-5 flex-wrap">
        {c.ugc.map((p, i) => (
          <button key={p.persona} onClick={() => setSel(i)}
            className={`rounded-xl px-4 py-2.5 text-sm font-semibold border transition-colors ${sel === i ? "bg-violet-500/15 border-violet-500/40 text-violet-200" : "bg-white/[0.03] border-white/10 text-zinc-400 hover:text-zinc-200"}`}>
            {p.emoji} {p.persona}
          </button>
        ))}
      </div>

      {u && (
        <div className="grid grid-cols-3 gap-5 fade-up" key={sel}>
          <Card className="col-span-2">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-bold text-lg">{u.emoji} {u.persona}</h3>
              <CopyBtn label="Copiar guion" text={`UGC — ${u.persona}\nPerfil: ${u.profile}\nTono: ${u.tone}\nSetting: ${u.setting}\nVestuario: ${u.wardrobe}\n\nHOOK: ${u.hook}\n\nGUION:\n${u.script}`} />
            </div>
            <div className="rounded-xl bg-cyan-500/10 border border-cyan-500/20 p-4 mb-4">
              <div className="text-[10px] font-bold uppercase tracking-widest text-cyan-300 mb-1">Hook de apertura</div>
              <p className="text-sm text-zinc-100 font-medium">{u.hook}</p>
            </div>
            <div className="text-[10px] font-bold uppercase tracking-widest text-zinc-600 mb-2">Guion completo (30-45s)</div>
            <p className="text-sm text-zinc-300 leading-relaxed whitespace-pre-line bg-white/[0.03] rounded-xl p-4 border border-white/5">{u.script}</p>
          </Card>
          <div className="space-y-4">
            <Card>
              <div className="text-[10px] font-bold uppercase tracking-widest text-zinc-600 mb-1.5">Perfil del creador</div>
              <p className="text-xs text-zinc-300 leading-relaxed">{u.profile}</p>
            </Card>
            <Card>
              <div className="text-[10px] font-bold uppercase tracking-widest text-zinc-600 mb-1.5">Tono</div>
              <p className="text-xs text-zinc-300 leading-relaxed">{u.tone}</p>
            </Card>
            <Card>
              <div className="text-[10px] font-bold uppercase tracking-widest text-zinc-600 mb-1.5">Setting / localización</div>
              <p className="text-xs text-zinc-300 leading-relaxed">{u.setting}</p>
            </Card>
            <Card>
              <div className="text-[10px] font-bold uppercase tracking-widest text-zinc-600 mb-1.5">Vestuario</div>
              <p className="text-xs text-zinc-300 leading-relaxed">{u.wardrobe}</p>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}

// ============ 12. Thumbnail Generator ============
export function ThumbnailsView() {
  const { active: c } = useApp();
  if (!c) return null;

  return (
    <div>
      <SectionHeader title="Thumbnail Generator" subtitle="Conceptos de miniatura optimizados para CTR, con layout, paleta de colores y prompt de IA para generarlos." />
      <div className="grid grid-cols-2 gap-5">
        {c.thumbnails.map((t, i) => (
          <Card key={i}>
            {/* Mini-preview del concepto */}
            <div className="rounded-xl h-36 mb-4 flex items-center justify-center relative overflow-hidden border border-white/10"
              style={{ background: `linear-gradient(135deg, ${t.colors[2] ?? "#111"}, #1a1a28)` }}>
              <span className="text-2xl font-black text-center px-6 leading-tight tracking-tight"
                style={{ color: t.colors[0], textShadow: `2px 2px 0 rgba(0,0,0,0.6)` }}>
                {t.headline}
              </span>
              <div className="absolute bottom-2 right-2 flex gap-1">
                {t.colors.map((col) => (
                  <span key={col} className="w-4 h-4 rounded-full border border-white/20" style={{ background: col }} />
                ))}
              </div>
            </div>
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-bold text-sm">{t.concept}</h3>
              <CopyBtn text={t.prompt} label="Copiar prompt" />
            </div>
            <p className="text-xs text-zinc-400 leading-relaxed mb-2">{t.style}</p>
            <p className="text-xs text-zinc-500 leading-relaxed"><strong className="text-zinc-400">Layout:</strong> {t.layout}</p>
          </Card>
        ))}
      </div>
    </div>
  );
}
