import React, { useState } from "react";
import { Check, Coins, CreditCard, Crown, Loader2, Sparkles, X, Zap } from "lucide-react";
import { useApp } from "../store";
import { Card, Chip, SectionHeader } from "../components/ui";
import { ACTION_LABEL, CREDIT_COSTS, CreditAction, PLANS, PlanId, getPlan, isUpgrade } from "../plans";
import { supabase } from "../lib/supabase";

async function callApi(path: string, body: object): Promise<{ url?: string; error?: string }> {
  const { data } = await supabase!.auth.getSession();
  const res = await fetch(path, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${data.session?.access_token ?? ""}`,
    },
    body: JSON.stringify(body),
  });
  return res.json();
}

export default function PlansView() {
  const { account, changePlan, setView, cloud, user } = useApp();
  const current = getPlan(account.planId);
  const [busy, setBusy] = useState<string | null>(null);
  const [apiError, setApiError] = useState("");

  const select = async (planId: PlanId) => {
    if (planId === account.planId) return;
    const plan = getPlan(planId);

    // ---- Modo nube: pago real vía Stripe ----
    if (cloud) {
      if (!user) {
        setView("auth");
        return;
      }
      setApiError("");
      setBusy(planId);
      try {
        if (planId === "free") {
          // Bajar a gratis = cancelar la suscripción desde el portal de Stripe
          const r = await callApi("/api/portal", {});
          if (r.url) window.location.href = r.url;
          else setApiError(r.error ?? "No se pudo abrir el portal de facturación.");
        } else {
          const r = await callApi("/api/checkout", { plan: planId });
          if (r.url) window.location.href = r.url;
          else setApiError(r.error ?? "No se pudo iniciar el pago.");
        }
      } catch {
        setApiError("Error de conexión con el servidor de pagos.");
      } finally {
        setBusy(null);
      }
      return;
    }

    // ---- Modo demo (sin Supabase/Stripe configurados) ----
    const upgrading = isUpgrade(account.planId, planId);
    const msg = upgrading
      ? `Activar el plan ${plan.name} ($${plan.price}/mes).\n\nRecibirás ${plan.credits} créditos y hasta ${plan.campaignLimit} campañas al mes.\n\n(Modo demo: la pasarela de pago aún no está conectada — el plan se activa al instante.)`
      : `¿Bajar al plan ${plan.name}? Perderás acceso a los módulos superiores y tus créditos se ajustarán a ${plan.credits}.`;
    if (confirm(msg)) {
      changePlan(planId);
    }
  };

  const openPortal = async () => {
    setApiError("");
    setBusy("portal");
    try {
      const r = await callApi("/api/portal", {});
      if (r.url) window.location.href = r.url;
      else setApiError(r.error ?? "No se pudo abrir el portal.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="fade-up">
      <div className="text-center mb-10">
        <div className="inline-flex items-center gap-2 text-xs font-semibold text-cyan-300 bg-cyan-500/10 rounded-full px-3 py-1 mb-4">
          <Crown size={12} /> Planes y precios
        </div>
        <h1 className="text-3xl font-extrabold tracking-tight">
          Elige cuánto quieres <span className="grad-text">escalar</span>
        </h1>
        <p className="text-sm text-zinc-400 mt-2 max-w-xl mx-auto">
          Todos los planes incluyen el motor de generación completo y guardado de campañas.
          Los créditos se renuevan el día 1 de cada mes.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-5 items-stretch">
        {PLANS.map((plan) => {
          const isCurrent = plan.id === account.planId;
          return (
            <div
              key={plan.id}
              className={`relative rounded-2xl border p-6 flex flex-col ${
                plan.highlight
                  ? "border-violet-500/60 bg-gradient-to-b from-violet-500/[0.08] to-transparent"
                  : "border-white/10 bg-[#10101a]"
              }`}
            >
              {plan.highlight && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 grad-btn text-white text-[10px] font-bold uppercase tracking-widest rounded-full px-3 py-1">
                  Más popular
                </span>
              )}

              <div className="flex items-center justify-between">
                <h3 className="text-lg font-extrabold">{plan.name}</h3>
                {isCurrent && <Chip tone="ok">Tu plan</Chip>}
              </div>
              <div className="mt-2 flex items-end gap-1">
                <span className="text-4xl font-black">${plan.price}</span>
                <span className="text-zinc-500 text-sm mb-1.5">/ mes</span>
              </div>
              <p className="text-xs text-zinc-400 mt-2 leading-relaxed min-h-8">{plan.tagline}</p>

              <div className="grid grid-cols-2 gap-2 mt-4">
                <div className="min-w-0 rounded-xl bg-white/[0.04] border border-white/5 p-2.5 text-center">
                  <div className="text-xl font-extrabold grad-text">{plan.credits}</div>
                  <div className="text-[9px] uppercase tracking-wide text-zinc-500 font-bold">créditos</div>
                </div>
                <div className="min-w-0 rounded-xl bg-white/[0.04] border border-white/5 p-2.5 text-center">
                  <div className="text-xl font-extrabold grad-text">{plan.campaignLimit}</div>
                  <div className="text-[9px] uppercase tracking-wide text-zinc-500 font-bold">campañas</div>
                </div>
              </div>

              <div className="mt-5 space-y-2.5 flex-1">
                {plan.features.map((f, i) => (
                  <div key={i} className={`flex items-start gap-2 text-xs leading-relaxed ${f.included ? "text-zinc-300" : "text-zinc-600"}`}>
                    {f.included
                      ? <Check size={14} className="text-emerald-400 shrink-0 mt-0.5" />
                      : <X size={14} className="text-zinc-700 shrink-0 mt-0.5" />}
                    {f.text}
                  </div>
                ))}
              </div>

              <button
                onClick={() => select(plan.id)}
                disabled={isCurrent || busy !== null}
                className={`mt-6 rounded-xl px-5 py-3 text-sm font-bold transition-colors inline-flex items-center justify-center gap-2 ${
                  isCurrent
                    ? "bg-white/5 text-zinc-500 cursor-default"
                    : plan.highlight
                      ? "grad-btn text-white disabled:opacity-50"
                      : "bg-white/10 hover:bg-white/15 text-white disabled:opacity-50"
                }`}
              >
                {busy === plan.id && <Loader2 size={14} className="spinner" />}
                {isCurrent ? "Plan activo" : cloud && !user ? "Crear cuenta para empezar" : plan.cta}
              </button>
            </div>
          );
        })}
      </div>

      {/* Cómo funcionan los créditos */}
      <div className="grid grid-cols-2 gap-5 mt-8">
        <Card>
          <h3 className="font-bold mb-3 flex items-center gap-2"><Coins size={17} className="text-amber-300" /> Cómo funcionan los créditos</h3>
          <p className="text-xs text-zinc-400 leading-relaxed mb-4">
            Cada acción generativa consume créditos, igual que en las IAs de generación de imágenes.
            Tu saldo se renueva automáticamente el día 1 de cada mes según tu plan.
          </p>
          <div className="space-y-2">
            {(Object.keys(CREDIT_COSTS) as CreditAction[]).map((a) => (
              <div key={a} className="flex items-center justify-between rounded-lg bg-white/[0.03] border border-white/5 px-3.5 py-2.5">
                <span className="text-sm text-zinc-300">{ACTION_LABEL[a]}</span>
                <span className="text-sm font-bold text-amber-300 flex items-center gap-1"><Zap size={12} /> {CREDIT_COSTS[a]} créditos</span>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <h3 className="font-bold mb-3 flex items-center gap-2"><Sparkles size={17} className="text-violet-300" /> Tu cuenta ahora mismo</h3>
          <div className="space-y-3 text-sm">
            {cloud && <Row k="Sesión" v={user ? <span className="text-emerald-300">{user.email}</span> : <span className="text-zinc-500">Sin iniciar</span>} />}
            <Row k="Plan actual" v={<span className="font-bold">{current.name} — ${current.price}/mes</span>} />
            <Row k="Créditos disponibles" v={<span className="font-bold text-amber-300">{account.credits} de {current.credits}</span>} />
            <Row k="Campañas este mes" v={`${account.campaignsThisMonth} de ${current.campaignLimit}`} />
            <Row k="Renovación" v="Día 1 del próximo mes" />
          </div>

          {apiError && <p className="text-xs text-red-400 mt-3">{apiError}</p>}

          {cloud && user && account.planId !== "free" && (
            <button
              onClick={openPortal}
              disabled={busy !== null}
              className="mt-4 w-full rounded-xl bg-white/10 hover:bg-white/15 px-4 py-2.5 text-xs font-bold text-white inline-flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {busy === "portal" ? <Loader2 size={13} className="spinner" /> : <CreditCard size={13} />}
              Gestionar suscripción (tarjeta, factura, cancelar)
            </button>
          )}

          <p className="text-[11px] text-zinc-600 mt-4 leading-relaxed">
            {cloud
              ? "* Pagos procesados de forma segura por Stripe. Tu plan y créditos se validan en el servidor. Uso sujeto al saldo de créditos del plan."
              : "* Uso sujeto al saldo de créditos del plan. Modo demo activo: conecta Supabase y Stripe (ver SETUP.md) para activar cuentas y pagos reales."}
          </p>
          <button onClick={() => setView("new")} className="mt-4 text-xs font-semibold text-cyan-300 hover:text-cyan-200">
            → Usar mis créditos en una campaña nueva
          </button>
        </Card>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-zinc-500 text-xs">{k}</span>
      <span className="text-zinc-200 text-sm">{v}</span>
    </div>
  );
}
