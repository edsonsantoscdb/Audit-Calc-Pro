import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  const token = (Deno.env.get("MERCADO_PAGO_ACCESS_TOKEN") ?? "").trim();
  if (!token) {
    return new Response(
      JSON.stringify({ error: "MERCADO_PAGO_ACCESS_TOKEN não configurado" }),
      {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      },
    );
  }

  if (req.method !== "POST") {
    return new Response(
      JSON.stringify({ error: "Método não permitido. Use POST." }),
      {
        status: 405,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      },
    );
  }

  let email: string;
  try {
    const body = (await req.json()) as { email?: unknown };
    const raw = typeof body.email === "string" ? body.email.trim() : "";
    if (!raw || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(raw)) {
      throw new Error("Email inválido");
    }
    email = raw;
  } catch {
    return new Response(
      JSON.stringify({
        error:
          'Email inválido ou ausente. Envie: { "email": "usuario@email.com" }',
      }),
      {
        status: 400,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      },
    );
  }

  try {
    const response = await fetch("https://api.mercadopago.com/checkout/preferences", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        items: [
          {
            title: "Licença Audit Calc",
            quantity: 1,
            currency_id: "BRL",
            unit_price: 1.0,
          },
        ],
        payment_methods: {
          excluded_payment_methods: [],
          excluded_payment_types: [],
        },
        payer: { email },
        external_reference: email,
        metadata: { audit_calc_email: email },
        back_urls: {
          success: "https://seudominio.com/sucesso",
          failure: "https://seudominio.com/falha",
          pending: "https://seudominio.com/pendente",
        },
        auto_return: "approved",
      }),
    });

    const data = (await response.json()) as Record<string, unknown>;

    if (!response.ok) {
      console.error("Erro MP:", data);
      return new Response(
        JSON.stringify({
          error: "Erro ao criar preferência no Mercado Pago",
          details: data,
        }),
        {
          status: response.status,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        },
      );
    }

    const init_point =
      (typeof data.init_point === "string" ? data.init_point : null) ??
      (typeof data.sandbox_init_point === "string"
        ? data.sandbox_init_point
        : null);

    if (!init_point) {
      return new Response(
        JSON.stringify({ error: "URL do checkout não retornada" }),
        {
          status: 502,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        },
      );
    }

    return new Response(
      JSON.stringify({
        init_point: init_point,
        preference_id: data.id,
      }),
      {
        status: 200,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      },
    );
  } catch (error) {
    console.error("Erro na função:", error);
    return new Response(JSON.stringify({ error: "Erro interno do servidor" }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});
