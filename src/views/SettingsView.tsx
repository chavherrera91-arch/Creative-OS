import React, { useState } from "react";
import { CheckCircle2, KeyRound, Loader2, XCircle } from "lucide-react";
import { useApp } from "../store";
import { Card, Field, inputCls, SectionHeader } from "../components/ui";
import { testApiKey } from "../engine/claude";

export default function SettingsView() {
  const { settings, setSettings } = useApp();
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<"ok" | "fail" | null>(null);
  const [testMsg, setTestMsg] = useState("");

  const test = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      await testApiKey(settings);
      setTestResult("ok");
      setTestMsg("Conexión correcta: la API de Claude responde.");
    } catch (e) {
      setTestResult("fail");
      setTestMsg(e instanceof Error ? e.message : "Error de conexión");
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="fade-up max-w-2xl mx-auto">
      <SectionHeader
        title="Configuración"
        subtitle="Creative OS funciona al 100% con su motor local. Conecta tu API key de Anthropic para que Claude genere la estrategia con conocimiento real del producto."
      />

      <Card className="space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-bold text-sm">Generación con Claude</div>
            <div className="text-xs text-zinc-500 mt-0.5">Inteligencia de producto, hooks, objeciones, landing y UGC generados por IA real</div>
          </div>
          <button
            onClick={() => setSettings({ ...settings, useClaude: !settings.useClaude })}
            className={`w-11 h-6 rounded-full transition-colors relative ${settings.useClaude ? "bg-violet-500" : "bg-zinc-700"}`}
          >
            <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition-all ${settings.useClaude ? "left-[22px]" : "left-0.5"}`} />
          </button>
        </div>

        <Field label="API Key de Anthropic" hint="Se guarda solo en tu navegador (localStorage). Consíguela en console.anthropic.com">
          <div className="relative">
            <KeyRound size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-600" />
            <input
              type="password"
              className={`${inputCls} pl-10`}
              placeholder="sk-ant-…"
              value={settings.apiKey}
              onChange={(e) => setSettings({ ...settings, apiKey: e.target.value })}
            />
          </div>
        </Field>

        <Field label="Modelo">
          <select
            className={inputCls}
            value={settings.model}
            onChange={(e) => setSettings({ ...settings, model: e.target.value })}
          >
            <option value="claude-opus-4-8">Claude Opus 4.8 — máxima calidad (recomendado)</option>
            <option value="claude-sonnet-5">Claude Sonnet 5 — rápido y muy capaz</option>
            <option value="claude-haiku-4-5">Claude Haiku 4.5 — el más económico</option>
          </select>
        </Field>

        <div className="flex items-center gap-3">
          <button
            onClick={test}
            disabled={!settings.apiKey || testing}
            className="grad-btn rounded-xl px-5 py-2.5 text-sm font-bold text-white disabled:opacity-40 inline-flex items-center gap-2"
          >
            {testing && <Loader2 size={14} className="spinner" />} Probar conexión
          </button>
          {testResult === "ok" && (
            <span className="text-sm text-emerald-400 inline-flex items-center gap-1.5"><CheckCircle2 size={15} /> {testMsg}</span>
          )}
          {testResult === "fail" && (
            <span className="text-sm text-red-400 inline-flex items-center gap-1.5"><XCircle size={15} /> {testMsg}</span>
          )}
        </div>
      </Card>

      <Card className="mt-5 text-xs text-zinc-500 leading-relaxed">
        <strong className="text-zinc-300">Cómo funciona:</strong> el motor local genera la campaña completa al instante con
        una base de conocimiento de marketing por categoría de producto. Si activas Claude, la parte estratégica
        (problema, ángulos, objeciones, hooks, landing y guiones UGC) se regenera con IA usando el nombre, la descripción
        y la URL reales de tu producto — el resto de módulos se adaptan automáticamente a esa estrategia.
      </Card>
    </div>
  );
}
