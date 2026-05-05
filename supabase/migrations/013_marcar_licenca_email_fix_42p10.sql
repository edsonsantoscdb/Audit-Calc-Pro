-- Webhook Mercado Pago: erro Postgres 42P10 ("there is no unique constraint matching ON CONFLICT")
-- quando falta UNIQUE(email) ou índice exigido pelo ON CONFLICT.
-- Esta versão faz UPDATE por email normalizado + INSERT se não existir — não usa ON CONFLICT.

create or replace function public.marcar_licenca_paga_por_email(p_email text)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_email text := lower(trim(both from coalesce(p_email, '')));
begin
  if v_email = '' then
    raise exception 'email vazio';
  end if;

  update public.licencas l
  set
    tipo = 'pago',
    ativo = true,
    data_ativacao = coalesce(l.data_ativacao, now()),
    -- Instalações com chave NOT NULL: preencher se ainda vier nulo/vazio.
    chave = coalesce(nullif(trim(both from l.chave), ''), 'MP-' || upper(md5(v_email)))
  where lower(trim(both from coalesce(l.email, ''))) = v_email;

  if found then
    return;
  end if;

  insert into public.licencas (email, chave, tipo, usos_restantes, ativo, data_ativacao)
  values (v_email, 'MP-' || upper(md5(v_email)), 'pago', 0, true, now());
end;
$$;

comment on function public.marcar_licenca_paga_por_email(text) is
  'Marca tipo=pago por email normalizado (sem ON CONFLICT; evita 42P10 sem UNIQUE em email).';

revoke all on function public.marcar_licenca_paga_por_email(text) from public;
grant execute on function public.marcar_licenca_paga_por_email(text) to service_role;
