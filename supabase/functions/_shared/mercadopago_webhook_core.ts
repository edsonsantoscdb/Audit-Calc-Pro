import { createClient, type SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2";

type WebhookBody = {
  type?: string;
  topic?: string;
  action?: string;
  id?: string | number;
  resource?: string;
  data?: { id?: string | number };
};

type MpPayment = {
  status?: string;
  external_reference?: string | null;
  payer?: { email?: string | null };
  metadata?: Record<string, unknown> | null;
};

const PAYMENT_TERMINAL_BAD = new Set([
  "rejected",
  "cancelled",
  "refunded",
  "charged_back",
]);

/** Estados em que vale voltar a consultar antes de desistir (corrida payment.created vs aprovação). */
const PAYMENT_RETRY_IF_STATUS = new Set([
  "pending",
  "in_process",
  "authorized",
]);

/** Poucas tentativas + espera curta — MP costuma falhar webhook se ultrapassar ~22s sem 200 OK. */
const POLL_ATTEMPTS = 6;
const POLL_BASE_MS = 900;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function extractPaymentIdFromResource(resource?: string): string {
  const value = (resource ?? "").trim();
  if (!value) return "";
  const match = value.match(/\/payments\/([^/?#]+)/i) ?? value.match(/(\d+)(?:[/?#].*)?$/);
  return match?.[1] ? String(match[1]).trim() : "";
}

async function fetchPaymentJson(
  paymentIdStr: string,
  accessToken: string,
): Promise<MpPayment | null> {
  const mpResponse = await fetch(
    `https://api.mercadopago.com/v1/payments/${paymentIdStr}`,
    {
      headers: { Authorization: `Bearer ${accessToken}` },
    },
  );

  if (!mpResponse.ok) {
    console.error(
      `Erro ao buscar pagamento ${paymentIdStr}: HTTP ${mpResponse.status}`,
    );
    return null;
  }

  return (await mpResponse.json()) as MpPayment;
}

function getSupabase(): SupabaseClient {
  const url = Deno.env.get("SUPABASE_URL");
  const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!url || !key) {
    throw new Error("SUPABASE_URL ou SUPABASE_SERVICE_ROLE_KEY ausente");
  }
  return createClient(url, key);
}

/**
 * Processa uma notificação do Mercado Pago (corpo JSON já lido).
 */
export async function handleMercadoPagoWebhookJson(
  webhook: WebhookBody,
): Promise<void> {
  const MP_ACCESS_TOKEN = Deno.env.get("MERCADO_PAGO_ACCESS_TOKEN")?.trim();
  if (!MP_ACCESS_TOKEN) {
    console.error("MERCADO_PAGO_ACCESS_TOKEN não configurado");
    return;
  }

  const webhookType =
    (webhook.type ?? webhook.topic ?? "").trim().toLowerCase() ||
    ((webhook.action ?? "").trim().toLowerCase().startsWith("payment.") ? "payment" : "");

  if (webhookType !== "payment") {
    console.log("Ignorando webhook que nao e payment:", {
      type: webhook.type,
      topic: webhook.topic,
      action: webhook.action,
    });
    return;
  }

  const paymentId = webhook.data?.id ?? webhook.id ?? extractPaymentIdFromResource(webhook.resource);
  if (paymentId == null || paymentId === "") {
    console.error("Payment ID ausente no webhook:", JSON.stringify(webhook).slice(0, 2000));
    return;
  }

  const paymentIdStr = String(paymentId);
  console.log(`Buscando pagamento ${paymentIdStr} na API MP...`);

  let payment: MpPayment | null = null;
  for (let attempt = 0; attempt < POLL_ATTEMPTS; attempt++) {
    payment = await fetchPaymentJson(paymentIdStr, MP_ACCESS_TOKEN);
    if (!payment) {
      return;
    }

    const st = (payment.status ?? "").trim();
    console.log(`Status do pagamento (tentativa ${attempt + 1}):`, st || "?");

    if (st === "approved") {
      break;
    }

    if (PAYMENT_TERMINAL_BAD.has(st)) {
      console.log(`Pagamento ${paymentIdStr} recusado/terminal: ${st}`);
      return;
    }

    const shouldRetry = PAYMENT_RETRY_IF_STATUS.has(st);
    if (shouldRetry && attempt < POLL_ATTEMPTS - 1) {
      const wait = POLL_BASE_MS + attempt * 400;
      console.log(
        `Pagamento ${paymentIdStr} ainda ${st}; nova consulta em ${wait}ms`,
      );
      await sleep(wait);
      continue;
    }

    console.log(
      `Pagamento ${paymentIdStr} não aprovado após tentativas (${st || "?"})`,
    );
    return;
  }

  if (!payment || payment.status !== "approved") {
    return;
  }

  const meta = payment.metadata && typeof payment.metadata === "object"
    ? payment.metadata
    : null;
  const metaEmail = meta &&
      typeof meta["audit_calc_email"] === "string"
    ? String(meta["audit_calc_email"]).trim()
    : "";

  const email =
    (payment.external_reference &&
      String(payment.external_reference).trim()) ||
    metaEmail ||
    (payment.payer?.email && String(payment.payer.email).trim()) ||
    "";

  if (!email) {
    console.error(
      "Email/reference vazio no pagamento aprovado:",
      paymentIdStr,
      JSON.stringify(payment).slice(0, 2000),
    );
    return;
  }

  const supabase = getSupabase();
  const { error } = await supabase.rpc("marcar_licenca_paga_por_email", {
    p_email: email,
  });

  if (error) {
    console.error("marcar_licenca_paga_por_email:", error);
    return;
  }

  console.log(`Licença paga activada (RPC) para: ${email}`);
}

export async function handleMercadoPagoWebhookRequest(req: Request): Promise<void> {
  const url = new URL(req.url);
  let webhook: WebhookBody = {};

  try {
    const parsed = await req.json();
    webhook = parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed as WebhookBody
      : {};
  } catch {
    webhook = {};
  }

  webhook.type ??= url.searchParams.get("type") ?? undefined;
  webhook.topic ??= url.searchParams.get("topic") ?? undefined;
  webhook.action ??= url.searchParams.get("action") ?? undefined;
  webhook.id ??= url.searchParams.get("id") ?? undefined;
  webhook.resource ??= url.searchParams.get("resource") ?? undefined;
  webhook.data ??= {};
  webhook.data.id ??=
    url.searchParams.get("data.id") ??
    url.searchParams.get("data_id") ??
    undefined;

  console.log("Webhook recebido:", JSON.stringify(webhook, null, 2));
  await handleMercadoPagoWebhookJson(webhook);
}
