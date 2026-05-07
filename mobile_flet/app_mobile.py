import asyncio
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

import flet as ft

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.motor_auditoria import ErroAuditoria, StatusVeredito, auditar_financiamento
from mobile_flet.app_identity import (
    email_basico_valido,
    get_device_id,
    get_email_salvo,
    salvar_email,
    set_storage_root,
)
from mobile_flet.supabase_license import (
    FREE_AUDITS_LIMIT,
    MERCADOPAGO_CHECKOUT_URL,
    activate,
    android_storage_candidate_dirs,
    chamar_consumir_auditoria,
    chamar_validar_acesso,
    chamar_validar_acesso_apos_checkout,
    criar_preferencia_mercadopago_via_edge,
    get_free_audits_remaining,
    is_activated,
    mensagem_pos_revalidacao,
    mensagem_falha_rpc_validar_acesso,
    record_successful_free_audit,
    revalidate_license,
)


def _is_android():
    return hasattr(sys, "getandroidapilevel") or "android" in sys.platform


def _score_dir_persistencia(path: str) -> int:
    """Maior = mais indicado para ficheiros que devem sobreviver ao fechar o app."""
    p = path.replace("\\", "/").lower()
    flet_data = (os.environ.get("FLET_APP_STORAGE_DATA") or "").replace("\\", "/").lower().rstrip("/")
    if flet_data and p.rstrip("/") == flet_data:
        return 500
    if "/data/user/" in p and "/files" in p:
        return 400
    if "/data/data/" in p and "/files" in p:
        return 350
    if "/no_backup/" not in p and "/files" in p and "cache" not in p:
        return 200
    if "cache" in p or "/tmp" in p or p.endswith("/tmp"):
        return -150
    return 0


def _get_data_dir():
    """Retorna diretório gravável para licença e JSON do app (persistente no Android)."""
    if _is_android():
        seen: set[str] = set()
        candidates: list[str] = []
        for key in ("FLET_APP_STORAGE_DATA", "FLET_APP_STORAGE_TEMP"):
            v = (os.environ.get(key) or "").strip()
            if v and v not in seen:
                seen.add(v)
                candidates.append(v)
        for key in ("HOME", "ANDROID_APP_DATA", "TMPDIR"):
            v = (os.environ.get(key) or "").strip()
            if v and v not in seen:
                seen.add(v)
                candidates.append(v)
        for extra in ("/data/local/tmp", tempfile.gettempdir()):
            ev = (extra or "").strip()
            if ev and ev not in seen:
                seen.add(ev)
                candidates.append(ev)

        lic = ".auditcalc_licenca.json"
        banco = ".auditoria_banco.json"
        for d in candidates:
            if not d or not os.path.isdir(d):
                continue
            if os.path.isfile(os.path.join(d, lic)) or os.path.isfile(os.path.join(d, banco)):
                return d

        ranked = sorted(
            (d for d in candidates if d and os.path.isdir(d)),
            key=_score_dir_persistencia,
            reverse=True,
        )
        for d in ranked:
            try:
                test = os.path.join(d, ".write_test_auditcalc")
                with open(test, "w", encoding="utf-8") as f:
                    f.write("ok")
                os.remove(test)
                return d
            except OSError:
                continue
        return ""
    flet_data = (os.environ.get("FLET_APP_STORAGE_DATA") or "").strip()
    if flet_data and os.path.isdir(flet_data):
        return flet_data
    return os.path.expanduser("~")


def main(page: ft.Page):
    # ==========================================
    # 1. BANCO DE DADOS E SEGURANÇA
    # ==========================================
    pasta_usuario = _get_data_dir()
    set_storage_root(pasta_usuario)
    _ = get_device_id()

    app_ativado = is_activated(pasta_usuario)
    licenca_aviso = ""
    if app_ativado:
        ok_lic, cod_lic = revalidate_license(pasta_usuario)
        if not ok_lic:
            app_ativado = False
            licenca_aviso = mensagem_pos_revalidacao(cod_lic)

    # Licença só por e‑mail/Mercado Pago: sem ficheiro .auditcalcpro_licenca.json local.
    _acesso_licenca_por_email_servidor = {"ativo": False}

    def _sinc_credencial_servidor(validar_resp: dict | None) -> None:
        """Actualiza permissão quando validar_acesso devolve estado (inclui pagamento só no servidor)."""
        if not validar_resp:
            return
        tipo = str(validar_resp.get("tipo") or "").strip().lower()
        status = str(validar_resp.get("status") or "").strip().lower()
        if status == "liberado" and tipo == "pago":
            _acesso_licenca_por_email_servidor["ativo"] = True
        elif status == "bloqueado" and tipo == "pago":
            _acesso_licenca_por_email_servidor["ativo"] = False

    def _pode_usar_o_app() -> bool:
        if not email_basico_valido(get_email_salvo()):
            return False
        return (
            is_activated(pasta_usuario)
            or get_free_audits_remaining(pasta_usuario) > 0
            or _acesso_licenca_por_email_servidor["ativo"]
        )

    # ==========================================
    # 2. CONFIGURAÇÃO E CORES
    # ==========================================
    if not _is_android():
        try:
            page.window.width = 400
            page.window.height = 750
            page.window.resizable = False
        except Exception:
            pass
    page.padding = 0
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.scroll = ft.ScrollMode.AUTO
    page.bgcolor = "#0f172a"
    page.theme_mode = ft.ThemeMode.DARK

    COR_FUNDO = "#0f172a"
    COR_CARD = "#1e293b"
    COR_INPUT = "#0c1424"
    COR_ACENTO = "#3b82f6"
    COR_ACENTO_ESCURO = "#2563eb"
    BORDA = "#475569"
    COR_TEXTO, COR_TEXTO_SEC = "#f8fafc", "#94a3b8"
    COR_SUCESSO, COR_ALERTA, COR_ERRO = "#22c55e", "#eab308", "#f87171"
    # Laranja para veredito “CET/Juros Altos” (painel de auditoria e manual)
    COR_STATUS_LARANJA = "#f97316"
    TAM_STATUS_AUDITORIA = 20  # rótulo principal do veredito (maior que o texto auxiliar)

    def _mostrar_snack(msg: str, *, erro: bool = False) -> None:
        """Flet 0.8x: usar show_dialog; page.snack_bar legado muitas vezes não aparece no Android."""
        page.show_dialog(
            ft.SnackBar(
                content=ft.Text(msg, size=14),
                bgcolor=COR_ERRO if erro else COR_CARD,
                behavior=ft.SnackBarBehavior.FLOATING,
                duration=ft.Duration(milliseconds=8000),
            )
        )

    def _msg_erro_preferencia_mp(codigo: str | None) -> str:
        if not codigo:
            return "Não foi possível iniciar o pagamento. Tente de novo."
        if codigo == "sem_email":
            return "Defina um e-mail válido na identificação antes de pagar."
        if codigo == "rede":
            return "Sem Internet ou o servidor não respondeu. Verifique a ligação."
        if codigo == "bad_json":
            return "Resposta inválida do servidor. Tente mais tarde."
        if codigo == "sem_init_point":
            return (
                "O servidor não devolveu o link de pagamento. "
                "Confirme se a função create_mercadopago_payment está em deploy no Supabase."
            )
        if codigo.startswith("http_"):
            return f"Servidor de pagamento respondeu com erro ({codigo})."
        return f"Não foi possível iniciar o pagamento ({codigo})."

    def _cor_historico_status(st: str) -> str:
        if "RASCUNHO" in st:
            return COR_ALERTA
        u = st.upper()
        if "CET/JUROS OK" in u or ("COERENTE" in u and "NÃO" not in u):
            return COR_SUCESSO
        if "CET/JUROS ALTOS" in u:
            return COR_ALERTA
        if "CET/JUROS ABUSIVOS" in u or "NÃO COERENTE" in u:
            return COR_ERRO
        if st.strip().upper() == "ERRO":
            return COR_ERRO
        return COR_TEXTO_SEC

    # Sombra bem leve no painel de resultado (visual mais “flat”; campos mantêm contraste próprio)
    _sombra_leve = ft.BoxShadow(
        spread_radius=0,
        blur_radius=4,
        color="#20000000",
        offset=ft.Offset(0, 2),
    )

    def _resolver_imagem(*nomes):
        if _is_android():
            return nomes[0] if nomes else None
        for nome in nomes:
            caminho_assets = _ROOT / "assets" / nome
            if caminho_assets.exists():
                return str(caminho_assets)
            caminho_raiz = _ROOT / nome
            if caminho_raiz.exists():
                return str(caminho_raiz)
        return None

    # Variáveis globais para os resultados da auditoria
    ultimo_resultado = {"cet": "--.--%", "status": "AGUARDANDO ANÁLISE", "msg": "Preencha os dados e execute"}

    lbl_modo_trial = ft.Text(
        "",
        size=11,
        color=COR_ALERTA,
        text_align=ft.TextAlign.CENTER,
        width=350,
        visible=False,
    )

    _ref_btn_compra: dict[str, ft.Container | None] = {
        "aud": None,
        "ativ": None,
        "jap_aud": None,
    }

    def _sync_btn_comprar_licenca_visibility() -> None:
        vis = (
            (not is_activated(pasta_usuario))
            and (not _acesso_licenca_por_email_servidor["ativo"])
        )
        for k in ("aud", "ativ", "jap_aud"):
            ctl = _ref_btn_compra.get(k)
            if ctl is not None:
                ctl.visible = vis

    def _abrir_tela_compra(msg: str) -> None:
        """Leva o utilizador para os botões de compra quando a quota grátis acaba."""
        lbl_ativacao.value = msg
        lbl_ativacao.color = COR_ALERTA
        _sync_btn_comprar_licenca_visibility()
        navegar_para(tela_ativacao)

    def _sync_banner_trial():
        if is_activated(pasta_usuario) or _acesso_licenca_por_email_servidor["ativo"]:
            lbl_modo_trial.visible = False
            _sync_btn_comprar_licenca_visibility()
            return
        r = get_free_audits_remaining(pasta_usuario)
        lbl_modo_trial.visible = True
        lbl_modo_trial.value = (
            f"Modo avaliação: {r} de {FREE_AUDITS_LIMIT} auditorias grátis. "
            "Depois é necessário licença ou pagamento."
        )
        _sync_btn_comprar_licenca_visibility()

    # =====================================================================
    # TELA DE ATIVAÇÃO (LICENÇA)
    # =====================================================================
    buffer_chave = {"texto": ""}

    def _sync_chave(e):
        buffer_chave["texto"] = (e.control.value or "") if e.control else ""

    def _texto_chave() -> str:
        a = (buffer_chave.get("texto") or "").strip()
        b = (txt_chave.value or "").strip()
        return a if len(a) >= len(b) else b

    def _btn_licenca(texto: str, cor_fundo: str, ao_clicar, altura: int = 52):
        """Container + on_click: em Android o ft.Button às vezes não dispara."""
        return ft.Container(
            content=ft.Text(
                texto,
                color="#f8fafc",
                weight=ft.FontWeight.W_600,
                size=14,
                text_align=ft.TextAlign.CENTER,
            ),
            bgcolor=cor_fundo,
            border_radius=12,
            height=altura,
            width=320,
            alignment=ft.Alignment(0, 0),
            on_click=ao_clicar,
            ink=True,
            ink_color="#40ffffff",
            padding=ft.padding.symmetric(horizontal=12, vertical=14),
        )

    txt_chave = ft.TextField(
        label="Chave de Ativação",
        label_style=ft.TextStyle(color="#94a3b8", weight=ft.FontWeight.W_500),
        bgcolor="#0c1424",
        border_color="#475569",
        focused_border_color=COR_ACENTO,
        focused_border_width=2,
        border_radius=12,
        width=320,
        color="#f8fafc",
        cursor_color=COR_ACENTO,
        prefix_icon=ft.Icons.VPN_KEY_ROUNDED,
        text_align=ft.TextAlign.CENTER,
        capitalization=ft.TextCapitalization.CHARACTERS,
        on_change=_sync_chave,
    )
    lbl_ativacao = ft.Text("", size=13, text_align=ft.TextAlign.CENTER, width=320)

    def _set_botoes_ativacao(desabilitar: bool):
        btn_guardar.disabled = desabilitar
        btn_entrar.disabled = desabilitar
        try:
            btn_japaguei.disabled = desabilitar
        except Exception:
            pass
        try:
            btn_japaguei_aud.disabled = desabilitar
        except Exception:
            pass

    def _tentar_guardar_chave(_):
        lbl_ativacao.value = "Verificando e gravando…"
        lbl_ativacao.color = "#94a3b8"
        _set_botoes_ativacao(True)
        page.update()
        ok, msg = activate(_texto_chave(), pasta_usuario)
        _set_botoes_ativacao(False)
        if ok:
            lbl_ativacao.value = msg
            lbl_ativacao.color = COR_SUCESSO
            _sync_banner_trial()
            page.update()
            navegar_para(tela_capa)
        else:
            lbl_ativacao.value = msg
            lbl_ativacao.color = COR_ERRO
            page.update()

    def _tentar_somente_entrar(_):
        if _pode_usar_o_app():
            lbl_ativacao.value = ""
            navegar_para(tela_capa)
        else:
            lbl_ativacao.value = "Sem licença e sem auditorias grátis. Introduza a chave ou pague através do Mercado Pago."
            lbl_ativacao.color = COR_ERRO
            page.update()

    btn_guardar = _btn_licenca(
        "GUARDAR CHAVE NESTE APARELHO",
        COR_SUCESSO,
        _tentar_guardar_chave,
        52,
    )
    btn_entrar = _btn_licenca(
        "ABRIR O APP",
        COR_ACENTO,
        _tentar_somente_entrar,
        48,
    )

    def _evt_abrir_mp(_):
        async def _go():
            if MERCADOPAGO_CHECKOUT_URL:
                await page.launch_url(MERCADOPAGO_CHECKOUT_URL)

        page.run_task(_go)

    def _evt_japaguei(_):
        """Após Mercado Pago: apenas validar_acesso (e‑mail + device_id). Fluxo por chave = campo próprio."""

        def _texto_activacao(msg: str, cor: str) -> None:
            lbl_ativacao.value = msg
            lbl_ativacao.color = cor
            try:
                if tela_auditoria.visible:
                    _mostrar_snack(msg, erro=(cor == COR_ERRO))
            except Exception:
                pass

        async def _go():
            _texto_activacao("A verificar pagamento pelo e-mail cadastrado...", COR_TEXTO_SEC)
            _set_botoes_ativacao(True)
            page.update()
            try:
                resposta, erro_val = await asyncio.to_thread(chamar_validar_acesso_apos_checkout)
                if erro_val == "rede":
                    _texto_activacao("Sem ligação. Tente de novo.", COR_ERRO)
                    return
                if erro_val:
                    _texto_activacao(mensagem_falha_rpc_validar_acesso(erro_val), COR_ERRO)
                    return
                if resposta:
                    _sinc_credencial_servidor(resposta)
                if resposta and resposta.get("status") == "liberado":
                    _texto_activacao("Acesso liberado.", COR_SUCESSO)
                    _sync_banner_trial()
                    navegar_para(tela_capa, servidor_liberou_capa=True)
                    return

                parte = ""
                if resposta and resposta.get("status") == "bloqueado":
                    parte = str(resposta.get("mensagem") or "").strip()
                tipo_linha = str(resposta.get("tipo") or "").strip().lower() if resposta else ""

                if tipo_linha == "pago" and parte:
                    msg_final = parte
                elif parte:
                    msg_final = parte
                else:
                    msg_final = (
                        "Pagamento não refletiu ainda nesta conta. Use o mesmo e-mail na app e no "
                        "Mercado Pago; aguarde 1–2 min e tente de novo. Se já pagou, confira no "
                        "Supabase se o webhook marcou «tipo = pago» para esse e-mail."
                    )
                _texto_activacao(msg_final, COR_ERRO)
            finally:
                _set_botoes_ativacao(False)
                page.update()

        page.run_task(_go)

    btn_mp = _btn_licenca(
        "ABRIR PAGAMENTO (MERCADO PAGO)",
        "#0f766e",
        _evt_abrir_mp,
        46,
    )
    btn_mp.visible = bool(MERCADOPAGO_CHECKOUT_URL)

    btn_japaguei = _btn_licenca(
        "JÁ PAGUEI — VERIFICAR ACESSO",
        "#475569",
        _evt_japaguei,
        46,
    )

    def _evt_comprar_licenca(_):
        async def _go():
            try:
                em = get_email_salvo() or ""
                if not email_basico_valido(em):
                    _mostrar_snack(
                        "Defina um e-mail válido na identificação antes de pagar.",
                        erro=True,
                    )
                    return

                ini, err = await asyncio.to_thread(criar_preferencia_mercadopago_via_edge, em)
                if ini:
                    try:
                        await page.launch_url(ini)
                    except Exception as ex:
                        _mostrar_snack(
                            f"Não foi possível abrir o pagamento no navegador: {ex!s}",
                            erro=True,
                        )
                else:
                    _mostrar_snack(_msg_erro_preferencia_mp(err), erro=True)
            except Exception as ex:
                _mostrar_snack(f"Erro inesperado: {ex!s}", erro=True)

        page.run_task(_go)

    btn_comprar_lic_aud = _btn_licenca(
        "COMPRAR LICENÇA (MERCADO PAGO)",
        "#0ea5e9",
        _evt_comprar_licenca,
        46,
    )
    btn_comprar_lic_aud.visible = False
    _ref_btn_compra["aud"] = btn_comprar_lic_aud

    btn_japaguei_aud = _btn_licenca(
        "JÁ PAGUEI — VERIFICAR ACESSO",
        "#475569",
        _evt_japaguei,
        46,
    )
    btn_japaguei_aud.visible = False
    _ref_btn_compra["jap_aud"] = btn_japaguei_aud

    btn_comprar_lic_ativ = _btn_licenca(
        "COMPRAR LICENÇA (MERCADO PAGO)",
        "#0ea5e9",
        _evt_comprar_licenca,
        46,
    )
    btn_comprar_lic_ativ.visible = False
    _ref_btn_compra["ativ"] = btn_comprar_lic_ativ

    img_logo_ativ = _resolver_imagem("icon.png")
    tela_ativacao = ft.SafeArea(
        content=ft.Column(
            [
                ft.Container(expand=True),
                ft.Image(
                    src=img_logo_ativ if img_logo_ativ else "icon.png",
                    width=80, height=80, fit=ft.BoxFit.CONTAIN,
                ) if (img_logo_ativ or _is_android()) else ft.Icon(ft.Icons.VERIFIED_USER_ROUNDED, color=COR_ACENTO, size=60),
                ft.Text("AUDIT CALC", size=26, weight=ft.FontWeight.BOLD, color="#f8fafc"),
                ft.Text("Ativação de Licença", size=14, color="#94a3b8"),
                ft.Container(height=20),
                txt_chave,
                ft.Container(height=10),
                btn_guardar,
                ft.Container(height=8),
                btn_entrar,
                ft.Container(height=6),
                btn_comprar_lic_ativ,
                ft.Container(height=6),
                btn_mp,
                ft.Container(height=6),
                btn_japaguei,
                lbl_ativacao,
                ft.Container(expand=True),
                ft.Text(
                    "Pode testar com até 5 auditorias grátis (botão EXECUTAR AUDITORIA) antes de comprar.",
                    size=11, color="#64748b", text_align=ft.TextAlign.CENTER, width=320,
                ),
                ft.Text(
                    "Com internet: pode guardar uma chave, pagar pelo Mercado Pago e verificar aqui.",
                    size=11, color="#64748b", text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=10),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=6,
        ),
        minimum_padding=ft.Padding(16, 8, 16, 16),
    )

    _ptr_onboarding: list = [None]

    def navegar_para(tela_destino, *, servidor_liberou_capa: bool = False):
        if not email_basico_valido(get_email_salvo()):
            onboarding = _ptr_onboarding[0]
            if onboarding is None:
                return
            tela_destino = onboarding
        elif (
            not _pode_usar_o_app()
            and tela_destino is not tela_ativacao
            and not (servidor_liberou_capa and tela_destino is tela_capa)
        ):
            tela_destino = tela_ativacao

        tela_ativacao.visible = False
        onboarding_ctrl = _ptr_onboarding[0]
        if onboarding_ctrl is not None:
            onboarding_ctrl.visible = False

        tela_capa.visible = False
        tela_auditoria.visible = False
        tela_dados.visible = False
        tela_historico.visible = False
        tela_calculadora.visible = False
        tela_manual.visible = False
        tela_destino.visible = True
        if tela_destino is tela_auditoria:
            _sync_banner_trial()
        elif tela_destino is tela_ativacao:
            _sync_btn_comprar_licenca_visibility()
        page.update()

    async def _revalidar_acesso_ao_voltar_do_mp():
        # Voltar do browser no ecrã de auditoria também deve revalidar (antes só em ativação).
        if not email_basico_valido(get_email_salvo()):
            return
        resposta, erro_val = await asyncio.to_thread(
            lambda: chamar_validar_acesso_apos_checkout(
                max_tentativas=4, intervalo_seg=1.5
            )
        )
        if erro_val or not resposta or resposta.get("status") != "liberado":
            return
        _sinc_credencial_servidor(resposta)
        lbl_ativacao.value = "Pagamento confirmado. Acesso liberado."
        lbl_ativacao.color = COR_SUCESSO
        _sync_banner_trial()
        navegar_para(tela_capa, servidor_liberou_capa=True)
        page.update()

    def _on_app_lifecycle(e: ft.AppLifecycleStateChangeEvent):
        if e.state == ft.AppLifecycleState.RESUME:
            page.run_task(_revalidar_acesso_ao_voltar_do_mp)

    page.on_app_lifecycle_state_change = _on_app_lifecycle

    def _continuar_onboarding_email(_):
        raw = (txt_email_ob.value or "").strip()
        if not email_basico_valido(raw):
            lbl_email_ob_erro.value = "Informe um e-mail válido (deve incluir @ e .)."
            lbl_email_ob_erro.color = COR_ERRO
            page.update()
            return
        if not salvar_email(raw):
            lbl_email_ob_erro.value = "Não foi possível gravar neste dispositivo."
            lbl_email_ob_erro.color = COR_ERRO
            page.update()
            return
        lbl_email_ob_erro.value = ""
        txt_email_ob.read_only = True
        lbl_email_ob_informativo.visible = False
        if _pode_usar_o_app():
            navegar_para(tela_capa)
        else:
            navegar_para(tela_ativacao)

    txt_email_ob = ft.TextField(
        label="E-mail",
        label_style=ft.TextStyle(color=COR_TEXTO_SEC, weight=ft.FontWeight.W_500),
        bgcolor=COR_INPUT,
        border_color=BORDA,
        focused_border_color=COR_ACENTO,
        focused_border_width=2,
        border_radius=12,
        keyboard_type=ft.KeyboardType.EMAIL,
        width=320,
        color=COR_TEXTO,
        cursor_color=COR_ACENTO,
        prefix_icon=None,
    )
    lbl_email_ob_informativo = ft.Text(
        "Este e-mail só pode ser definido uma vez neste telemóvel.",
        size=11,
        color=COR_TEXTO_SEC,
        text_align=ft.TextAlign.CENTER,
        width=300,
        visible=False,
    )

    lbl_email_ob_erro = ft.Text("", size=13, width=320, color=COR_ERRO, text_align=ft.TextAlign.CENTER)

    btn_email_ob = _btn_licenca("CONTINUAR", COR_SUCESSO, _continuar_onboarding_email, 52)

    tela_onboarding_email = ft.SafeArea(
        visible=False,
        content=ft.Column(
            [
                ft.Container(expand=True),
                ft.Text("AUDIT CALC", size=22, weight=ft.FontWeight.BOLD, color=COR_TEXTO),
                ft.Text("Identificação", size=13, color=COR_TEXTO_SEC),
                ft.Container(height=24),
                txt_email_ob,
                lbl_email_ob_informativo,
                lbl_email_ob_erro,
                ft.Container(height=14),
                btn_email_ob,
                ft.Container(expand=True),
                ft.Text(
                    "Precisamos do e-mail para continuar.",
                    size=11,
                    color="#64748b",
                    text_align=ft.TextAlign.CENTER,
                    width=300,
                ),
                ft.Container(height=12),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        ),
        minimum_padding=ft.Padding(16, 8, 16, 16),
    )

    _ptr_onboarding[0] = tela_onboarding_email

    _em_ini = get_email_salvo()
    if email_basico_valido(_em_ini):
        txt_email_ob.value = _em_ini
        txt_email_ob.read_only = True
        lbl_email_ob_informativo.visible = True

    if licenca_aviso:
        lbl_ativacao.value = licenca_aviso
        lbl_ativacao.color = COR_ERRO

    def criar_campo(label, prefixo="R$ ", tipo=ft.KeyboardType.NUMBER, icone=None):
        return ft.TextField(
            label=label,
            label_style=ft.TextStyle(color=COR_TEXTO_SEC, weight=ft.FontWeight.W_500),
            prefix=ft.Text(prefixo) if prefixo else None,
            bgcolor=COR_INPUT,
            border_color=BORDA,
            focused_border_color=COR_ACENTO,
            focused_border_width=2,
            border_radius=12,
            keyboard_type=tipo,
            width=350,
            color=COR_TEXTO,
            cursor_color=COR_ACENTO,
            prefix_icon=icone,
        )

    def formatar_numero(valor_str):
        if not valor_str:
            return 0.0
        valor_str = str(valor_str).strip().replace("R$", "").strip()
        valor_str = valor_str.replace(".", "").replace(",", ".")
        try:
            return float(valor_str)
        except Exception:
            return 0.0

    def _on_change_moeda(e):
        campo = e.control
        raw = "".join(c for c in (campo.value or "") if c.isdigit())
        if not raw:
            campo.value = ""
            page.update()
            return
        centavos = int(raw)
        reais = centavos // 100
        resto = centavos % 100
        parte_inteira = f"{reais:,}".replace(",", ".")
        campo.value = f"{parte_inteira},{resto:02d}"
        page.update()

    def _on_change_taxa(e):
        campo = e.control
        raw = "".join(c for c in (campo.value or "") if c.isdigit())
        if not raw:
            campo.value = ""
            page.update()
            return
        centesimos = int(raw)
        inteiro = centesimos // 100
        decimal = centesimos % 100
        campo.value = f"{inteiro},{decimal:02d}"
        page.update()

    # =====================================================================
    # TELA 1: AUDITORIA (PRINCIPAL)
    # =====================================================================
    img_logo = _resolver_imagem("icon.png")
    titulo_t1 = ft.Column(
        [
            ft.Image(src=img_logo if img_logo else "icon.png", width=48, height=48, fit=ft.BoxFit.CONTAIN)
            if img_logo or _is_android()
            else ft.Icon(ft.Icons.VERIFIED_USER_ROUNDED, color=COR_ACENTO, size=36),
            ft.Container(
                content=ft.Row(
                    [
                        ft.Text("AUDIT CALC", size=22, weight=ft.FontWeight.BOLD, color=COR_TEXTO),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=8,
                ),
                padding=ft.Padding(0, 0, 0, 2),
            ),
            ft.Text("Auditoria de financiamento", size=12, color=COR_TEXTO_SEC),
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=2,
    )

    txt_valor = criar_campo("Valor do Veículo", icone=ft.Icons.DIRECTIONS_CAR_ROUNDED)
    txt_valor.on_change = _on_change_moeda
    txt_entrada = criar_campo("Valor da Entrada", icone=ft.Icons.PAID_ROUNDED)
    txt_entrada.on_change = _on_change_moeda
    txt_taxa_p = criar_campo("Taxa Prometida (% a.m.)", prefixo="", tipo=ft.KeyboardType.NUMBER, icone=ft.Icons.PERCENT_ROUNDED)
    txt_taxa_p.on_change = _on_change_taxa
    txt_parcela = criar_campo("Valor da Parcela Cobrada", icone=ft.Icons.CALENDAR_MONTH_ROUNDED)
    txt_parcela.on_change = _on_change_moeda

    lbl_prazo = ft.Text("Prazo do Financiamento: 48 meses", color=COR_TEXTO_SEC, size=14)
    
    def atualizar_label_prazo(e):
        lbl_prazo.value = f"Prazo do Financiamento: {int(e.control.value)} meses"
        page.update()

    slider_prazo = ft.Slider(min=6, max=72, divisions=66, value=48, active_color=COR_ACENTO, width=350, on_change=atualizar_label_prazo)

    def _formatar_brl(valor: float) -> str:
        centavos_total = round(valor * 100)
        inteiro = centavos_total // 100
        centavos = centavos_total % 100
        parte_inteira = f"{inteiro:,}".replace(",", ".")
        return f"R$ {parte_inteira},{centavos:02d}"

    texto_status = ft.Text("AGUARDANDO ANÁLISE", size=12, weight=ft.FontWeight.BOLD, color=COR_TEXTO_SEC)
    texto_taxa = ft.Text("--.--%", size=40, weight=ft.FontWeight.BOLD, color=COR_ACENTO_ESCURO)
    texto_msg = ft.Text("Preencha os dados e execute", size=14, color=COR_TEXTO_SEC, text_align=ft.TextAlign.CENTER)
    texto_diferenca = ft.Text("", size=13, color=COR_ERRO, text_align=ft.TextAlign.CENTER, weight=ft.FontWeight.W_600, visible=False)

    painel_res = ft.Container(
        content=ft.Column([texto_status, texto_taxa, texto_msg, texto_diferenca], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
        bgcolor="#162032",
        border=ft.Border.all(1, "#64748b"),
        border_radius=18,
        padding=14,
        width=350,
        shadow=_sombra_leve,
    )

    def executar_auditoria(e):
        nonlocal ultimo_resultado
        try:
            v = formatar_numero(txt_valor.value)
            ent = formatar_numero(txt_entrada.value)
            tx_p = formatar_numero(txt_taxa_p.value)
            parc = formatar_numero(txt_parcela.value)
            prazo = int(slider_prazo.value)

            # Taxas da tela 2 (closure: widgets já existem quando o usuário clica)
            t_v = formatar_numero(txt_vistoria.value)
            t_b = formatar_numero(txt_bancaria.value)
            t_r = formatar_numero(txt_registro.value)
            t_s = formatar_numero(txt_seguro.value)

            res = auditar_financiamento(v, ent, tx_p, parc, prazo, (t_v + t_b), t_r, t_s)

            if isinstance(res, ErroAuditoria):
                texto_taxa.value = "--.--%"
                texto_msg.value = res.mensagem
                texto_status.value = "ERRO"
                texto_status.size = 14
                texto_status.color = COR_ERRO
                texto_taxa.color = COR_ERRO
                painel_res.border = ft.Border.all(2, COR_ERRO)
                texto_diferenca.value = ""
                texto_diferenca.visible = False
                page.update()
                return

            usar_fallback_local = False
            resposta_servidor: dict | None = None

            cons, err_c = chamar_consumir_auditoria()
            if err_c == "rede":
                _mostrar_snack("Erro ao conectar com o servidor.", erro=True)
                usar_fallback_local = True
            elif err_c or cons is None:
                usar_fallback_local = True
            elif cons.get("status") == "bloqueado":
                msg_b = cons.get("mensagem") or (
                    "Não é possível registar esta auditoria no servidor. "
                    "Se acabaram as auditorias gratuitas nesta conta, use "
                    "«COMPRAR LICENÇA (MERCADO PAGO)» ou «JÁ PAGUEI»."
                )
                _abrir_tela_compra(str(msg_b))
                return
            elif cons.get("status") == "liberado":
                resposta_servidor = cons
            else:
                usar_fallback_local = True

            if usar_fallback_local and (not is_activated(pasta_usuario)):
                if get_free_audits_remaining(pasta_usuario) <= 0:
                    lbl_ativacao.value = (
                        "Acabaram as auditorias grátis (modo offline). "
                        "Conecte-se ou adquira licença."
                    )
                    lbl_ativacao.color = COR_ERRO
                    navegar_para(tela_ativacao)
                    return

            ultimo_resultado = {
                "cet": f"{res.cet_percent_am:.2f}%",
                "status": res.status,
                "msg": res.mensagem
            }
            texto_taxa.value = ultimo_resultado["cet"]
            texto_msg.value = ultimo_resultado["msg"]
            if res.status == StatusVeredito.OK:
                cor = COR_SUCESSO
                texto_status.value = "CET/Juros OK"
            elif res.status == StatusVeredito.ALERTA:
                cor = COR_ALERTA
                texto_status.value = "CET/Juros Altos"
            else:
                cor = COR_ERRO
                texto_status.value = "CET/Juros ABUSIVOS"

            painel_res.border = ft.Border.all(2, cor)
            texto_status.size = TAM_STATUS_AUDITORIA
            texto_status.color = cor
            texto_taxa.color = cor

            if res.diferenca_mensal is not None and res.diferenca_mensal > 0 and res.status != StatusVeredito.OK:
                diferenca_total = res.diferenca_mensal * prazo
                texto_diferenca.value = f"O Banco está te cobrando {_formatar_brl(diferenca_total)} a mais do que a taxa prometida no financiamento!"
                texto_diferenca.visible = True
            else:
                texto_diferenca.value = ""
                texto_diferenca.visible = False

            if not is_activated(pasta_usuario):
                if usar_fallback_local:
                    record_successful_free_audit(pasta_usuario)
                usos_serv = (
                    None
                    if resposta_servidor is None
                    else resposta_servidor.get("usos_restantes")
                )
                try:
                    u_int = (
                        int(usos_serv)
                        if usos_serv is not None and str(usos_serv).strip() != ""
                        else None
                    )
                except (TypeError, ValueError):
                    u_int = None
                if u_int is None:
                    _sync_banner_trial()
                else:
                    lbl_modo_trial.visible = True
                    lbl_modo_trial.value = (
                        f"Modo avaliação: {u_int} de {FREE_AUDITS_LIMIT} auditorias grátis. "
                        "Depois é necessário licença ou pagamento."
                    )
                    if u_int <= 0:
                        page.update()
                        _abrir_tela_compra(
                            "As 5 auditorias grátis terminaram. "
                            "Toque em «COMPRAR LICENÇA (MERCADO PAGO)» para liberar o acesso."
                        )
                        return

            _sync_btn_comprar_licenca_visibility()
            page.update()
        except Exception as ex:
            texto_msg.value = f"Erro: {str(ex)[:50]}"
            page.update()

    def limpar_dados(e):
        campos_auditoria = [txt_valor, txt_entrada, txt_taxa_p, txt_parcela]
        for c in campos_auditoria: 
            c.value = ""
        slider_prazo.value = 48
        lbl_prazo.value = "Prazo do Financiamento: 48 meses"
        painel_res.border = ft.Border.all(1, "#64748b")
        texto_status.value = "AGUARDANDO ANÁLISE"
        texto_status.size = 12
        texto_status.color = COR_TEXTO_SEC
        texto_taxa.value = "--.--%"
        texto_taxa.color = COR_ACENTO_ESCURO
        texto_msg.value = "Preencha os dados e execute"
        texto_diferenca.value = ""
        texto_diferenca.visible = False
        
        # Limpa campos da Tela 2 se existirem
        if 'txt_loja' in locals():
            txt_loja.value = ""
            txt_vendedor.value = ""
            txt_telefone.value = ""
            txt_modelo.value = ""
            txt_ano.value = ""
            txt_vistoria.value = "600,00"
            txt_bancaria.value = "600,00"
            txt_registro.value = ""
            txt_seguro.value = ""
        page.update()

    # Botões sem o parâmetro 'alignment' problemático
    btn_executar = ft.Button(
        content="EXECUTAR AUDITORIA",
        bgcolor=COR_ACENTO,
        color=COR_TEXTO,
        width=350,
        height=50,
        on_click=executar_auditoria,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12)),
    )

    btn_reset = ft.Button(
        content="RESETAR PESQUISA",
        color=COR_ERRO,
        width=350,
        height=45,
        on_click=limpar_dados,
        bgcolor="transparent",
        style=ft.ButtonStyle(
            side=ft.BorderSide(1, COR_ERRO),
            shape=ft.RoundedRectangleBorder(radius=12),
        ),
    )

    btn_avancar = ft.Button(
        content="DADOS DA PESQUISA ➔",
        bgcolor="#334155",
        color=COR_TEXTO,
        width=350,
        height=50,
        on_click=lambda _: navegar_para(tela_dados),
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12)),
    )

    btn_hist = ft.Button(
        content="HISTÓRICO",
        bgcolor=COR_CARD,
        color=COR_TEXTO,
        width=170,
        height=45,
        on_click=lambda _: abrir_historico(),
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12)),
    )

    btn_calc_nav = ft.Button(
        content="CALCULADORA",
        bgcolor=COR_CARD,
        color=COR_TEXTO,
        width=170,
        height=45,
        on_click=lambda _: navegar_para(tela_calculadora),
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12)),
    )

    img_capa = _resolver_imagem("capa.png")
    img_capa_src = img_capa if img_capa else None

    btn_iniciar_fallback = ft.Button(
        content="INICIAR ANÁLISE",
        bgcolor=COR_ACENTO,
        color=COR_TEXTO,
        width=300,
        height=50,
        on_click=lambda _: navegar_para(tela_auditoria),
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12)),
    )

    if img_capa_src:
        # Desktop: pixels calibrados para janela ~400×750. Android: ancorar pela base
        # (left/right/bottom) — coordenadas fixas em top não batem com CONTAIN + outra altura/DPI.
        # GestureDetector + fundo quase transparente melhora o hit-test em alguns aparelhos.
        _capa_abrir = lambda _: navegar_para(tela_auditoria)
        _capa_hit: ft.Control
        if _is_android():
            _capa_hit = ft.GestureDetector(
                mouse_cursor=ft.MouseCursor.CLICK,
                on_tap=lambda e: _capa_abrir(None),
                left=20,
                right=20,
                bottom=72,
                height=56,
                content=ft.Container(
                    bgcolor="#05FFFFFF",
                    border_radius=16,
                ),
            )
        else:
            _capa_hit = ft.Container(
                left=50,
                top=631,
                width=240,
                height=48,
                border_radius=14,
                on_click=_capa_abrir,
                ink=True,
                ink_color="#3b82f644",
            )
        tela_capa = ft.Stack(
            [
                ft.Container(expand=True, bgcolor="#0f172a"),
                ft.Container(
                    content=ft.Image(src=img_capa_src, fit=ft.BoxFit.CONTAIN),
                    expand=True,
                    padding=ft.padding.only(top=100),
                ),
                _capa_hit,
            ],
            expand=True,
        )
    else:
        tela_capa = ft.Column(
            [
                ft.Container(expand=True),
                ft.Text("AUDIT CALC", size=32, weight=ft.FontWeight.BOLD, color=COR_TEXTO),
                ft.Text("Auditoria de financiamento de veículos", size=14, color=COR_TEXTO_SEC),
                ft.Container(height=20),
                btn_iniciar_fallback,
                ft.Container(expand=True),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        )

    cabecalho_auditoria = ft.Container(
        content=ft.Column(
            [
                titulo_t1,
                ft.Text(
                    "Simule, audite e negocie com mais segurança",
                    size=11,
                    color=COR_TEXTO_SEC,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=4,
        ),
        width=350,
        padding=16,
        border_radius=16,
        bgcolor="#101a2c",
        border=ft.Border.all(1, "#334155"),
    )

    bloco_campos = ft.Container(
        content=ft.Column(
            [
                txt_valor,
                txt_entrada,
                txt_taxa_p,
                txt_parcela,
                lbl_prazo,
                slider_prazo,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
        ),
        width=350,
        padding=16,
        border_radius=16,
        bgcolor="#101a2c",
        border=ft.Border.all(1, "#334155"),
    )

    tela_auditoria = ft.SafeArea(
        content=ft.Column(
            [
                cabecalho_auditoria,
                lbl_modo_trial,
                btn_comprar_lic_aud,
                btn_japaguei_aud,
                bloco_campos,
                btn_executar,
                btn_reset,
                painel_res,
                btn_avancar,
                ft.Row([btn_hist, btn_calc_nav], alignment=ft.MainAxisAlignment.CENTER),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
        ),
        minimum_padding=ft.Padding(16, 8, 16, 16),
    )
    tela_auditoria.visible = False

    # =====================================================================
    # TELA 2: DADOS COMPLEMENTARES
    # =====================================================================
    btn_voltar_t2 = ft.Button(
        content="⬅ VOLTAR",
        color=COR_TEXTO_SEC,
        bgcolor="transparent",
        on_click=lambda _: navegar_para(tela_auditoria),
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
    )

    txt_loja = criar_campo("Loja / Concessionária", "", ft.KeyboardType.TEXT, ft.Icons.STORE_ROUNDED)
    txt_vendedor = criar_campo("Nome do Vendedor", "", ft.KeyboardType.TEXT, ft.Icons.PERSON_ROUNDED)
    txt_telefone = criar_campo("Telefone do Vendedor", "", ft.KeyboardType.PHONE, ft.Icons.PHONE_ROUNDED)
    txt_modelo = criar_campo("Modelo do Veículo", "", ft.KeyboardType.TEXT, ft.Icons.TWO_WHEELER_ROUNDED)
    txt_ano = criar_campo("Ano", "", ft.KeyboardType.NUMBER, ft.Icons.EVENT_ROUNDED)
    txt_modelo.width, txt_ano.width = 230, 110

    txt_vistoria = criar_campo("Tarifa de Registro de Contrato", icone=ft.Icons.FACT_CHECK_ROUNDED)
    txt_vistoria.value = "600,00"
    txt_vistoria.on_change = _on_change_moeda
    txt_bancaria = criar_campo("Tarifa de Avaliação de Bens", icone=ft.Icons.ACCOUNT_BALANCE_ROUNDED)
    txt_bancaria.value = "600,00"
    txt_bancaria.on_change = _on_change_moeda
    txt_registro = criar_campo("Tarifa de Cadastro", icone=ft.Icons.DESCRIPTION_ROUNDED)
    txt_registro.on_change = _on_change_moeda
    txt_seguro = criar_campo("Seguro Prestamista", icone=ft.Icons.SHIELD_ROUNDED)
    txt_seguro.on_change = _on_change_moeda

    _HIST_FILE = ".auditoria_banco.json"

    def _historico_paths():
        """Ordem: pasta da licença; no Android também pastas candidatas (como a licença)."""
        paths: list[str] = []
        seen: set[str] = set()
        if pasta_usuario:
            p = os.path.join(pasta_usuario, _HIST_FILE)
            seen.add(p)
            paths.append(p)
        if _is_android():
            for d in android_storage_candidate_dirs():
                p = os.path.join(d, _HIST_FILE)
                if p not in seen:
                    seen.add(p)
                    paths.append(p)
        return paths

    def _get_banco_path():
        """Caminho principal (para mensagens de erro)."""
        ps = _historico_paths()
        return ps[0] if ps else ""

    def _ler_historico():
        for path in _historico_paths():
            if not path or not os.path.isfile(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                continue
        # Legado: versão antiga gravava "historico.json" com pasta de pacote incorreta
        if _is_android():
            leg_dirs: list[str] = []
            if pasta_usuario:
                leg_dirs.append(pasta_usuario)
            leg_dirs.extend(android_storage_candidate_dirs())
            seen_d: set[str] = set()
            for d in leg_dirs:
                if not d or d in seen_d:
                    continue
                seen_d.add(d)
                leg = os.path.join(d, "historico.json")
                if os.path.isfile(leg):
                    try:
                        with open(leg, "r", encoding="utf-8") as f:
                            return json.load(f)
                    except Exception:
                        continue
        return []

    def _gravar_historico(dados):
        ok_any = False
        for path in _historico_paths():
            if not path:
                continue
            try:
                parent = os.path.dirname(path)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(dados, f, ensure_ascii=False, indent=2)
                ok_any = True
            except OSError:
                pass
        return ok_any

    lbl_salvo = ft.Text("", size=13, text_align=ft.TextAlign.CENTER)

    def _fazer_registro(rascunho=False):
        nonlocal ultimo_resultado
        status_val = texto_status.value if texto_status.value else "SEM ANÁLISE"
        taxa_val = ultimo_resultado["cet"] if ultimo_resultado["cet"] != "--.--%"  else "—"
        return {
            "loja":     txt_loja.value or "N/I",
            "vend":     txt_vendedor.value or "N/I",
            "tel":      txt_telefone.value or "N/I",
            "modelo":   txt_modelo.value or "N/I",
            "ano":      txt_ano.value or "N/I",
            "veiculo":  txt_valor.value or "0",
            "entrada":  txt_entrada.value or "0",
            "taxa_p":   txt_taxa_p.value or "—",
            "parcela":  txt_parcela.value or "0",
            "prazo":    str(int(slider_prazo.value)),
            "reg_contr": txt_vistoria.value or "0",
            "aval_bens": txt_bancaria.value or "0",
            "tar_cad":   txt_registro.value or "0",
            "seguro_p":  txt_seguro.value or "0",
            "taxa":     taxa_val,
            "status":   "(RASCUNHO) " + status_val if rascunho else status_val,
            "data":     str(uuid.uuid4())[:8],
        }

    def salvar_no_banco(e):
        banco = _ler_historico()
        banco.append(_fazer_registro(rascunho=False))
        ok = _gravar_historico(banco)
        if ok:
            lbl_salvo.value = "Histórico salvo! Os dados permanecem na tela até você resetar a pesquisa."
            lbl_salvo.color = COR_SUCESSO
            page.update()
        else:
            lbl_salvo.value = f"Erro ao salvar. Caminho: {_get_banco_path()}"
            lbl_salvo.color = COR_ERRO
            page.update()

    def salvar_rascunho(e):
        banco = _ler_historico()
        banco.append(_fazer_registro(rascunho=True))
        ok = _gravar_historico(banco)
        lbl_salvo.value = "Rascunho salvo! Pode continuar preenchendo." if ok else "Erro ao salvar rascunho."
        lbl_salvo.color = COR_SUCESSO if ok else COR_ERRO
        page.update()

    btn_salvar = ft.Button(
        content="SALVAR HISTÓRICO",
        bgcolor=COR_SUCESSO,
        color=COR_TEXTO,
        expand=True,
        height=50,
        on_click=salvar_no_banco,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12)),
    )

    btn_rascunho = ft.Button(
        content="SALVAR RASCUNHO",
        bgcolor="#334155",
        color=COR_ACENTO,
        expand=True,
        height=50,
        on_click=salvar_rascunho,
        style=ft.ButtonStyle(
            side=ft.BorderSide(1, COR_ACENTO),
            shape=ft.RoundedRectangleBorder(radius=12),
        ),
    )

    row_botoes_salvar = ft.Row(
        [btn_salvar, btn_rascunho],
        spacing=10,
        width=350,
    )

    tela_dados = ft.SafeArea(
        content=ft.Column([
            btn_voltar_t2,
            ft.Text("DADOS COMPLEMENTARES", size=18, weight=ft.FontWeight.BOLD),
            txt_loja,
            txt_vendedor,
            txt_telefone,
            ft.Row([txt_modelo, txt_ano], alignment=ft.MainAxisAlignment.CENTER),
            ft.Text("Taxas e Tarifas", color=COR_TEXTO_SEC),
            txt_vistoria,
            txt_bancaria,
            txt_registro,
            txt_seguro,
            ft.Container(height=10),
            row_botoes_salvar,
            lbl_salvo,
            ft.Button(
                content="MANUAL DE USO",
                bgcolor="#1e293b",
                color=COR_TEXTO_SEC,
                width=350,
                height=42,
                on_click=lambda _: navegar_para(tela_manual),
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12)),
            ),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, scroll=ft.ScrollMode.AUTO),
        minimum_padding=ft.Padding(16, 8, 16, 16),
    )
    tela_dados.visible = False

    # =====================================================================
    # TELA 3: HISTÓRICO
    # =====================================================================
    lista_h = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, height=450, width=350)

    def apagar_um_item_historico(e: ft.ControlEvent):
        idx = e.control.data
        if not isinstance(idx, int):
            return
        banco = _ler_historico()
        if 0 <= idx < len(banco):
            banco.pop(idx)
            _gravar_historico(banco)
        abrir_historico()

    def abrir_historico():
        lista_h.controls.clear()
        try:
            dados = _ler_historico()
            # Mais recente primeiro; índice real em `dados` para apagar com segurança.
            for rev_i, i in enumerate(reversed(dados[-20:])):
                idx_real = len(dados) - 1 - rev_i
                st = i.get("status", "N/A")
                rascunho = "RASCUNHO" in st
                cor_st = COR_ALERTA if rascunho else _cor_historico_status(st)
                borda_cor = COR_ALERTA if rascunho else BORDA
                linhas = [
                    ft.Row(
                        [
                            ft.Text(
                                f"{'📝 RASCUNHO  ' if rascunho else ''}Loja: {i.get('loja','N/I')}",
                                weight=ft.FontWeight.BOLD,
                                color=COR_ALERTA if rascunho else COR_TEXTO,
                                expand=True,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                                icon_size=20,
                                icon_color=COR_ERRO,
                                tooltip="Apagar esta pesquisa",
                                data=idx_real,
                                on_click=apagar_um_item_historico,
                                style=ft.ButtonStyle(padding=6),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                    ft.Text(
                        f"Vendedor: {i.get('vend','N/I')} | Tel: {i.get('tel','N/I')}",
                        size=12, color=COR_TEXTO_SEC,
                    ),
                    ft.Text(
                        f"Veículo: {i.get('modelo','N/I')} {i.get('ano','N/I')}",
                        size=12, color=COR_TEXTO_SEC,
                    ),
                    ft.Text(
                        f"Valor: R$ {i.get('veiculo','0')} | Entrada: R$ {i.get('entrada','0')}",
                        size=12,
                    ),
                    ft.Text(
                        f"Parcela: R$ {i.get('parcela','0')} | Prazo: {i.get('prazo','—')} meses",
                        size=12,
                    ),
                    ft.Text(
                        f"Taxa Prometida: {i.get('taxa_p','—')}% | Taxa Real (CET): {i.get('taxa','—')}",
                        size=12,
                    ),
                    ft.Text(
                        f"Reg. Contrato: R$ {i.get('reg_contr','0')} | Aval. Bens: R$ {i.get('aval_bens','0')}",
                        size=11, color=COR_TEXTO_SEC,
                    ),
                    ft.Text(
                        f"Tar. Cadastro: R$ {i.get('tar_cad','0')} | Seguro Prest.: R$ {i.get('seguro_p','0')}",
                        size=11, color=COR_TEXTO_SEC,
                    ),
                    ft.Text(st, size=11, weight=ft.FontWeight.BOLD, color=cor_st),
                ]
                lista_h.controls.append(
                    ft.Container(
                        content=ft.Column(linhas, spacing=3),
                        bgcolor=COR_INPUT,
                        padding=14,
                        border_radius=12,
                        border=ft.Border.all(1, borda_cor),
                    )
                )
        except Exception:
            pass
        if not lista_h.controls:
            lista_h.controls.append(ft.Text("Nenhum registro encontrado.", color=COR_TEXTO_SEC))
        navegar_para(tela_historico)

    def apagar_historico(e):
        for path in _historico_paths():
            if path and os.path.isfile(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
        abrir_historico()

    btn_limpar_hist = ft.Button(
        content="APAGAR TUDO",
        color=COR_ERRO,
        width=350,
        height=45,
        on_click=apagar_historico,
        bgcolor="transparent",
        style=ft.ButtonStyle(
            side=ft.BorderSide(1, COR_ERRO),
            shape=ft.RoundedRectangleBorder(radius=12),
        ),
    )

    tela_historico = ft.SafeArea(
        content=ft.Column([
            ft.Button(
                content="⬅ VOLTAR",
                color=COR_TEXTO_SEC,
                bgcolor="transparent",
                on_click=lambda _: navegar_para(tela_auditoria),
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
            ),
            ft.Text("HISTÓRICO DE PESQUISAS", size=18, weight=ft.FontWeight.BOLD),
            lista_h,
            ft.Container(height=10),
            btn_limpar_hist,
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, scroll=ft.ScrollMode.AUTO),
        minimum_padding=ft.Padding(16, 8, 16, 16),
    )
    tela_historico.visible = False

    # =====================================================================
    # TELA 4: CALCULADORA
    # =====================================================================
    visor = ft.Text("0", size=35, weight=ft.FontWeight.BOLD)
    expressao = ""
    
    def calc_press(e):
        nonlocal expressao
        val = e.control.data
        if val == "C": 
            expressao = ""
            visor.value = "0"
        elif val == "=":
            try:
                resultado = eval(expressao.replace("x", "*"), {"__builtins__": {}}, {})
                visor.value = str(resultado)
                expressao = str(resultado)
            except:
                visor.value = "Erro"
                expressao = ""
        else:
            expressao = val if expressao == "" else expressao + val
            visor.value = expressao
        page.update()

    def criar_btn_calc(txt, cor=COR_CARD, expandir=1):
        return ft.Container(
            content=ft.Text(txt, size=20, weight=ft.FontWeight.BOLD),
            bgcolor=cor,
            border_radius=12,
            expand=expandir,
            height=65,
            alignment=ft.Alignment(0, 0),
            on_click=calc_press,
            data=txt
        )

    tela_calculadora = ft.SafeArea(
        content=ft.Column([
            ft.Button(
                content="⬅ VOLTAR",
                color=COR_TEXTO_SEC,
                bgcolor="transparent",
                on_click=lambda _: navegar_para(tela_auditoria),
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
            ),
            ft.Text("CALCULADORA", size=18, weight=ft.FontWeight.BOLD),
            ft.Container(
                content=visor,
                bgcolor="#0c1424",
                padding=20,
                border_radius=14,
                border=ft.Border.all(1, BORDA),
                width=350,
                alignment=ft.Alignment(1, 0)
            ),
            ft.Column([
                ft.Row([criar_btn_calc("C", COR_ERRO), criar_btn_calc("/"), criar_btn_calc("x"), criar_btn_calc("-")], spacing=10),
                ft.Row([criar_btn_calc("7"), criar_btn_calc("8"), criar_btn_calc("9"), criar_btn_calc("+")], spacing=10),
                ft.Row([criar_btn_calc("4"), criar_btn_calc("5"), criar_btn_calc("6"), criar_btn_calc("=", COR_ACENTO)], spacing=10),
                ft.Row([criar_btn_calc("1"), criar_btn_calc("2"), criar_btn_calc("3"), criar_btn_calc("0", expandir=2)], spacing=10),
            ], spacing=10, width=350),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        minimum_padding=ft.Padding(16, 8, 16, 16),
    )
    tela_calculadora.visible = False

    # =====================================================================
    # TELA: MANUAL DE USO
    # =====================================================================
    manual_texto = ft.Column(
        [
            ft.Text("MANUAL DE USO", size=18, weight=ft.FontWeight.BOLD, color=COR_TEXTO),
            ft.Container(height=6),
            ft.Text("O que é o Audit Calc?", size=14, weight=ft.FontWeight.BOLD, color=COR_ACENTO),
            ft.Text(
                "Ferramenta de auditoria para financiamento de veículos (carros e motos). "
                "Ela calcula a taxa real (CET) que está sendo cobrada e compara com a taxa "
                "que o vendedor prometeu. Assim você descobre se o negócio é justo antes de assinar.",
                size=12, color=COR_TEXTO_SEC,
            ),
            ft.Container(height=8),
            ft.Text("Licença e passes", size=14, weight=ft.FontWeight.BOLD, color=COR_ACENTO),
            ft.Text(
                "Na primeira abertura você digita a chave recebida após a compra. "
                "A chave fica vinculada a este celular. "
                "Os planos divulgados costumam ser passe semanal ou mensal — "
                "quando o prazo acabar, o app pede uma nova chave. "
                "Com internet, a validade é conferida ao abrir o app.",
                size=12, color=COR_TEXTO_SEC,
            ),
            ft.Container(height=8),
            ft.Text("Como usar — Tela de Auditoria", size=14, weight=ft.FontWeight.BOLD, color=COR_ACENTO),
            ft.Text(
                "Os campos de valor aceitam apenas números. A formatação com vírgula e ponto "
                "é aplicada automaticamente conforme você digita.",
                size=12, color=COR_ALERTA,
            ),
            ft.Text("1. Valor do Veículo: preço total do veículo (digite: 4500000 → aparece 45.000,00).", size=12, color=COR_TEXTO_SEC),
            ft.Text("2. Valor da Entrada: quanto vai pagar de entrada.", size=12, color=COR_TEXTO_SEC),
            ft.Text("3. Taxa Prometida (% a.m.): taxa mensal do vendedor/banco (digite: 199 → aparece 1,99).", size=12, color=COR_TEXTO_SEC),
            ft.Text("4. Valor da Parcela Cobrada: prestação mensal cobrada.", size=12, color=COR_TEXTO_SEC),
            ft.Text("5. Prazo: arraste o controle para escolher a quantidade de meses (6 a 72).", size=12, color=COR_TEXTO_SEC),
            ft.Text("6. Clique em EXECUTAR AUDITORIA.", size=12, color=COR_TEXTO_SEC),
            ft.Container(height=8),
            ft.Text("Entendendo o resultado", size=14, weight=ft.FontWeight.BOLD, color=COR_ACENTO),
            ft.Text(
                "CET/Juros OK (verde): taxa real próxima da prometida. Negócio dentro da média.",
                size=15,
                weight=ft.FontWeight.W_600,
                color=COR_SUCESSO,
            ),
            ft.Text(
                "CET/Juros Altos (amarelo): taxa acima do esperado. Negocie melhores condições antes de assinar.",
                size=15,
                weight=ft.FontWeight.W_600,
                color=COR_ALERTA,
            ),
            ft.Text(
                "CET/Juros ABUSIVOS (vermelho): taxa muito acima do prometido. Possível abuso (Art. 39 CDC).",
                size=15,
                weight=ft.FontWeight.W_600,
                color=COR_ERRO,
            ),
            ft.Text("O número grande exibido é a taxa real mensal (CET) calculada a partir da parcela informada.", size=12, color=COR_TEXTO_SEC),
            ft.Container(height=8),
            ft.Text("Dados Complementares", size=14, weight=ft.FontWeight.BOLD, color=COR_ACENTO),
            ft.Text(
                "Registre: loja, vendedor, telefone, modelo, ano e taxas adicionais "
                "(vistoria, avaliação bancária e taxa de registro). "
                "Todos os dados da tela de auditoria também são salvos automaticamente.",
                size=12, color=COR_TEXTO_SEC,
            ),
            ft.Text(
                "Importante: as taxas adicionais variam de estado para estado e conforme o banco. "
                "Consulte os valores antes de executar a auditoria — eles influenciam no cálculo da parcela justa.",
                size=12, weight=ft.FontWeight.W_500, color=COR_TEXTO,
            ),
            ft.Container(height=4),
            ft.Text("Salvando pesquisas:", size=13, weight=ft.FontWeight.BOLD, color=COR_ACENTO),
            ft.Text(
                "SALVAR NO HISTÓRICO — salva o registro completo e retorna à tela principal.",
                size=12, color=COR_TEXTO_SEC,
            ),
            ft.Text(
                "SALVAR RASCUNHO — salva os dados parciais sem fechar o formulário. "
                "Útil para registrar uma negociação em andamento. O rascunho fica destacado em amarelo no histórico.",
                size=12, color=COR_TEXTO_SEC,
            ),
            ft.Container(height=8),
            ft.Text("Histórico", size=14, weight=ft.FontWeight.BOLD, color=COR_ACENTO),
            ft.Text(
                "Exibe as últimas 20 pesquisas salvas com todos os dados: veículo, valores, "
                "taxas, resultado da auditoria e informações do vendedor. "
                "Rascunhos aparecem marcados em amarelo. "
                "Útil para comparar propostas de diferentes lojas.",
                size=12, color=COR_TEXTO_SEC,
            ),
            ft.Container(height=8),
            ft.Text("Calculadora", size=14, weight=ft.FontWeight.BOLD, color=COR_ACENTO),
            ft.Text("Calculadora simples para contas rápidas durante a negociação.", size=12, color=COR_TEXTO_SEC),
            ft.Container(height=8),
            ft.Text("Dica de negociação", size=14, weight=ft.FontWeight.BOLD, color=COR_ACENTO),
            ft.Text(
                "Execute a auditoria na frente do vendedor. Se o resultado aparecer vermelho, "
                "mostre a tela e peça revisão das condições. A transparência costuma melhorar a proposta na hora.",
                size=12, color=COR_TEXTO_SEC,
            ),
            ft.Container(height=12),
            ft.Container(
                content=ft.Text("COBRANÇAS DEVIDAS E INDEVIDAS", size=15, weight=ft.FontWeight.BOLD, color=COR_TEXTO),
                bgcolor="#1e293b",
                padding=10,
                border_radius=10,
                width=350,
                alignment=ft.Alignment(0, 0),
            ),
            ft.Container(height=8),
            ft.Text("✅  O que é DEVIDO (o banco pode cobrar)", size=14, weight=ft.FontWeight.BOLD, color=COR_SUCESSO),
            ft.Container(height=4),
            ft.Text("IOF", size=12, weight=ft.FontWeight.BOLD, color=COR_ACENTO),
            ft.Text(
                "Obrigatório. 0,38% fixo + 0,0082% ao dia (máximo total de 3,38%).",
                size=12, color=COR_TEXTO_SEC,
            ),
            ft.Text("Tarifa de Cadastro (TC)", size=12, weight=ft.FontWeight.BOLD, color=COR_ACENTO),
            ft.Text(
                "Devida apenas no primeiro contato com aquele banco. "
                "Serve para pesquisar seu nome nos órgãos de proteção ao crédito.",
                size=12, color=COR_TEXTO_SEC,
            ),
            ft.Text("Tarifa de Registro de Contrato", size=12, weight=ft.FontWeight.BOLD, color=COR_ACENTO),
            ft.Text(
                "Devida para pagar o registro da alienação no Detran. "
                "O banco repassa esse custo operacional. Média: R$ 600 (SP).",
                size=12, color=COR_TEXTO_SEC,
            ),
            ft.Text("Tarifa de Avaliação de Bens", size=12, weight=ft.FontWeight.BOLD, color=COR_ACENTO),
            ft.Text(
                "Devida em carros usados. Custeia o perito que avalia se o "
                "veículo serve como garantia para o banco. Média: R$ 500.",
                size=12, color=COR_TEXTO_SEC,
            ),
            ft.Text("Seguro Prestamista", size=12, weight=ft.FontWeight.BOLD, color=COR_ACENTO),
            ft.Text(
                "Devido apenas se você quiser. Protege o pagamento em caso de "
                "morte ou desemprego. Você NÃO é obrigado a aceitar.",
                size=12, color=COR_TEXTO_SEC,
            ),
            ft.Container(height=12),
            ft.Text("❌  O que é INDEVIDO (o banco NÃO pode cobrar)", size=14, weight=ft.FontWeight.BOLD, color=COR_ERRO),
            ft.Container(height=4),
            ft.Text("Tarifa de Cadastro para quem já é cliente", size=12, weight=ft.FontWeight.BOLD, color=COR_ERRO),
            ft.Text(
                "Se você já tem cartão, conta ou outro financiamento no banco, "
                "cobrar a TC de novo é ilegal.",
                size=12, color=COR_TEXTO_SEC,
            ),
            ft.Text("Venda Casada de Seguro", size=12, weight=ft.FontWeight.BOLD, color=COR_ERRO),
            ft.Text(
                "Obrigar você a fechar o seguro do banco para liberar o crédito. "
                "Você tem o direito de escolher outra seguradora ou nenhuma.",
                size=12, color=COR_TEXTO_SEC,
            ),
            ft.Text("Serviços de Terceiros (Taxa de Retorno)", size=12, weight=ft.FontWeight.BOLD, color=COR_ERRO),
            ft.Text(
                "Taxa genérica que lojas cobram para ganhar comissão extra do banco. "
                "O STJ proibiu se o serviço não for discriminado e comprovado.",
                size=12, color=COR_TEXTO_SEC,
            ),
            ft.Text("Comissão de Correspondente", size=12, weight=ft.FontWeight.BOLD, color=COR_ERRO),
            ft.Text(
                "Taxa por \"ter feito o meio de campo\" entre você e o banco. "
                "O banco é quem deve pagar a loja, não você.",
                size=12, color=COR_TEXTO_SEC,
            ),
            ft.Text("Taxa de Emissão de Carnê (TEC) / Boleto", size=12, weight=ft.FontWeight.BOLD, color=COR_ERRO),
            ft.Text(
                "Proibida pelo Banco Central. O custo de enviar a cobrança é do banco.",
                size=12, color=COR_TEXTO_SEC,
            ),
            ft.Text("Taxa de Abertura de Crédito (TAC)", size=12, weight=ft.FontWeight.BOLD, color=COR_ERRO),
            ft.Text(
                "Foi substituída pela Tarifa de Cadastro. Se aparecerem as duas, "
                "é cobrança duplicada.",
                size=12, color=COR_TEXTO_SEC,
            ),
            ft.Text("Taxa de Substituição de Garantia", size=12, weight=ft.FontWeight.BOLD, color=COR_ERRO),
            ft.Text(
                "Cobrar para trocar o carro do financiamento. Só pode ser cobrada "
                "se houver gasto real comprovado pelo banco.",
                size=12, color=COR_TEXTO_SEC,
            ),
        ],
        spacing=4,
        scroll=ft.ScrollMode.AUTO,
        width=350,
    )

    tela_manual = ft.SafeArea(
        content=ft.Column(
            [
                ft.Button(
                    content="⬅ VOLTAR",
                    color=COR_TEXTO_SEC,
                    bgcolor="transparent",
                    on_click=lambda _: navegar_para(tela_dados),
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                ),
                manual_texto,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            scroll=ft.ScrollMode.AUTO,
        ),
        minimum_padding=ft.Padding(16, 8, 16, 16),
    )
    tela_manual.visible = False

    # Rota inicial: e-mail → validação no Supabase → capa ou ativação
    def _abrir_fallback_sem_servidor():
        if _pode_usar_o_app():
            navegar_para(tela_capa)
        else:
            navegar_para(tela_ativacao)

    if not email_basico_valido(get_email_salvo()):
        navegar_para(tela_onboarding_email)
    else:
        resposta, erro_val = chamar_validar_acesso()

        if erro_val == "rede":
            _mostrar_snack("Erro ao conectar com o servidor.", erro=True)
            _abrir_fallback_sem_servidor()

        elif erro_val == "sem_email":
            navegar_para(tela_onboarding_email)

        elif erro_val or resposta is None:
            _abrir_fallback_sem_servidor()

        elif resposta.get("status") == "bloqueado":
            _sinc_credencial_servidor(resposta)
            msg_serv = resposta.get("mensagem") or "Acesso bloqueado."
            lbl_ativacao.value = str(msg_serv)
            lbl_ativacao.color = COR_ERRO
            navegar_para(tela_ativacao)

        elif resposta.get("status") == "liberado":
            _sinc_credencial_servidor(resposta)
            navegar_para(tela_capa, servidor_liberou_capa=True)

        else:
            _abrir_fallback_sem_servidor()

    _sync_banner_trial()

    def _voltar_android(e):
        if tela_onboarding_email.visible and not email_basico_valido(get_email_salvo()):
            return
        if tela_manual.visible:
            navegar_para(tela_dados)
        elif tela_calculadora.visible or tela_historico.visible or tela_dados.visible:
            navegar_para(tela_auditoria)
        elif tela_auditoria.visible:
            navegar_para(tela_capa)

    page.on_back_button_pressed = _voltar_android
    page.add(
        tela_onboarding_email,
        tela_ativacao,
        tela_capa,
        tela_auditoria,
        tela_dados,
        tela_historico,
        tela_calculadora,
        tela_manual,
    )

if __name__ == "__main__":
    ft.run(main)