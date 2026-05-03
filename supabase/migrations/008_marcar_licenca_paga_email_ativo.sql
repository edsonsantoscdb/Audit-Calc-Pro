-- Webhook Mercado Pago: marca licença paga por email.
-- Schema: estado "ativo" = coluna `ativo` (boolean); data de primeira confirmação de pagamento = `data_ativacao`.

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

  -- Localizar/atualizar pela unicidade em `email`; ativa licença (ativo = true) e marca timestamp.
  insert into public.licencas (email, tipo, usos_restantes, ativo, data_ativacao)
  values (v_email, 'pago', 0, true, now())
  on conflict (email) do update set
    tipo = 'pago',
    ativo = true,
    data_ativacao = now();

  -- Mantém comportamento anterior: não redefine usos_restantes, device_id/android_id nem trocas no conflito.
end;
$$;

comment on function public.marcar_licenca_paga_por_email(text) is
  'Upsert por email: tipo pago, ativo=true, data_ativacao atualizada ao confirmar pagamento.';
