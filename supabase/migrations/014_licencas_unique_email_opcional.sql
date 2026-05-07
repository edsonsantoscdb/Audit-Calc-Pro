-- Garantir UNIQUE(email) em instalações que perderam ou nunca aplicaram licencas_email_unique.
-- Se falhar: primeiro apague linhas duplicadas com o mesmo trim(lower(email)).

do $$
begin
  if not exists (
    select 1
    from pg_constraint c
    join pg_class t on c.conrelid = t.oid
    join pg_namespace n on n.oid = t.relnamespace
    where n.nspname = 'public'
      and t.relname = 'licencas'
      and c.conname = 'licencas_email_unique'
      and c.contype = 'u'
  ) then
    alter table public.licencas
      add constraint licencas_email_unique unique (email);
  end if;
exception
  when duplicate_object then null;
  when unique_violation then
    raise notice 'licencas_email_unique nao aplicada: ha e-mails duplicados; a migration 016 regulariza o fluxo sem depender desta constraint.';
  when others then raise;
end $$;
