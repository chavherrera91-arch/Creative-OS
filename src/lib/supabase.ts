import { createClient, type SupabaseClient } from "@supabase/supabase-js";

// Modo nube: se activa automáticamente cuando las variables de entorno están
// configuradas (ver SETUP.md). Sin ellas, la app funciona en modo demo local.
const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

export const cloudEnabled = Boolean(url && anonKey);

export const supabase: SupabaseClient | null = cloudEnabled ? createClient(url!, anonKey!) : null;

export interface ProfileRow {
  plan_id: "free" | "premium" | "max";
  credits: number;
  period: string;
  campaigns_this_month: number;
}
