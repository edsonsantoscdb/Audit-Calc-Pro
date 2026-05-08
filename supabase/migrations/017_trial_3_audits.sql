-- Reduz auditorias gratuitas (trial) de 5 para 3.
-- - Ajusta default da coluna usos_restantes.
-- - Recria validar_acesso e consumir_auditoria com o novo limite.
-- - Aplica teto de 3 nas linhas trial existentes (ninguem comprou ainda;
--   contas pagas ja entram com 0 e nao sao afetadas).

alter table public.licencas alter column usos_restantes set default 3;

update public.licencas
set usos_restantes = least(coalesce(usos_restantes, 0), 3)
where lower(trim(both from coalesce(tipo, ''))) = 'teste'
  and coalesce(usos_restantes, 0) > 3;

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
  r public.licencas%rowtype;
  reg_dev text;
  vtipo_norm text;
begin
  if v_email = '' then
    status := 'bloqueado';
    tipo := 'teste';
    usos_restantes := 0;
    mensagem := 'Informe um e-mail valido.';
    return next;
    return;
  end if;

  insert into public.licencas (email, chave, tipo, usos_restantes, ativo, created_at)
  select v_email, 'TR-' || upper(md5(v_email)), 'teste', 3, true, now()
  where not exists (
    select 1
    from public.licencas l
    where lower(trim(both from coalesce(l.email, ''))) = v_email
  );

  select l.*
  into r
  from public.licencas l
  where lower(trim(both from coalesce(l.email, ''))) = v_email
  order by
    case when lower(trim(both from coalesce(l.tipo, ''))) = 'pago' and l.ativo then 0 else 1 end,
    case when l.ativo then 0 else 1 end,
    coalesce(l.data_ativacao, l.created_at, now()) desc,
    l.id
  limit 1
  for update;

  if not found then
    status := 'bloqueado';
    tipo := 'teste';
    usos_restantes := 0;
    mensagem := 'Registo nao disponivel.';
    return next;
    return;
  end if;

  vtipo_norm := lower(trim(both from coalesce(r.tipo, '')));
  reg_dev := nullif(trim(both from coalesce(r.device_id, '')), '');

  if not r.ativo then
    status := 'bloqueado';
    tipo := coalesce(vtipo_norm, 'teste');
    usos_restantes := greatest(coalesce(r.usos_restantes, 0), 0);
    mensagem := 'Licenca inativa.';
    return next;
    return;
  end if;

  if vtipo_norm = 'pago' then
    if reg_dev is null and v_in is not null then
      update public.licencas l
      set device_id = v_in
      where l.id = r.id;
    end if;

    status := 'liberado';
    tipo := 'pago';
    usos_restantes := greatest(coalesce(r.usos_restantes, 0), 0);
    mensagem := 'Acesso liberado pelo e-mail cadastrado.';
    return next;
    return;
  end if;

  if vtipo_norm = 'teste' then
    status := 'liberado';
    tipo := 'teste';
    usos_restantes := greatest(coalesce(r.usos_restantes, 0), 0);
    mensagem := format('Voce possui %s auditorias gratuitas restantes.', usos_restantes);
    return next;
    return;
  end if;

  status := 'bloqueado';
  tipo := coalesce(vtipo_norm, 'teste');
  usos_restantes := greatest(coalesce(r.usos_restantes, 0), 0);
  mensagem := 'Tipo de licenca invalido.';
  return next;
end;
$$;

comment on function public.validar_acesso(text, text) is
  'Valida por e-mail normalizado; trial cria com 3 usos; pago libera por e-mail.';

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
  vtipo_norm text;
begin
  if v_email = '' then
    status := 'bloqueado';
    usos_restantes := 0;
    return next;
    return;
  end if;

  insert into public.licencas (email, chave, tipo, usos_restantes, ativo, created_at)
  select v_email, 'TR-' || upper(md5(v_email)), 'teste', 3, true, now()
  where not exists (
    select 1
    from public.licencas l
    where lower(trim(both from coalesce(l.email, ''))) = v_email
  );

  select l.*
  into r
  from public.licencas l
  where lower(trim(both from coalesce(l.email, ''))) = v_email
  order by
    case when lower(trim(both from coalesce(l.tipo, ''))) = 'pago' and l.ativo then 0 else 1 end,
    case when l.ativo then 0 else 1 end,
    coalesce(l.data_ativacao, l.created_at, now()) desc,
    l.id
  limit 1
  for update;

  if not found or not r.ativo then
    status := 'bloqueado';
    usos_restantes := 0;
    return next;
    return;
  end if;

  vtipo_norm := lower(trim(both from coalesce(r.tipo, '')));
  reg_dev := nullif(trim(both from coalesce(r.device_id, '')), '');

  if vtipo_norm = 'pago' then
    if reg_dev is null and v_in is not null then
      update public.licencas l
      set device_id = v_in
      where l.id = r.id;
    end if;

    status := 'liberado';
    usos_restantes := greatest(coalesce(r.usos_restantes, 0), 0);
    return next;
    return;
  end if;

  if vtipo_norm <> 'teste' then
    status := 'bloqueado';
    usos_restantes := greatest(coalesce(r.usos_restantes, 0), 0);
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

  status := case when novo is null then 'bloqueado' else 'liberado' end;
  usos_restantes := coalesce(novo, 0);
  return next;
end;
$$;

comment on function public.consumir_auditoria(text, text) is
  'Consome trial (3 usos); pago libera por e-mail e nao bloqueia por device_id antigo.';

grant execute on function public.consumir_auditoria(text, text) to anon;
grant execute on function public.consumir_auditoria(text, text) to authenticated;
