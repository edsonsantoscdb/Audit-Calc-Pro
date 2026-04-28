-- Chamada pelo webhook Mercado Pago (service role) para activar licença paga sem duplicar email.

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

  insert into public.licencas (email, tipo, usos_restantes, ativo)
  values (v_email, 'pago', 0, true)
  on conflict (email) do update set
    tipo = 'pago',
    ativo = true;
  -- em conflito não altera usos_restantes, device_id, trocas, etc.
end;
$$;

comment on function public.marcar_licenca_paga_por_email(text) is
  'Upsert atómico: novo registo com usos_restantes=0; existente só tipo+ativo.';

revoke all on function public.marcar_licenca_paga_por_email(text) from public;
grant execute on function public.marcar_licenca_paga_por_email(text) to service_role;
