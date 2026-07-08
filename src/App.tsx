import React from "react";
import {
  BookOpen, Brain, Clapperboard, Crown, FileText, FlaskConical, Gauge, Gift,
  Home, Image, LayoutDashboard, Layers, Lightbulb, Lock, Megaphone, Package,
  Rocket, ScanSearch, Settings as SettingsIcon, Sparkles, SwatchBook, Target, TrendingUp,
  UserRound, Video, Wand2, Zap, type LucideIcon,
} from "lucide-react";
import { useApp, AppProvider } from "./store";
import { MODULES, ModuleId } from "./types";
import { getPlan } from "./plans";
import HomeView from "./views/HomeView";
import NewCampaignView from "./views/NewCampaignView";
import SettingsView from "./views/SettingsView";
import PlansView from "./views/PlansView";
import LockedModule from "./components/LockedModule";
import { OverviewView, IntelligenceView, ScoreView, ViralView, CompetitorView } from "./views/AnalysisViews";
import { HooksView, AdsView, ScriptsView, VisualView, ImagePromptsView, VideoPromptsView, UgcView, ThumbnailsView } from "./views/GenerationViews";
import { LandingView, OffersView, PlannerView, AbTestingView, IterationView, LibraryView, ExportView } from "./views/StrategyViews";

const ICONS: Record<string, LucideIcon> = {
  overview: LayoutDashboard,
  intelligence: Brain,
  score: Gauge,
  viral: TrendingUp,
  competitor: ScanSearch,
  hooks: Zap,
  ads: Megaphone,
  scripts: FileText,
  visual: Clapperboard,
  imageprompts: Image,
  videoprompts: Video,
  ugc: UserRound,
  thumbnails: SwatchBook,
  landing: Layers,
  offers: Gift,
  planner: Target,
  abtesting: FlaskConical,
  iteration: Wand2,
  library: BookOpen,
  export: Package,
};

function ModuleContent({ id }: { id: ModuleId }) {
  const { hasModule } = useApp();
  if (!hasModule(id)) return <LockedModule moduleId={id} />;
  switch (id) {
    case "overview": return <OverviewView />;
    case "intelligence": return <IntelligenceView />;
    case "score": return <ScoreView />;
    case "viral": return <ViralView />;
    case "competitor": return <CompetitorView />;
    case "hooks": return <HooksView />;
    case "ads": return <AdsView />;
    case "scripts": return <ScriptsView />;
    case "visual": return <VisualView />;
    case "imageprompts": return <ImagePromptsView />;
    case "videoprompts": return <VideoPromptsView />;
    case "ugc": return <UgcView />;
    case "thumbnails": return <ThumbnailsView />;
    case "landing": return <LandingView />;
    case "offers": return <OffersView />;
    case "planner": return <PlannerView />;
    case "abtesting": return <AbTestingView />;
    case "iteration": return <IterationView />;
    case "library": return <LibraryView />;
    case "export": return <ExportView />;
  }
}

function CreditsWidget() {
  const { account, setView } = useApp();
  const plan = getPlan(account.planId);
  const pct = Math.max(0, Math.min(100, (account.credits / plan.credits) * 100));
  const low = account.credits < 10;
  return (
    <button
      onClick={() => setView("plans")}
      className="w-full text-left rounded-xl bg-white/[0.03] border border-white/10 hover:border-violet-500/40 transition-colors p-3 mb-2"
      title="Ver planes y créditos"
    >
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">Plan {plan.name}</span>
        <span className={`text-xs font-bold ${low ? "text-amber-300" : "text-zinc-300"}`}>
          ⚡ {account.credits}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{ width: `${pct}%`, background: low ? "#fbbf24" : "linear-gradient(90deg,#7c3aed,#22d3ee)", transition: "width 0.5s ease" }}
        />
      </div>
      <div className="text-[10px] text-zinc-600 mt-1.5">
        {account.credits} de {plan.credits} créditos · {account.campaignsThisMonth}/{plan.campaignLimit} campañas
      </div>
    </button>
  );
}

function Shell() {
  const { view, setView, active, campaigns, setActive, hasModule } = useApp();
  const groups = ["Campaña", "Análisis", "Generación", "Conversión", "Estrategia"];

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <aside className="w-64 shrink-0 border-r border-white/5 flex flex-col bg-[#0b0b12]">
        <button onClick={() => setView("home")} className="flex items-center gap-2.5 px-5 h-16 border-b border-white/5 text-left">
          <div className="w-8 h-8 rounded-lg grad-btn flex items-center justify-center">
            <Sparkles size={16} className="text-white" />
          </div>
          <div>
            <div className="font-extrabold tracking-tight leading-none">Creative OS</div>
            <div className="text-[10px] text-zinc-500 font-medium mt-0.5">AI Campaign Orchestrator</div>
          </div>
        </button>

        <div className="flex-1 overflow-y-auto py-4 px-3">
          <NavBtn active={view === "home"} onClick={() => setView("home")} icon={Home} label="Inicio" />
          <NavBtn active={view === "new"} onClick={() => setView("new")} icon={Rocket} label="Nueva campaña" accent />
          <NavBtn active={view === "plans"} onClick={() => setView("plans")} icon={Crown} label="Planes y precios" />

          {active ? (
            <>
              <div className="mt-5 mb-2 px-2">
                <select
                  value={active.id}
                  onChange={(e) => setActive(e.target.value)}
                  className="w-full text-xs bg-white/[0.04] border border-white/10 rounded-lg px-2 py-1.5 text-zinc-300 outline-none"
                >
                  {campaigns.map((c) => (
                    <option key={c.id} value={c.id}>{c.input.name.slice(0, 32)}</option>
                  ))}
                </select>
              </div>
              {groups.map((g) => {
                const mods = MODULES.filter((m) => m.group === g);
                if (!mods.length) return null;
                return (
                  <div key={g} className="mt-4">
                    <div className="px-2 mb-1 text-[10px] font-bold uppercase tracking-widest text-zinc-600">{g}</div>
                    {mods.map((m) => (
                      <NavBtn
                        key={m.id}
                        active={view === m.id}
                        onClick={() => setView(m.id)}
                        icon={ICONS[m.id] ?? Lightbulb}
                        label={m.name}
                        locked={!hasModule(m.id)}
                      />
                    ))}
                  </div>
                );
              })}
            </>
          ) : (
            <div className="mt-6 px-3 py-4 rounded-xl bg-white/[0.03] border border-white/5 text-xs text-zinc-500 leading-relaxed">
              Crea o selecciona una campaña para desbloquear los 18 módulos de generación creativa.
            </div>
          )}
        </div>

        <div className="p-3 border-t border-white/5">
          <CreditsWidget />
          <NavBtn active={view === "settings"} onClick={() => setView("settings")} icon={SettingsIcon} label="Configuración" />
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-6xl mx-auto px-8 py-8">
          {view === "home" && <HomeView />}
          {view === "new" && <NewCampaignView />}
          {view === "settings" && <SettingsView />}
          {view === "plans" && <PlansView />}
          {view !== "home" && view !== "new" && view !== "settings" && view !== "plans" && (
            active ? <div className="fade-up" key={view + active.id}><ModuleContent id={view} /></div> : <HomeView />
          )}
        </div>
      </main>
    </div>
  );
}

function NavBtn({ active, onClick, icon: Icon, label, accent, locked }: {
  active: boolean; onClick: () => void;
  icon: LucideIcon;
  label: string; accent?: boolean; locked?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-2.5 px-2.5 py-[7px] rounded-lg text-[13px] font-medium transition-colors mb-0.5 text-left
        ${active ? "bg-violet-500/15 text-violet-200" : accent ? "text-cyan-300 hover:bg-white/5" : locked ? "text-zinc-600 hover:text-zinc-400 hover:bg-white/5" : "text-zinc-400 hover:text-zinc-200 hover:bg-white/5"}`}
    >
      <Icon size={15} className={active ? "text-violet-300" : ""} />
      <span className="truncate flex-1">{label}</span>
      {locked && <Lock size={11} className="text-zinc-700 shrink-0" />}
    </button>
  );
}

export default function App() {
  return (
    <AppProvider>
      <Shell />
    </AppProvider>
  );
}
