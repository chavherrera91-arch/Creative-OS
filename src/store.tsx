import React, { createContext, useContext, useEffect, useState } from "react";
import type { Campaign, ModuleId, Settings } from "./types";
import {
  Account, CREDIT_COSTS, CreditAction, PlanId, SpendCheck,
  canSpend, freshAccount, getPlan, planIncludes, rolloverIfNeeded,
} from "./plans";
import { cloudEnabled, supabase, type ProfileRow } from "./lib/supabase";

type View = ModuleId | "home" | "new" | "settings" | "plans" | "auth";

export interface CloudUser {
  id: string;
  email: string;
}

interface AppState {
  campaigns: Campaign[];
  activeId: string | null;
  view: View;
  settings: Settings;
  account: Account;
  setView: (v: View) => void;
  setActive: (id: string | null) => void;
  addCampaign: (c: Campaign) => void;
  updateCampaign: (c: Campaign) => void;
  deleteCampaign: (id: string) => void;
  setSettings: (s: Settings) => void;
  active: Campaign | null;
  // Suscripción y créditos
  hasModule: (id: ModuleId) => boolean;
  checkSpend: (action: CreditAction) => SpendCheck;
  spend: (action: CreditAction) => Promise<boolean>;
  changePlan: (planId: PlanId) => void;
  // Cuenta en la nube (Supabase) — null si el modo nube no está configurado o no hay sesión
  cloud: boolean;
  user: CloudUser | null;
  refreshAccount: () => Promise<void>;
  signOut: () => Promise<void>;
}

const Ctx = createContext<AppState>(null as unknown as AppState);
export const useApp = () => useContext(Ctx);

const LS_CAMPAIGNS = "creativeos.campaigns.v1";
const LS_SETTINGS = "creativeos.settings.v1";
const LS_ACCOUNT = "creativeos.account.v1";

function load<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function accountFromProfile(p: ProfileRow): Account {
  return {
    planId: p.plan_id,
    credits: p.credits,
    period: p.period,
    campaignsThisMonth: p.campaigns_this_month,
  };
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [campaigns, setCampaigns] = useState<Campaign[]>(() => load(LS_CAMPAIGNS, [] as Campaign[]));
  const [activeId, setActiveId] = useState<string | null>(null);
  const [view, setView] = useState<View>("home");
  const [settings, setSettingsState] = useState<Settings>(() =>
    load(LS_SETTINGS, { apiKey: "", model: "claude-opus-4-8", useClaude: false })
  );
  const [account, setAccount] = useState<Account>(() => rolloverIfNeeded(load(LS_ACCOUNT, freshAccount())));
  const [user, setUser] = useState<CloudUser | null>(null);

  useEffect(() => {
    try {
      // Guardar solo las últimas 12 campañas para no desbordar localStorage
      localStorage.setItem(LS_CAMPAIGNS, JSON.stringify(campaigns.slice(0, 12)));
    } catch {
      /* localStorage lleno: se ignora, la sesión sigue en memoria */
    }
  }, [campaigns]);

  useEffect(() => {
    localStorage.setItem(LS_SETTINGS, JSON.stringify(settings));
  }, [settings]);

  useEffect(() => {
    // La cuenta local solo se persiste en modo demo (sin sesión en la nube)
    if (!user) localStorage.setItem(LS_ACCOUNT, JSON.stringify(account));
  }, [account, user]);

  const refreshAccount = async () => {
    if (!supabase) return;
    const { data, error } = await supabase.rpc("current_profile");
    if (!error && data) setAccount(accountFromProfile(data as ProfileRow));
  };

  // Sesión de Supabase: escuchar login/logout y cargar el perfil real
  useEffect(() => {
    if (!supabase) return;

    const applySession = (sessionUser: { id: string; email?: string } | null) => {
      if (sessionUser) {
        setUser({ id: sessionUser.id, email: sessionUser.email ?? "" });
        void refreshAccount();
      } else {
        setUser(null);
        setAccount(rolloverIfNeeded(load(LS_ACCOUNT, freshAccount())));
      }
    };

    supabase.auth.getSession().then(({ data }) => applySession(data.session?.user ?? null));
    const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => {
      applySession(session?.user ?? null);
    });

    // Al volver de Stripe Checkout: refrescar el plan y mostrar la página de planes
    const params = new URLSearchParams(window.location.search);
    if (params.has("checkout") || params.has("portal")) {
      window.history.replaceState({}, "", window.location.pathname);
      setView("plans");
      // El webhook puede tardar 1-3s en actualizar el perfil: reintentar
      let tries = 0;
      const interval = setInterval(() => {
        void refreshAccount();
        if (++tries >= 5) clearInterval(interval);
      }, 2000);
    }

    return () => sub.subscription.unsubscribe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const value: AppState = {
    campaigns,
    activeId,
    view,
    settings,
    account,
    setView,
    setActive: setActiveId,
    addCampaign: (c) => {
      setCampaigns((prev) => [c, ...prev]);
      setActiveId(c.id);
    },
    updateCampaign: (c) => setCampaigns((prev) => prev.map((x) => (x.id === c.id ? c : x))),
    deleteCampaign: (id) => {
      setCampaigns((prev) => prev.filter((x) => x.id !== id));
      setActiveId((cur) => (cur === id ? null : cur));
    },
    setSettings: setSettingsState,
    active: campaigns.find((c) => c.id === activeId) ?? null,

    hasModule: (id) => planIncludes(account.planId, id),
    checkSpend: (action) => canSpend(rolloverIfNeeded(account), action),

    spend: async (action) => {
      // Modo nube: el servidor valida y descuenta (imposible de falsear)
      if (supabase && user) {
        const { data, error } = await supabase.rpc("spend_credits", { action });
        if (error || !data?.ok) {
          if (data) setAccount(accountFromProfile(data as ProfileRow));
          return false;
        }
        setAccount(accountFromProfile(data as ProfileRow));
        return true;
      }
      // Modo demo local
      const acc = rolloverIfNeeded(account);
      const check = canSpend(acc, action);
      if (!check.ok) return false;
      setAccount({
        ...acc,
        credits: acc.credits - CREDIT_COSTS[action],
        campaignsThisMonth: action === "campaign" ? acc.campaignsThisMonth + 1 : acc.campaignsThisMonth,
      });
      return true;
    },

    changePlan: (planId) => {
      // Solo modo demo: en modo nube los planes cambian vía Stripe (webhook)
      if (user) return;
      setAccount((prev) => ({
        ...rolloverIfNeeded(prev),
        planId,
        credits: getPlan(planId).credits,
      }));
    },

    cloud: cloudEnabled,
    user,
    refreshAccount,
    signOut: async () => {
      if (supabase) await supabase.auth.signOut();
    },
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
