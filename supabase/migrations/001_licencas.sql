-- Tabela de licenças: controlo de uso no servidor (Supabase).
-- Uma linha por utilizador: o email é único (constraint UNIQUE).

create table if not exists public.licencas (
  id uuid primary key default gen_random_uuid(),

  -- Identificação do cliente; único na tabela (uma licença por email).
  email text not null,

  constraint licencas_email_unique unique (email),

  -- Hash/identificador do aparelho (ex.: mesmo algoritmo do app); null até primeiro vínculo.
  device_id text,

  -- 'teste' = modo gratuito limitado; 'pago' = licença adquirida.
  tipo text not null default 'teste'
    check (tipo in ('teste', 'pago')),

  -- Contador de auditorias disponíveis (ex.: 5 no início do teste).
  usos_restantes integer not null default 5
    check (usos_restantes >= 0),

  -- Número de trocas de dispositivo já consumidas (política de limite no código/RPC).
  trocas integer not null default 0
    check (trocas >= 0),

  -- Licença revogada ou invalidada sem apagar o registo.
  ativo boolean not null default true,

  -- Momento de criação da linha (servidor, UTC).
  criado_em timestamptz not null default now()
);

comment on table public.licencas is
  'Uma licença por email; estado e quotas no servidor.';

comment on column public.licencas.email is
  'Endereço do utilizador; UNIQUE — no máximo uma linha por email.';

comment on column public.licencas.device_id is
  'Identificador estável do dispositivo vinculado a esta linha (quando aplicável).';

comment on column public.licencas.tipo is
  'teste = quota gratuita; pago = acesso pago.';

comment on column public.licencas.usos_restantes is
  'Auditorias restantes nesta licença (ex.: decremente no servidor a cada uso).';

comment on column public.licencas.trocas is
  'Contagem de operações de troca de aparelho (limite tratado pela aplicação ou RPC).';
