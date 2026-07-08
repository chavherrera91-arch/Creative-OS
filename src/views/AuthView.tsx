import React, { useState } from "react";
import { KeyRound, Loader2, LogIn, Mail, Sparkles, UserPlus } from "lucide-react";
import { useApp } from "../store";
import { Card, Field, inputCls } from "../components/ui";
import { supabase } from "../lib/supabase";

export default function AuthView() {
  const { setView } = useApp();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const sb = supabase;
  if (!sb) {
    return (
      <Card className="max-w-md mx-auto text-center py-10">
        <p className="text-sm text-zinc-400">
          El modo nube no está configurado todavía. Sigue la guía de <strong>SETUP.md</strong> para
          conectar Supabase y Stripe.
        </p>
      </Card>
    );
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setNotice("");
    setLoading(true);
    try {
      if (mode === "signup") {
        const { data, error } = await sb.auth.signUp({ email, password });
        if (error) throw error;
        if (data.user && !data.session) {
          setNotice("Cuenta creada. Revisa tu correo para confirmarla y luego inicia sesión.");
        } else {
          setView("plans");
        }
      } else {
        const { error } = await sb.auth.signInWithPassword({ email, password });
        if (error) throw error;
        setView("home");
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Error desconocido";
      setError(
        /invalid login credentials/i.test(msg) ? "Correo o contraseña incorrectos." :
        /already registered/i.test(msg) ? "Ese correo ya tiene cuenta — inicia sesión." :
        /at least 6/i.test(msg) ? "La contraseña debe tener al menos 6 caracteres." : msg
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fade-up max-w-md mx-auto">
      <div className="text-center mb-8">
        <div className="w-14 h-14 rounded-2xl grad-btn flex items-center justify-center mx-auto mb-4">
          <Sparkles size={24} className="text-white" />
        </div>
        <h1 className="text-2xl font-extrabold tracking-tight">
          {mode === "login" ? "Bienvenido de vuelta" : "Crea tu cuenta"}
        </h1>
        <p className="text-sm text-zinc-500 mt-1.5">
          {mode === "login"
            ? "Inicia sesión para acceder a tu plan y tus créditos."
            : "Empieza gratis: 1 campaña y 10 créditos al mes, sin tarjeta."}
        </p>
      </div>

      <Card>
        <form onSubmit={submit} className="space-y-4">
          <Field label="Correo electrónico">
            <div className="relative">
              <Mail size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-600" />
              <input
                type="email" required autoComplete="email"
                className={`${inputCls} pl-10`} placeholder="tu@correo.com"
                value={email} onChange={(e) => setEmail(e.target.value)}
              />
            </div>
          </Field>
          <Field label="Contraseña" hint={mode === "signup" ? "Mínimo 6 caracteres" : undefined}>
            <div className="relative">
              <KeyRound size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-600" />
              <input
                type="password" required minLength={6}
                autoComplete={mode === "signup" ? "new-password" : "current-password"}
                className={`${inputCls} pl-10`} placeholder="••••••••"
                value={password} onChange={(e) => setPassword(e.target.value)}
              />
            </div>
          </Field>

          {error && <p className="text-sm text-red-400">{error}</p>}
          {notice && <p className="text-sm text-emerald-400">{notice}</p>}

          <button
            type="submit" disabled={loading}
            className="grad-btn w-full rounded-xl px-5 py-3 font-bold text-white disabled:opacity-50 inline-flex items-center justify-center gap-2"
          >
            {loading ? <Loader2 size={15} className="spinner" /> : mode === "login" ? <LogIn size={15} /> : <UserPlus size={15} />}
            {mode === "login" ? "Iniciar sesión" : "Crear cuenta gratis"}
          </button>
        </form>

        <div className="text-center mt-5 text-xs text-zinc-500">
          {mode === "login" ? (
            <>¿No tienes cuenta?{" "}
              <button onClick={() => { setMode("signup"); setError(""); }} className="text-cyan-300 font-semibold hover:underline">
                Regístrate gratis
              </button>
            </>
          ) : (
            <>¿Ya tienes cuenta?{" "}
              <button onClick={() => { setMode("login"); setError(""); }} className="text-cyan-300 font-semibold hover:underline">
                Inicia sesión
              </button>
            </>
          )}
        </div>
      </Card>

      <p className="text-[11px] text-zinc-600 text-center mt-4 leading-relaxed">
        Tu plan y tus créditos se guardan de forma segura en tu cuenta y se validan en el servidor.
      </p>
    </div>
  );
}
