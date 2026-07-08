import React, { useState } from "react";
import { Check, Copy, Star } from "lucide-react";

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`card p-5 ${className}`}>{children}</div>;
}

export function SectionHeader({ title, subtitle, right }: { title: string; subtitle?: string; right?: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 mb-5">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        {subtitle && <p className="text-sm text-zinc-400 mt-1 max-w-2xl">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

export function Stars({ n, max = 5 }: { n: number; max?: number }) {
  return (
    <span className="inline-flex gap-0.5">
      {Array.from({ length: max }).map((_, i) => (
        <Star
          key={i}
          size={14}
          className={i < n ? "fill-amber-400 text-amber-400" : "text-zinc-700"}
        />
      ))}
    </span>
  );
}

export function CopyBtn({ text, label }: { text: string; label?: string }) {
  const [ok, setOk] = useState(false);
  return (
    <button
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setOk(true);
          setTimeout(() => setOk(false), 1400);
        } catch { /* clipboard bloqueado */ }
      }}
      className="inline-flex items-center gap-1.5 text-xs font-medium text-zinc-400 hover:text-white transition-colors shrink-0 px-2 py-1 rounded-md hover:bg-white/5"
      title="Copiar"
    >
      {ok ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
      {label && <span>{ok ? "Copiado" : label}</span>}
    </button>
  );
}

export function ScoreRing({ value, size = 120, label }: { value: number; size?: number; label?: string }) {
  const r = (size - 14) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, value));
  const color = pct >= 80 ? "#34d399" : pct >= 60 ? "#fbbf24" : "#f87171";
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth="9" />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none"
          stroke={color} strokeWidth="9" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c - (c * pct) / 100}
          style={{ transition: "stroke-dashoffset 1s ease" }}
        />
      </svg>
      <div className="absolute text-center">
        <div className="text-3xl font-extrabold" style={{ color }}>{Math.round(pct)}</div>
        {label && <div className="text-[10px] uppercase tracking-wider text-zinc-500 font-semibold">{label}</div>}
      </div>
    </div>
  );
}

export function Bar({ value, max = 10, color }: { value: number; max?: number; color?: string }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="h-2 rounded-full bg-white/5 overflow-hidden w-full">
      <div
        className="h-full rounded-full"
        style={{
          width: `${pct}%`,
          background: color ?? "linear-gradient(90deg,#7c3aed,#22d3ee)",
          transition: "width 0.8s ease",
        }}
      />
    </div>
  );
}

export function Chip({ children, tone = "default" }: { children: React.ReactNode; tone?: "default" | "ok" | "warn" | "bad" | "accent" }) {
  const tones: Record<string, string> = {
    default: "bg-white/5 text-zinc-300",
    ok: "bg-emerald-500/10 text-emerald-300",
    warn: "bg-amber-500/10 text-amber-300",
    bad: "bg-red-500/10 text-red-300",
    accent: "bg-violet-500/15 text-violet-300",
  };
  return <span className={`chip ${tones[tone]}`}>{children}</span>;
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-1.5">{label}</span>
      {children}
      {hint && <span className="block text-xs text-zinc-500 mt-1.5">{hint}</span>}
    </label>
  );
}

export const inputCls =
  "w-full rounded-xl bg-white/[0.04] border border-white/10 px-3.5 py-2.5 text-sm placeholder-zinc-600 outline-none focus:border-violet-500/60 focus:bg-white/[0.06] transition-colors";

export function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex gap-2 text-sm py-1">
      <span className="text-zinc-500 shrink-0 w-28">{k}</span>
      <span className="text-zinc-200">{v}</span>
    </div>
  );
}
