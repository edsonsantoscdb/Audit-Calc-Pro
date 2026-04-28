-- Substitui consumir_auditoria(text) por consumir_auditoria(text, text) com device_id.
-- Compatibilidade: remove a assinatura antiga (Postgres não substitui ao mudar parâmetros).

drop function if exists public.consumir_auditoria(text);

create or replace function public.consumir_auditoria(p_email text, p_device_id text)
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
  v_in text := nullif(trim(both from coalesce(p_device_id, '')), '');
  r public.licencas%rowtype;
  novo integer;
  reg_dev text;
  -- Futuro: passar a true para exigir correspondência de dispositivo também em tipo 'teste'
  enforce_device_on_teste boolean := false;
begin
  -- entrada inválida
  if v_email = '' then
    status := 'bloqueado';
    usos_restantes := 0;
    return next;
    return;
  end if;

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

  -- Primeiro vínculo do aparelho (só linha ativa; prepara validação futura)
  if r.ativo and (r.device_id is null or trim(both from r.device_id) = '') and v_in is not null then
    update public.licencas l
    set device_id = v_in
    where l.id = r.id;

    r.device_id := v_in;
  end if;

  reg_dev := nullif(trim(both from coalesce(r.device_id, '')), '');

  if not r.ativo then
    status := 'bloqueado';
    usos_restantes := greatest(r.usos_restantes, 0);
    return next;
    return;
  end if;

  -- pago: validar dispositivo quando já existe registo (imposição estrita)
  if r.tipo = 'pago' then
    if reg_dev is not null and (v_in is null or v_in <> reg_dev) then
      status := 'bloqueado';
      usos_restantes := greatest(r.usos_restantes, 0);
      return next;
      return;
    end if;

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

  -- teste: validação de dispositivo opcional (desligada por agora)
  if enforce_device_on_teste and reg_dev is not null and (v_in is null or v_in <> reg_dev) then
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

comment on function public.consumir_auditoria(text, text) is
  'UPSERT por email; vincula device_id na primeira vez; tipo pago exige device quando já gravado; teste decrementa igual; teste+device enforcement reservado (enforce_device_on_teste).';

grant execute on function public.consumir_auditoria(text, text) to anon;
grant execute on function public.consumir_auditoria(text, text) to authenticated;
