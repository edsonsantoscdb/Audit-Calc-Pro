-- Corrige Postgres 42703 (undefined_column) em marcar_licenca_paga_por_email
-- quando 008 já está aplicada mas 007/009 não criaram esta coluna.

alter table public.licencas
  add column if not exists data_ativacao timestamptz;
