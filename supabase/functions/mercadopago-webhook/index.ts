/**
 * Webhook Mercado Pago → activa licença (tipo pago) por email após pagamento approved.
 *
 * Secrets (Supabase Dashboard → Edge Functions → mercadopago-webhook):
 * - MERCADO_PAGO_ACCESS_TOKEN — criar/obter na conta Mercado Pago (developers → credenciais).
 * SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY são injectados automaticamente no deploy Supabase.
 *
 * URL da função: https://<project-ref>.supabase.co/functions/v1/mercadopago-webhook
 *
 * Deploy: supabase functions deploy mercadopago-webhook
 */

import { createClient } from "npm:@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

type MpNotificationBody = Record<string, unknown>;

function extrair_payment_id(corpo: MpNotificationBody | null): string | null {
  if (!corpo || typeof corpo !== "object") return null;

  const d = corpo.data;
  if (d && typeof d === "object" && "id" in d) {
    const id = (d as { id?: unknown }).id;
    if (id !== undefined && id !== null) return String(id);
  }

  if ("id" in corpo && corpo.id !== undefined && corpo.id !== null) {
    return String(corpo.id);
  }

  const resource = corpo.resource;
  if (typeof resource === "string" && resource.includes("/")) {
    const partes = resource.split("/");
    const ultimo = partes[partes.length - 1]?.split("?")[0];
    if (ultimo) return ultimo;
  }

  return null;
}

function normalizar_email(val: unknown): string | null {
  if (typeof val !== "string") return null;
  const t = val.trim().toLowerCase();
  return t.length > 0 ? t : null;
}

async function processar_pagamento(
  paymentId: string,
  supabase_url: string,
  service_key: string,
  mp_token: string,
): Promise<Response> {
  const supabase = createClient(supabase_url, service_key, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  const mpRes = await fetch(`https://api.mercadopago.com/v1/payments/${paymentId}`, {
    headers: { Authorization: `Bearer ${mp_token}` },
  });

  if (!mpRes.ok) {
    const errBody = await mpRes.text();
    console.error("Webhook MP API", mpRes.status, errBody);
    return new Response(JSON.stringify({ error: "mp_api" }), {
      status: 502,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  const payment = await mpRes.json() as Record<string, unknown>;

  const statusMp = typeof payment.status === "string" ? payment.status : "";
  if (statusMp !== "approved") {
    console.log("Webhook: pagamento não approved", paymentId, statusMp);
    return new Response(JSON.stringify({ ok: true, skip: "not_approved", status: statusMp }), {
      status: 200,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  const payer = payment.payer as Record<string, unknown> | undefined;
  const meta = payment.metadata as Record<string, unknown> | undefined;

  /* Ordem: external_reference (definido na criação do pagamento) → metadata.email → payer.email */
  let email =
    normalizar_email(payment.external_reference) ??
    normalizar_email(meta?.email) ??
    normalizar_email(payer?.email);

  if (!email) {
    console.warn("Webhook: approved sem identificação (external_reference / metadata.email / payer.email)", paymentId);
    return new Response(JSON.stringify({ ok: true, skip: "no_email", payment_id: paymentId }), {
      status: 200,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  const { error } = await supabase.rpc("marcar_licenca_paga_por_email", {
    p_email: email,
  });

  if (error) {
    console.error("Webhook: RPC marcar_licenca_paga_por_email", error);
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  return new Response(
    JSON.stringify({ ok: true, email, payment_id: paymentId }),
    { status: 200, headers: { ...corsHeaders, "Content-Type": "application/json" } },
  );
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL") ?? "";
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
  const mpToken = Deno.env.get("MERCADO_PAGO_ACCESS_TOKEN") ?? "";

  if (!supabaseUrl || !serviceKey || !mpToken) {
    console.error("Webhook: falta SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY ou MERCADO_PAGO_ACCESS_TOKEN");
    return new Response(JSON.stringify({ error: "misconfigured" }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  /** IPN legacy Mercado Pago: GET ...?topic=payment&id=<id> */
  if (req.method === "GET") {
    const u = new URL(req.url);
    const topic = u.searchParams.get("topic");
    const pid = u.searchParams.get("id") || u.searchParams.get("data.id");
    if (topic === "payment" && pid) {
      return await processar_pagamento(pid, supabaseUrl, serviceKey, mpToken);
    }
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  if (req.method !== "POST") {
    return new Response(JSON.stringify({ ok: true, skip: "method" }), {
      status: 200,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  let corpo: MpNotificationBody | null = null;
  try {
    const texto = await req.text();
    if (texto) corpo = JSON.parse(texto) as MpNotificationBody;
  } catch {
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  const paymentId = extrair_payment_id(corpo);
  if (!paymentId) {
    console.log("Webhook: payload sem payment id ignorado", JSON.stringify(corpo));
    return new Response(JSON.stringify({ ok: true, skip: "no_payment_id" }), {
      status: 200,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  return await processar_pagamento(paymentId, supabaseUrl, serviceKey, mpToken);
});
