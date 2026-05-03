-- Evita cair em «tipo inválido» ou ramo errado por espaços / capitalização em `licencas.tipo`.

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

  insert into public.licencas (email, tipo, usos_restantes, ativo)
  values (v_email, 'teste', 5, true)
  on conflict (email) do nothing;

  select *
  into r
  from public.licencas l
  where l.email = v_email
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
  'Abertura app: garante UPSERT por email; pago valida/dispositivos; tipo normalizado com trim + lower.';

grant execute on function public.validar_acesso(text, text) to anon;
grant execute on function public.validar_acesso(text, text) to authenticated;
