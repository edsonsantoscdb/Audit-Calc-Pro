-- RPC: registar consumo de uma auditoria gratuita (tipo teste) ou autorizar uso (tipo pago).
-- Espera unicidade em public.licencas(email) — ver 001/002.

create or replace function public.consumir_auditoria(p_email text)
returns table (
  status text,
  usos_restantes integer
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_email text := lower(trim(both from coalesce(p_email, '')));
  r public.licencas%rowtype;
  novo integer;
begin
  -- entrada inválida
  if v_email = '' then
    status := 'bloqueado';
    usos_restantes := 0;
    return next;
    return;
  end if;

  -- garantir uma linha para o email (sem erro se já existir)
  insert into public.licencas (email, tipo, usos_restantes, ativo)
  values (v_email, 'teste', 5, true)
  on conflict (email) do nothing;

  select *
  into r
  from public.licencas
  where licencas.email = v_email
  for update;

  if not found then
    status := 'bloqueado';
    usos_restantes := 0;
    return next;
    return;
  end if;

  if not r.ativo then
    status := 'bloqueado';
    usos_restantes := greatest(r.usos_restantes, 0);
    return next;
    return;
  end if;

  -- pago: não decrementa; “uso ilimitado”
  if r.tipo = 'pago' then
    status := 'liberado';
    usos_restantes := greatest(r.usos_restantes, 0);
    return next;
    return;
  end if;

  if r.tipo <> 'teste' then
    status := 'bloqueado';
    usos_restantes := greatest(r.usos_restantes, 0);
    return next;
    return;
  end if;

  -- teste: sem créditos
  if coalesce(r.usos_restantes, 0) <= 0 then
    status := 'bloqueado';
    usos_restantes := 0;
    return next;
    return;
  end if;

  -- teste: decremento atómico (nunca fica negativo)
  update public.licencas l
  set usos_restantes = greatest(l.usos_restantes - 1, 0)
  where l.id = r.id
    and l.usos_restantes > 0
  returning l.usos_restantes into novo;

  if novo is null then
    -- corrida ou esgotamento entre selects
    select greatest(l.usos_restantes, 0)
    into usos_restantes
    from public.licencas l
    where l.id = r.id;

    status := 'bloqueado';
    usos_restantes := coalesce(usos_restantes, 0);
    return next;
    return;
  end if;

  status := 'liberado';
  usos_restantes := novo;
  return next;
end;
$$;

comment on function public.consumir_auditoria(text) is
  'UPSERT inicial por email; teste decrementa até 0; pago libera sem decrementar; inativo ou sem teste bloqueia.';

grant execute on function public.consumir_auditoria(text) to anon;
grant execute on function public.consumir_auditoria(text) to authenticated;
