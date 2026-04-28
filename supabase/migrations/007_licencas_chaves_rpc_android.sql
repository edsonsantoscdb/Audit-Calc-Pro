-- Completa o schema para licença por CHAVE + Android (mobile_flet/supabase_license.py)
-- e alinha admin/gerador (created_at). Compatível com 001–006 (e-mail / trial).

-- --- Colunas usadas pela app e pelo gerador ---
alter table public.licencas add column if not exists chave text;
alter table public.licencas add column if not exists comprador text;
alter table public.licencas add column if not exists android_id text;
alter table public.licencas add column if not exists pending_android_id text;
alter table public.licencas add column if not exists data_ativacao timestamptz;
alter table public.licencas add column if not exists expira_em timestamptz;
alter table public.licencas add column if not exists created_at timestamptz;

-- Linhas só com chave (sem e-mail ao criar pelo script) são permitidas
do $$
begin
  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'licencas' and column_name = 'email'
      and is_nullable = 'NO'
  ) then
    alter table public.licencas alter column email drop not null;
  end if;
end $$;

-- Índice único em chave quando preenchida (várias linhas sem chave = trial/e-mail)
create unique index if not exists licencas_chave_unique_not_null
  on public.licencas (upper(trim(chave)))
  where chave is not null and trim(chave) <> '';

-- created_at para listagens (admin ordena por created_at)
do $$
begin
  if exists (
    select 1 from information_schema.columns c
    where c.table_schema = 'public'
      and c.table_name = 'licencas'
      and c.column_name = 'criado_em'
  ) then
    update public.licencas l
    set created_at = l.criado_em
    where l.created_at is null and l.criado_em is not null;
  end if;
end $$;

update public.licencas set created_at = now() where created_at is null;

-- --- RPCs: leitura por chave e vínculo Android (anon só via função) ---
create or replace function public.get_licenca_por_chave(p_chave text)
returns setof public.licencas
language sql
security definer
set search_path = public
as $$
  select *
  from public.licencas
  where upper(trim(chave)) = upper(trim(p_chave))
  limit 1;
$$;

create or replace function public.vincular_android_licenca(
  p_chave text,
  p_android_id text,
  p_anterior text default null
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  update public.licencas l
  set
    android_id = nullif(trim(p_android_id), ''),
    data_ativacao = now()
  where upper(trim(l.chave)) = upper(trim(p_chave))
    and l.ativo = true
    and (l.expira_em is null or l.expira_em > now())
    and (
      l.android_id is null
      or l.android_id = nullif(trim(p_android_id), '')
      or (
        p_anterior is not null
        and trim(p_anterior) <> ''
        and l.android_id = trim(p_anterior)
      )
    );
end;
$$;

comment on function public.get_licenca_por_chave(text) is
  'Cliente anon: uma linha da licença pela chave (para ativação e revalidação).';
comment on function public.vincular_android_licenca(text, text, text) is
  'Cliente anon: grava android_id quando a chave é válida e regras de dispositivo.';

grant execute on function public.get_licenca_por_chave(text) to anon;
grant execute on function public.get_licenca_por_chave(text) to authenticated;
grant execute on function public.vincular_android_licenca(text, text, text) to anon;
grant execute on function public.vincular_android_licenca(text, text, text) to authenticated;

-- --- Claim pós Mercado Pago: libertar chave quando pending_android_id bate ---
create or replace function public.claim_licenca_por_dispositivo(p_android_id text)
returns table (chave text, expira_em timestamptz)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_chave text;
  v_exp timestamptz;
begin
  if p_android_id is null or trim(p_android_id) = '' then
    return;
  end if;

  select l.chave, l.expira_em into v_chave, v_exp
  from public.licencas l
  where l.ativo = true
    and (l.android_id is null or trim(l.android_id) = '')
    and l.pending_android_id is not null
    and trim(l.pending_android_id) = trim(p_android_id)
  limit 1
  for update;

  if v_chave is null then
    return;
  end if;

  update public.licencas u
  set android_id = trim(p_android_id),
      pending_android_id = null,
      data_ativacao = coalesce(u.data_ativacao, now())
  where upper(trim(u.chave)) = upper(trim(v_chave));

  return query select v_chave, v_exp;
end;
$$;

comment on function public.claim_licenca_por_dispositivo(text) is
  'Primeira vez após webhook: transfere pending_android_id → android_id e devolve chave.';
grant execute on function public.claim_licenca_por_dispositivo(text) to anon;
grant execute on function public.claim_licenca_por_dispositivo(text) to authenticated;

-- --- RLS: anon não faz SELECT direto na tabela; apenas RPC ---
alter table public.licencas enable row level security;
