# 🔌 Activar cuentas y pagos reales (Supabase + Stripe)

El código de autenticación, base de datos y cobros **ya está integrado y desplegado**.
Solo falta conectar tus cuentas. Son ~15 minutos, en 3 pasos. Mientras no lo hagas,
la app sigue funcionando en modo demo (planes simulados en el navegador).

---

## Paso 1 — Supabase (usuarios + planes + créditos) · 5 min

1. Entra a [supabase.com](https://supabase.com) → **New project** (el plan gratuito sirve).
2. Cuando el proyecto esté listo, ve a **SQL Editor** → pega el contenido completo de
   [`supabase/schema.sql`](supabase/schema.sql) → **Run**. Esto crea la tabla de perfiles,
   los triggers y las funciones seguras de créditos.
3. Ve a **Authentication → Sign In / Up → Email** y desactiva *"Confirm email"*
   (opcional, pero simplifica el registro; si lo dejas activo también funciona).
4. Copia estas 3 claves desde **Project Settings → API**:
   - `Project URL` → será `VITE_SUPABASE_URL` y `SUPABASE_URL`
   - `anon public` key → será `VITE_SUPABASE_ANON_KEY`
   - `service_role` key → será `SUPABASE_SERVICE_ROLE_KEY` ⚠️ *secreta, nunca en el frontend*

## Paso 2 — Stripe (cobros) · 5 min

1. Entra a [dashboard.stripe.com](https://dashboard.stripe.com) (modo **Test** para probar).
2. **Product catalog → Add product**, crea dos productos con precio recurrente mensual:
   - `Creative OS Premium` — $10.00 USD / mes → copia su **Price ID** (`price_...`)
   - `Creative OS Max` — $20.00 USD / mes → copia su **Price ID** (`price_...`)
3. **Developers → API keys** → copia la **Secret key** (`sk_test_...` o `sk_live_...`).
4. **Developers → Webhooks → Add destination** (endpoint):
   - URL: `https://creative-os-weld.vercel.app/api/webhook`
   - Eventos: `checkout.session.completed`, `customer.subscription.updated`,
     `customer.subscription.deleted`
   - Copia el **Signing secret** (`whsec_...`).
5. (Para el botón "Gestionar suscripción") **Settings → Billing → Customer portal** → **Activate**.

## Paso 3 — Variables de entorno en Vercel · 5 min

En [vercel.com](https://vercel.com) → proyecto **creative-os** → **Settings → Environment Variables**,
agrega (entorno *Production*, y *Preview* si quieres):

| Variable | Valor |
|---|---|
| `VITE_SUPABASE_URL` | Project URL de Supabase |
| `VITE_SUPABASE_ANON_KEY` | anon public key |
| `SUPABASE_URL` | Project URL de Supabase (la misma) |
| `SUPABASE_SERVICE_ROLE_KEY` | service_role key |
| `STRIPE_SECRET_KEY` | Secret key de Stripe |
| `STRIPE_WEBHOOK_SECRET` | Signing secret del webhook |
| `STRIPE_PRICE_PREMIUM` | Price ID del producto Premium |
| `STRIPE_PRICE_MAX` | Price ID del producto Max |
| `SITE_URL` | `https://creative-os-weld.vercel.app` |

Después: **Deployments → ⋯ del último deploy → Redeploy** (para que tome las variables).

---

## ✅ Cómo verificar que funciona

1. Abre la web → debe aparecer **"Iniciar sesión"** en el sidebar (señal de que el modo nube está activo).
2. Crea una cuenta → en Supabase (**Table Editor → profiles**) aparecerá tu perfil con plan `free` y 10 créditos.
3. En **Planes y precios** pulsa "Pasar a Premium" → te llevará al Checkout real de Stripe.
   En modo Test paga con la tarjeta `4242 4242 4242 4242`, cualquier fecha futura y CVC.
4. Al volver, tu plan será Premium con 100 créditos (el webhook lo actualiza en segundos).
5. Genera una campaña → verás los créditos descontarse (validado en servidor: ni borrando
   el localStorage se puede hacer trampa).

## Cómo funciona por dentro

- **Frontend** (`src/lib/supabase.ts`, `src/views/AuthView.tsx`): registro/login con Supabase Auth.
  Si las variables `VITE_*` no existen, todo cae automáticamente al modo demo local.
- **Base de datos** (`supabase/schema.sql`): tabla `profiles` con RLS — los usuarios solo pueden
  *leer* su perfil. Los créditos se gastan únicamente vía la función `spend_credits()` (atómica,
  valida límites y renueva el mes en servidor).
- **Pagos** (`api/checkout.ts`, `api/webhook.ts`, `api/portal.ts`): funciones serverless en Vercel.
  El checkout crea la suscripción en Stripe; el webhook activa el plan en Supabase; el portal
  permite cambiar tarjeta o cancelar. La renovación mensual (`invoice.paid`) recarga los créditos.

## Pasar a producción real

Cuando quieras cobrar de verdad: activa tu cuenta de Stripe (datos fiscales y bancarios),
repite el Paso 2 en modo **Live** y reemplaza `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`
y los dos `STRIPE_PRICE_*` por sus versiones live. Nada más.
