import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { handleMercadoPagoWebhookRequest } from "../_shared/mercadopago_webhook_core.ts";

serve(async (req) => {
  if (req.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405 });
  }

  try {
    await handleMercadoPagoWebhookRequest(req);
  } catch (e) {
    console.error("Erro no processamento do webhook:", e);
  }

  return new Response(
    JSON.stringify({ received: true, timestamp: Date.now() }),
    {
      status: 200,
      headers: { "Content-Type": "application/json" },
    },
  );
});
