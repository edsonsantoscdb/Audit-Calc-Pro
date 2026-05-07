-- Repara tabela public.licencas quando foi criada ou alterada sem o schema completo
-- (erro 42703: column "tipo" does not exist, etc.).
-- Idempotente: usa IF NOT EXISTS em colunas.

-- Colunas base (001_licencas.sql); não tocámos em `email` — assume-se que já existe.
alter table public.licencas add column if not exists id uuid default gen_random_uuid();
alter table public.licencas add column if not exists device_id text;
alter table public.licencas add column if not exists tipo text not null default 'teste';
alter table public.licencas add column if not exists usos_restantes integer not null default 5;
alter table public.licencas add column if not exists trocas integer not null default 0;
alter table public.licencas add column if not exists ativo boolean not null default true;
alter table public.licencas add column if not exists criado_em timestamptz not null default now();

-- Já usada pelo webhook (007/008/009)
alter table public.licencas add column if not exists data_ativacao timestamptz;

-- Extras usados por RPCs/Android (007/009) — segurança futura
alter table public.licencas add column if not exists chave text;
alter table public.licencas add column if not exists comprador text;
alter table public.licencas add column if not exists android_id text;
alter table public.licencas add column if not exists pending_android_id text;
alter table public.licencas add column if not exists expira_em timestamptz;
alter table public.licencas add column if not exists created_at timestamptz;

-- Uma linha por email (necessário para ON CONFLICT (email) no webhook)
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
exception
  when duplicate_object then null;
  when unique_violation then
    raise notice 'licencas_email_unique nao aplicada: ha e-mails duplicados; migrations posteriores nao dependem de ON CONFLICT(email).';
  when others then raise;
end $$;
