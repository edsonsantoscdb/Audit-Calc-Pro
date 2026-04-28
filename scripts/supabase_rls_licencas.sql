-- NOTA: estas funções e o RLS fazem parte da migration
--   supabase/migrations/007_licencas_chaves_rpc_android.sql
-- Use este ficheiro só se precisar de reproduzir o trecho isoladamente no SQL Editor.
--
-- Rode no Supabase: SQL Editor → New query → colar tudo → Run.
-- Objetivo: ativar RLS na tabela licencas e deixar de expor SELECT/UPDATE direto para anon.
-- O app cliente passa a usar apenas as funções RPC abaixo (anon só executa estas funções).
-- O gerador interno usa service_role, que ignora RLS (continua a inserir/listar).

-- 1) Funções RPC (SECURITY DEFINER = executam com permissões do dono, com regras explícitas)

create or replace function public.get_licenca_por_chave(p_chave text)
returns setof public.licencas
language sql
security definer
set search_path = public
as $$
  select *
  from public.licencas
  where upper(trim(chave)) = upper(trim(p_chave))
  limit 1;
$$;

create or replace function public.vincular_android_licenca(
  p_chave text,
  p_android_id text,
  p_anterior text default null
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  update public.licencas l
  set
    android_id = nullif(trim(p_android_id), ''),
    data_ativacao = now()
  where upper(trim(l.chave)) = upper(trim(p_chave))
    and l.ativo = true
    and (l.expira_em is null or l.expira_em > now())
    and (
      l.android_id is null
      or l.android_id = nullif(trim(p_android_id), '')
      or (
        p_anterior is not null
        and trim(p_anterior) <> ''
        and l.android_id = trim(p_anterior)
      )
    );
end;
$$;

-- 2) Quem pode executar (cliente = anon; gerador = service_role já tem tudo)

grant execute on function public.get_licenca_por_chave(text) to anon;
grant execute on function public.vincular_android_licenca(text, text, text) to anon;

-- 3) RLS: sem políticas na tabela para anon = anon não lê nem altera a tabela diretamente

alter table public.licencas enable row level security;

-- 4) Coluna de e-mail (para associar o cliente à chave gerada pelo gerador interno)

alter table public.licencas add column if not exists email text;

-- Opcional: políticas explícitas só para utilizadores autenticados (se no futuro usar Auth).
-- Por agora, não é necessário: service_role ignora RLS; anon não tem políticas = bloqueado na tabela.
