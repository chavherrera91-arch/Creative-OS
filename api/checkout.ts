import Stripe from "stripe";
import { createClient } from "@supabase/supabase-js";

// POST /api/checkout  { plan: "premium" | "max" }
// Requiere: Authorization: Bearer <token de sesión de Supabase>
// Devuelve: { url } — URL de Stripe Checkout para completar la suscripción.
export async function POST(request: Request): Promise<Response> {
  const missing = ["STRIPE_SECRET_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"].filter((k) => !process.env[k]);
  if (missing.length) {
    return Response.json({ error: `Faltan variables de entorno: ${missing.join(", ")}` }, { status: 500 });
  }

  const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!);
  const supabase = createClient(process.env.SUPABASE_URL!, process.env.SUPABASE_SERVICE_ROLE_KEY!);

  // Autenticar al usuario con su token de Supabase
  const token = (request.headers.get("authorization") ?? "").replace(/^Bearer\s+/i, "");
  const { data: userData, error: authError } = await supabase.auth.getUser(token);
  const user = userData?.user;
  if (authError || !user) {
    return Response.json({ error: "No autenticado" }, { status: 401 });
  }

  const { plan } = (await request.json()) as { plan?: string };
  const priceId = plan === "max" ? process.env.STRIPE_PRICE_MAX : plan === "premium" ? process.env.STRIPE_PRICE_PREMIUM : null;
  if (!priceId) {
    return Response.json({ error: "Plan inválido o precio no configurado (STRIPE_PRICE_PREMIUM / STRIPE_PRICE_MAX)" }, { status: 400 });
  }

  // Reutilizar el cliente de Stripe si ya existe
  const { data: profile } = await supabase.from("profiles").select("stripe_customer_id").eq("id", user.id).single();
  let customerId = profile?.stripe_customer_id as string | null;
  if (!customerId) {
    const customer = await stripe.customers.create({
      email: user.email ?? undefined,
      metadata: { supabase_id: user.id },
    });
    customerId = customer.id;
    await supabase.from("profiles").update({ stripe_customer_id: customerId }).eq("id", user.id);
  }

  const site = process.env.SITE_URL ?? new URL(request.url).origin;
  const session = await stripe.checkout.sessions.create({
    customer: customerId,
    mode: "subscription",
    line_items: [{ price: priceId, quantity: 1 }],
    success_url: `${site}/?checkout=success`,
    cancel_url: `${site}/?checkout=cancel`,
    metadata: { supabase_id: user.id, plan: plan! },
    subscription_data: { metadata: { supabase_id: user.id, plan: plan! } },
    allow_promotion_codes: true,
  });

  return Response.json({ url: session.url });
}
