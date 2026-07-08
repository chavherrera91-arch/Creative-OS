import Stripe from "stripe";
import { createClient } from "@supabase/supabase-js";

// POST /api/portal — abre el portal de facturación de Stripe
// (cambiar de plan, actualizar tarjeta, cancelar suscripción).
// Requiere: Authorization: Bearer <token de sesión de Supabase>
export async function POST(request: Request): Promise<Response> {
  const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!);
  const supabase = createClient(process.env.SUPABASE_URL!, process.env.SUPABASE_SERVICE_ROLE_KEY!);

  const token = (request.headers.get("authorization") ?? "").replace(/^Bearer\s+/i, "");
  const { data: userData, error: authError } = await supabase.auth.getUser(token);
  const user = userData?.user;
  if (authError || !user) {
    return Response.json({ error: "No autenticado" }, { status: 401 });
  }

  const { data: profile } = await supabase.from("profiles").select("stripe_customer_id").eq("id", user.id).single();
  if (!profile?.stripe_customer_id) {
    return Response.json({ error: "No tienes una suscripción activa todavía" }, { status: 400 });
  }

  const site = process.env.SITE_URL ?? new URL(request.url).origin;
  const session = await stripe.billingPortal.sessions.create({
    customer: profile.stripe_customer_id,
    return_url: `${site}/?portal=return`,
  });

  return Response.json({ url: session.url });
}
