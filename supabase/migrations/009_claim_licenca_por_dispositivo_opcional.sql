-- Garantir RPC opcional para fluxo por chave + pending_android_id (apps antigos ou deploy sem 007 completo).

alter table public.licencas add column if not exists chave text;
alter table public.licencas add column if not exists android_id text;
alter table public.licencas add column if not exists expira_em timestamptz;
alter table public.licencas add column if not exists data_ativacao timestamptz;
alter table public.licencas add column if not exists pending_android_id text;

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
  'Opcional: primeira vez quando existe pending_android_id; fluxo principal de MP é por e-mail (validar_acesso).';

grant execute on function public.claim_licenca_por_dispositivo(text) to anon;
grant execute on function public.claim_licenca_por_dispositivo(text) to authenticated;
