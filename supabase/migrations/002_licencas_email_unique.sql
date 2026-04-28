-- Aplicar em bases onde a tabela public.licencas já existia SEM unique em email.
-- Instalações novas já criam a constraint em 001_licencas.sql — este script ignora-se a si próprio.

do $$
begin
  if not exists (
    select 1
    from pg_constraint c
    join pg_class t on c.conrelid = t.oid
    join pg_namespace n on t.relnamespace = n.oid
    where n.nspname = 'public'
      and t.relname = 'licencas'
      and c.conname = 'licencas_email_unique'
  ) then
    alter table public.licencas
      add constraint licencas_email_unique unique (email);
  end if;
end $$;

comment on column public.licencas.email is
  'Endereço do utilizador; UNIQUE — no máximo uma linha por email.';

comment on table public.licencas is
  'Uma licença por email; estado e quotas no servidor.';
