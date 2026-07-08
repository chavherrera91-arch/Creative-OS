import React from "react";
import { ArrowRight, Rocket, Sparkles, Trash2, TrendingUp, Zap } from "lucide-react";
import { useApp } from "../store";
import { Card, Chip } from "../components/ui";
import { SOURCE_LABEL } from "../engine/generate";

export default function HomeView() {
  const { campaigns, setActive, setView, deleteCampaign } = useApp();

  return (
    <div className="fade-up">
      {/* Hero */}
      <div className="relative overflow-hidden rounded-3xl border border-white/10 p-10 mb-8"
        style={{ background: "radial-gradient(1200px 400px at 20% -10%, rgba(124,58,237,0.25), transparent), radial-gradient(800px 300px at 90% 0%, rgba(34,211,238,0.15), transparent), #0e0e17" }}>
        <div className="max-w-2xl">
          <div className="inline-flex items-center gap-2 text-xs font-semibold text-cyan-300 bg-cyan-500/10 rounded-full px-3 py-1 mb-4">
            <Sparkles size={12} /> Creative Operating System
          </div>
          <h1 className="text-4xl font-extrabold tracking-tight leading-tight">
            Pega un producto.<br />
            <span className="grad-text">Sal con una campaña completa.</span>
          </h1>
          <p className="text-zinc-400 mt-4 leading-relaxed">
            AliExpress, Amazon, Shopify, TikTok, cualquier tienda o una simple imagen.
            Creative OS analiza el producto y genera hooks, guiones, anuncios, prompts de IA,
            UGC, landing, ofertas y un plan de testeo — todo listo para producir.
          </p>
          <button
            onClick={() => setView("new")}
            className="grad-btn mt-6 inline-flex items-center gap-2 rounded-xl px-6 py-3 font-bold text-white"
          >
            <Rocket size={17} /> Crear campaña <ArrowRight size={16} />
          </button>
        </div>
      </div>

      {/* Stats del flujo */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        {[
          { icon: Zap, t: "140+ hooks", d: "14 categorías emocionales listas para grabar" },
          { icon: TrendingUp, t: "36 guiones", d: "De 15 segundos a VSL de 3 minutos" },
          { icon: Sparkles, t: "18 módulos", d: "Del análisis al plan de A/B testing" },
        ].map((s, i) => (
          <Card key={i} className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-lg bg-violet-500/15 flex items-center justify-center shrink-0">
              <s.icon size={17} className="text-violet-300" />
            </div>
            <div>
              <div className="font-bold">{s.t}</div>
              <div className="text-xs text-zinc-500 mt-0.5">{s.d}</div>
            </div>
          </Card>
        ))}
      </div>

      {/* Campañas */}
      <h2 className="text-lg font-bold mb-3">Tus campañas</h2>
      {campaigns.length === 0 ? (
        <Card className="text-center py-12 text-zinc-500">
          <p className="text-sm">Todavía no hay campañas. Crea la primera pegando un link o subiendo una imagen.</p>
        </Card>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          {campaigns.map((c) => (
            <Card key={c.id} className="hover:border-violet-500/40 transition-colors cursor-pointer group"
            >
              <div onClick={() => { setActive(c.id); setView("overview"); }}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="font-bold truncate">{c.input.name}</div>
                    <div className="text-xs text-zinc-500 mt-0.5">
                      {new Date(c.createdAt).toLocaleDateString("es")} · {SOURCE_LABEL[c.input.sourceType]}
                      {c.generatedBy === "claude" && " · ✨ Claude"}
                    </div>
                  </div>
                  <div className={`text-xl font-extrabold shrink-0 ${c.score.total >= 80 ? "text-emerald-400" : c.score.total >= 60 ? "text-amber-400" : "text-red-400"}`}>
                    {c.score.total}
                  </div>
                </div>
                <div className="flex gap-1.5 mt-3 flex-wrap">
                  <Chip tone="accent">{c.hooks.reduce((n, h) => n + h.items.length, 0)} hooks</Chip>
                  <Chip>{c.scripts.length} guiones</Chip>
                  <Chip>{c.ads.length} ads</Chip>
                  <Chip>{c.ugc.length} UGC</Chip>
                </div>
              </div>
              <div className="flex justify-end mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                  onClick={(e) => { e.stopPropagation(); if (confirm(`¿Eliminar la campaña "${c.input.name}"?`)) deleteCampaign(c.id); }}
                  className="text-zinc-600 hover:text-red-400 p-1"
                  title="Eliminar campaña"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
