import Stripe from "stripe";
import { createClient } from "@supabase/supabase-js";

const PLAN_CREDITS: Record<string, number> = { free: 10, premium: 100, max: 500 };

function currentPeriod(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

// POST /api/webhook — endpoint de webhooks de Stripe.
// Eventos: checkout.session.completed, customer.subscription.updated,
//          customer.subscription.deleted
// La renovación mensual también llega como customer.subscription.updated,
// que recarga los créditos del plan.
export async function POST(request: Request): Promise<Response> {
  const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!);
  const supabase = createClient(process.env.SUPABASE_URL!, process.env.SUPABASE_SERVICE_ROLE_KEY!);

  const signature = request.headers.get("stripe-signature");
  const rawBody = await request.text();

  let event: Stripe.Event;
  try {
    event = await stripe.webhooks.constructEventAsync(rawBody, signature!, process.env.STRIPE_WEBHOOK_SECRET!);
  } catch (err) {
    return Response.json({ error: `Firma de webhook inválida: ${err instanceof Error ? err.message : "?"}` }, { status: 400 });
  }

  const setPlan = async (supabaseId: string, planId: "free" | "premium" | "max") => {
    await supabase
      .from("profiles")
      .update({
        plan_id: planId,
        credits: PLAN_CREDITS[planId],
        period: currentPeriod(),
        campaigns_this_month: 0,
      })
      .eq("id", supabaseId);
  };

  const planFromPrice = (priceId: string | undefined): "premium" | "max" | null =>
    priceId === process.env.STRIPE_PRICE_MAX ? "max" : priceId === process.env.STRIPE_PRICE_PREMIUM ? "premium" : null;

  switch (event.type) {
    // Pago inicial completado → activar el plan
    case "checkout.session.completed": {
      const session = event.data.object as Stripe.Checkout.Session;
      const supabaseId = session.metadata?.supabase_id;
      const plan = session.metadata?.plan as "premium" | "max" | undefined;
      if (supabaseId && (plan === "premium" || plan === "max")) {
        await setPlan(supabaseId, plan);
      }
      break;
    }

    // Cambio de suscripción (upgrade/downgrade desde el portal, impago, etc.)
    case "customer.subscription.updated": {
      const sub = event.data.object as Stripe.Subscription;
      const supabaseId = sub.metadata?.supabase_id;
      if (!supabaseId) break;
      if (sub.status === "active" || sub.status === "trialing") {
        const plan = planFromPrice(sub.items.data[0]?.price?.id);
        if (plan) await setPlan(supabaseId, plan);
      } else if (["canceled", "unpaid", "incomplete_expired"].includes(sub.status)) {
        await setPlan(supabaseId, "free");
      }
      break;
    }

    // Suscripción cancelada → volver al plan gratis
    case "customer.subscription.deleted": {
      const sub = event.data.object as Stripe.Subscription;
      const supabaseId = sub.metadata?.supabase_id;
      if (supabaseId) await setPlan(supabaseId, "free");
      break;
    }
  }

  return Response.json({ received: true });
}
