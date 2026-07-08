import React, { createContext, useContext, useEffect, useState } from "react";
import type { Campaign, ModuleId, Settings } from "./types";
import {
  Account, CREDIT_COSTS, CreditAction, PlanId, SpendCheck,
  canSpend, freshAccount, getPlan, planIncludes, rolloverIfNeeded,
} from "./plans";

type View = ModuleId | "home" | "new" | "settings" | "plans";

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
  spend: (action: CreditAction) => boolean;
  changePlan: (planId: PlanId) => void;
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

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [campaigns, setCampaigns] = useState<Campaign[]>(() => load(LS_CAMPAIGNS, [] as Campaign[]));
  const [activeId, setActiveId] = useState<string | null>(null);
  const [view, setView] = useState<View>("home");
  const [settings, setSettingsState] = useState<Settings>(() =>
    load(LS_SETTINGS, { apiKey: "", model: "claude-opus-4-8", useClaude: false })
  );
  const [account, setAccount] = useState<Account>(() => rolloverIfNeeded(load(LS_ACCOUNT, freshAccount())));

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
    localStorage.setItem(LS_ACCOUNT, JSON.stringify(account));
  }, [account]);

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
    spend: (action) => {
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
      // Al cambiar de plan se otorga la asignación completa del nuevo plan
      setAccount((prev) => ({
        ...rolloverIfNeeded(prev),
        planId,
        credits: getPlan(planId).credits,
      }));
    },
  };

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
