-- ============================================================
-- Creative OS — Esquema de Supabase
-- Pega este archivo completo en: Supabase → SQL Editor → Run
-- ============================================================

-- Perfil de usuario: plan, créditos y contadores del mes.
-- La fuente de verdad de la suscripción vive aquí, no en el navegador.
create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  email text,
  plan_id text not null default 'free' check (plan_id in ('free', 'premium', 'max')),
  credits int not null default 10,
  period text not null default to_char(now(), 'YYYY-MM'),
  campaigns_this_month int not null default 0,
  stripe_customer_id text,
  created_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

-- Los usuarios solo pueden LEER su propio perfil.
-- Nadie puede escribir directamente: todo cambio pasa por las funciones
-- de abajo (security definer) o por el webhook de Stripe (service role).
drop policy if exists "own profile read" on public.profiles;
create policy "own profile read"
  on public.profiles for select
  using (auth.uid() = id);

-- Crear el perfil automáticamente al registrarse
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email) values (new.id, new.email)
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Configuración de planes (misma tabla de precios que el frontend)
create or replace function public.plan_credits(p text)
returns int language sql immutable as $$
  select case p when 'premium' then 100 when 'max' then 500 else 10 end;
$$;

create or replace function public.plan_campaign_limit(p text)
returns int language sql immutable as $$
  select case p when 'premium' then 10 when 'max' then 50 else 1 end;
$$;

create or replace function public.action_cost(a text)
returns int language sql immutable as $$
  select case a when 'campaign' then 10 when 'competitor' then 5 when 'iteration' then 5 else null end;
$$;

-- Devuelve el perfil del usuario, renovando créditos si empezó un mes nuevo
create or replace function public.current_profile()
returns json
language plpgsql
security definer
set search_path = public
as $$
declare
  prof profiles;
begin
  select * into prof from profiles where id = auth.uid() for update;
  if prof.id is null then
    return null;
  end if;

  if prof.period <> to_char(now(), 'YYYY-MM') then
    update profiles
      set period = to_char(now(), 'YYYY-MM'),
          credits = plan_credits(prof.plan_id),
          campaigns_this_month = 0
      where id = prof.id
      returning * into prof;
  end if;

  return json_build_object(
    'plan_id', prof.plan_id,
    'credits', prof.credits,
    'period', prof.period,
    'campaigns_this_month', prof.campaigns_this_month
  );
end;
$$;

-- Gasta créditos de forma atómica y validada en servidor.
-- El cliente NO puede saltarse límites: esta función es la única vía.
create or replace function public.spend_credits(action text)
returns json
language plpgsql
security definer
set search_path = public
as $$
declare
  prof profiles;
  cost int;
begin
  cost := action_cost(action);
  if cost is null then
    return json_build_object('ok', false, 'reason', 'bad_action');
  end if;

  select * into prof from profiles where id = auth.uid() for update;
  if prof.id is null then
    return json_build_object('ok', false, 'reason', 'no_profile');
  end if;

  -- Renovación mensual
  if prof.period <> to_char(now(), 'YYYY-MM') then
    prof.period := to_char(now(), 'YYYY-MM');
    prof.credits := plan_credits(prof.plan_id);
    prof.campaigns_this_month := 0;
  end if;

  -- Límite de campañas del plan
  if action = 'campaign' and prof.campaigns_this_month >= plan_campaign_limit(prof.plan_id) then
    update profiles set period = prof.period, credits = prof.credits,
      campaigns_this_month = prof.campaigns_this_month where id = prof.id;
    return json_build_object('ok', false, 'reason', 'limit',
      'credits', prof.credits, 'campaigns_this_month', prof.campaigns_this_month,
      'plan_id', prof.plan_id, 'period', prof.period);
  end if;

  -- Saldo de créditos
  if prof.credits < cost then
    update profiles set period = prof.period, credits = prof.credits,
      campaigns_this_month = prof.campaigns_this_month where id = prof.id;
    return json_build_object('ok', false, 'reason', 'credits',
      'credits', prof.credits, 'campaigns_this_month', prof.campaigns_this_month,
      'plan_id', prof.plan_id, 'period', prof.period);
  end if;

  update profiles
    set credits = prof.credits - cost,
        period = prof.period,
        campaigns_this_month = prof.campaigns_this_month + (case when action = 'campaign' then 1 else 0 end)
    where id = prof.id
    returning * into prof;

  return json_build_object('ok', true, 'reason', '',
    'credits', prof.credits, 'campaigns_this_month', prof.campaigns_this_month,
    'plan_id', prof.plan_id, 'period', prof.period);
end;
$$;

-- Permisos: solo usuarios autenticados pueden llamar a las RPCs
revoke all on function public.spend_credits(text) from anon, public;
revoke all on function public.current_profile() from anon, public;
grant execute on function public.spend_credits(text) to authenticated;
grant execute on function public.current_profile() to authenticated;
