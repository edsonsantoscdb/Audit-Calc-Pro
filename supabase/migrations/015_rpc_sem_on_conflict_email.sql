-- Mesmo problema 42P10 do webhook: validar_acesso e consumir_auditoria usam
-- INSERT ... ON CONFLICT (email) sem UNIQUE(em email) nesta instalacao.
-- Substitui por INSERT ... SELECT ... WHERE NOT EXISTS e associa uma chave
-- sintetica TR-* (tabelas onde chave e NOT NULL).

create or replace function public.validar_acesso(p_email text, p_device_id text)
returns table (
  status text,
  tipo text,
  usos_restantes integer,
  mensagem text
)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_email text := lower(trim(both from coalesce(p_email, '')));
  v_in text := nullif(trim(both from coalesce(p_device_id, '')), '');
  r record;
  reg_dev text;
  vtipo text;
  vtipo_norm text;
begin
  if v_email = '' then
    status := 'bloqueado';
    tipo := 'teste';
    usos_restantes := 0;
    mensagem := 'Informe um e-mail válido.';
    return next;
    return;
  end if;

  insert into public.licencas (email, chave, tipo, usos_restantes, ativo)
  select
    v_email,
    'TR-' || upper(md5(v_email)),
    'teste',
    5,
    true
  where not exists (
    select 1
    from public.licencas l
    where lower(trim(both from coalesce(l.email, ''))) = v_email
  );

  select *
  into r
  from public.licencas l
  where lower(trim(both from coalesce(l.email, ''))) = v_email
  for update;

  if not found then
    status := 'bloqueado';
    tipo := 'teste';
    usos_restantes := 0;
    mensagem := 'Registo não disponível.';
    return next;
    return;
  end if;

  vtipo := r.tipo;
  vtipo_norm := lower(trim(both from coalesce(vtipo, '')));
  reg_dev := nullif(trim(both from coalesce(r.device_id, '')), '');

  if not r.ativo then
    status := 'bloqueado';
    tipo := coalesce(vtipo_norm, 'teste');
    usos_restantes := greatest(coalesce(r.usos_restantes, 0), 0);
    mensagem := 'Licença inativa.';
    return next;
    return;
  end if;

  if vtipo_norm = 'pago' then
    if reg_dev is null then
      if v_in is not null then
        update public.licencas l
        set device_id = v_in
        where l.id = r.id;

        status := 'liberado';
        tipo := 'pago';
        usos_restantes := greatest(coalesce(r.usos_restantes, 0), 0);
        mensagem := null;
        return next;
        return;
      end if;

      status := 'bloqueado';
      tipo := 'pago';
      usos_restantes := greatest(coalesce(r.usos_restantes, 0), 0);
      mensagem := 'Envie o identificador do dispositivo para vincular a licença paga.';
      return next;
      return;
    end if;

    if v_in is not null and reg_dev = v_in then
      status := 'liberado';
      tipo := 'pago';
      usos_restantes := greatest(coalesce(r.usos_restantes, 0), 0);
      mensagem := null;
      return next;
      return;
    end if;

    status := 'bloqueado';
    tipo := 'pago';
    usos_restantes := greatest(coalesce(r.usos_restantes, 0), 0);
    mensagem := 'Dispositivo não autorizado para esta licença.';
    return next;
    return;
  end if;

  if vtipo_norm = 'teste' then
    status := 'liberado';
    tipo := 'teste';
    usos_restantes := greatest(coalesce(r.usos_restantes, 0), 0);
    mensagem := format(
      'Você possui %s auditorias gratuitas restantes.',
      usos_restantes
    );
    return next;
    return;
  end if;

  status := 'bloqueado';
  tipo := coalesce(vtipo_norm, 'teste');
  usos_restantes := greatest(coalesce(r.usos_restantes, 0), 0);
  mensagem := 'Tipo de licença inválido.';
  return next;
end;
$$;

comment on function public.validar_acesso(text, text) is
  'Primeira vista: garante linha trial sem ON CONFLICT; paga valida/dispositivo; tipo normalizado.';

grant execute on function public.validar_acesso(text, text) to anon;
grant execute on function public.validar_acesso(text, text) to authenticated;


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
  enforce_device_on_teste boolean := false;
begin
  if v_email = '' then
    status := 'bloqueado';
    usos_restantes := 0;
    return next;
    return;
  end if;

  insert into public.licencas (email, chave, tipo, usos_restantes, ativo)
  select
    v_email,
    'TR-' || upper(md5(v_email)),
    'teste',
    5,
    true
  where not exists (
    select 1
    from public.licencas l
    where lower(trim(both from coalesce(l.email, ''))) = v_email
  );

  select *
  into r
  from public.licencas
  where lower(trim(both from coalesce(email, ''))) = v_email
  for update;

  if not found then
    status := 'bloqueado';
    usos_restantes := 0;
    return next;
    return;
  end if;

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

  if enforce_device_on_teste and reg_dev is not null and (v_in is null or v_in <> reg_dev) then
    status := 'bloqueado';
    usos_restantes := greatest(r.usos_restantes, 0);
    return next;
    return;
  end if;

  if coalesce(r.usos_restantes, 0) <= 0 then
    status := 'bloqueado';
    usos_restantes := 0;
    return next;
    return;
  end if;

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
  'Garante linha trial sem ON CONFLICT (email); igual consumo decremento antes.';

grant execute on function public.consumir_auditoria(text, text) to anon;
grant execute on function public.consumir_auditoria(text, text) to authenticated;
