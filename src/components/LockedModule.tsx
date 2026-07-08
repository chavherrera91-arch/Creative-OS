import React from "react";
import { Crown, Lock, Sparkles } from "lucide-react";
import { useApp } from "../store";
import { MODULES, ModuleId } from "../types";
import { MODULE_MIN_PLAN, getPlan } from "../plans";

// Textos de venta por módulo: qué se pierde el usuario exactamente
const PITCH: Partial<Record<ModuleId, string[]>> = {
  viral: ["Probabilidad viral 0-100 antes de gastar en ads", "6 factores analizados con recomendaciones", "Plan de maximización de alcance orgánico"],
  scripts: ["36 guiones completos de 15s a VSL de 3 minutos", "Timing exacto, voz en off y dirección visual", "6 ángulos de venta distintos por duración"],
  ads: ["10 anuncios listos: Meta, TikTok, Shorts, Reels…", "Copy, headline, CTA y specs por plataforma", "Notas de producción de cada formato"],
  ugc: ["7 personalidades: Mamá, Doctor, Deportista, CEO…", "Guion hablado completo por creador", "Tono, setting y vestuario definidos"],
  landing: ["Headline, beneficios, FAQ y garantía listos", "Comparativa 'nosotros vs. ellos'", "Reviews de ejemplo y 5 variantes de CTA"],
  offers: ["7 estructuras: 2x1, bundle, regalo, escasez…", "Matemática de margen de cada oferta", "Copy de ejemplo listo para usar"],
  thumbnails: ["6 conceptos de miniatura optimizados para CTR", "Paleta, layout y prompt de IA por concepto", "Previews visuales de cada idea"],
  export: ["Campaña completa en Markdown para Notion/Docs", "JSON estructurado para integraciones", "Copia directa al portapapeles"],
  visual: ["3 storyboards escena por escena", "Plano, luz, expresión, movimiento y audio", "Listos para pasar a tu editor o filmmaker"],
  imageprompts: ["18 prompts para Midjourney, Flux, GPT Image…", "Hero shots, lifestyle, antes/después e infografías", "Optimizados por herramienta y formato"],
  videoprompts: ["12 prompts para Veo, Kling, Runway, Pika…", "Movimiento de cámara y luz especificados", "Desde demos hasta loops satisfying"],
  competitor: ["Extrae hooks, CTAs y framework de cualquier competidor", "Detecta sus debilidades y cómo explotarlas", "Estrategia concreta para ganarle"],
  planner: ["Plan de producción exacto de 4 semanas", "Qué crear, cuánto y para qué canal", "Prioridades para no quemar presupuesto"],
  abtesting: ["115+ variantes listas para testear", "50 hooks, 20 CTAs, 20 thumbnails, intros y finales", "La métrica que decide cada test"],
  iteration: ["Diagnóstico de tus anuncios actuales", "Qué eliminar, agregar y cambiar del hook/CTA/ritmo", "Tests concretos para revivir un creativo"],
};

export default function LockedModule({ moduleId }: { moduleId: ModuleId }) {
  const { setView, account } = useApp();
  const mod = MODULES.find((m) => m.id === moduleId);
  const requiredPlan = getPlan(MODULE_MIN_PLAN[moduleId]);
  const pitch = PITCH[moduleId] ?? ["Desbloquea esta herramienta con un plan superior"];

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center fade-up">
      <div className="w-16 h-16 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center mb-5">
        <Lock size={26} className="text-zinc-500" />
      </div>

      <div className="inline-flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-widest text-violet-300 bg-violet-500/10 rounded-full px-3 py-1 mb-3">
        <Crown size={11} /> Requiere plan {requiredPlan.name}
      </div>

      <h2 className="text-2xl font-extrabold tracking-tight">{mod?.name}</h2>
      <p className="text-sm text-zinc-500 mt-2 max-w-md">
        Esta herramienta está incluida en el plan <strong className="text-zinc-300">{requiredPlan.name}</strong> (${requiredPlan.price}/mes).
        Tu plan actual es <strong className="text-zinc-300">{getPlan(account.planId).name}</strong>.
      </p>

      <div className="mt-6 space-y-2.5 text-left">
        {pitch.map((p, i) => (
          <div key={i} className="flex items-center gap-2.5 text-sm text-zinc-300">
            <Sparkles size={14} className="text-cyan-300 shrink-0" /> {p}
          </div>
        ))}
      </div>

      <button
        onClick={() => setView("plans")}
        className="grad-btn mt-8 rounded-xl px-8 py-3 font-bold text-white inline-flex items-center gap-2"
      >
        <Crown size={16} /> Ver planes desde ${requiredPlan.price}/mes
      </button>
      <p className="text-[11px] text-zinc-600 mt-3">Los créditos se renuevan cada mes · Cancela cuando quieras</p>
    </div>
  );
}
