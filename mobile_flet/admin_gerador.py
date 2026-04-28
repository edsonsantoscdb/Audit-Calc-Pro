"""
Ferramenta interna: gera licenças e grava no Supabase.
Instale SOMENTE no seu celular. Usa a chave service_role (nunca no app dos clientes).

Build APK (na pasta CALCULADORA):
  python scripts/run_build_gerador.py
 Saída: build\apk\audit_gerador.apk

Service role: Supabase → Project Settings → API → service_role (secret).

Coluna opcional no Supabase (SQL, uma vez):
  alter table licencas add column if not exists email text;
"""
from __future__ import annotations

import json
import os
import secrets
import string
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import flet as ft

SUPABASE_URL = "https://ynixfnrjxuqdhzcralvo.supabase.co"
_KEY_FILE = ".auditcalc_admin_service_role.txt"


def _is_android():
    return hasattr(sys, "getandroidapilevel") or "android" in sys.platform


def _data_dir():
    """Diretório gravável (Android)."""
    if _is_android():
        candidates = [
            os.environ.get("HOME", ""),
            os.environ.get("TMPDIR", ""),
            "/data/local/tmp",
            tempfile.gettempdir(),
        ]
        for d in candidates:
            if d and os.path.isdir(d):
                try:
                    test = os.path.join(d, ".write_test_admin")
                    with open(test, "w", encoding="utf-8") as f:
                        f.write("ok")
                    os.remove(test)
                    return d
                except OSError:
                    continue
        td = tempfile.gettempdir()
        return td if td else ""
    return os.path.expanduser("~")


def _candidate_paths():
    """Ordem: pasta do app; depois /tmp do sistema."""
    paths = []
    base = _data_dir()
    if base:
        paths.append(os.path.join(base, _KEY_FILE))
    paths.append(os.path.join(tempfile.gettempdir(), _KEY_FILE))
    return paths


def _load_service_role() -> str:
    for p in _candidate_paths():
        if p and os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    s = f.read().strip()
                    if s:
                        return s
            except OSError:
                continue
    return ""


def _save_service_role(key: str) -> bool:
    key = key.strip()
    if not key:
        return False
    for p in _candidate_paths():
        if not p:
            continue
        try:
            d = os.path.dirname(p)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(key)
            return True
        except OSError:
            continue
    return False


def _gerar_chave() -> str:
    alfa = string.ascii_uppercase + string.digits
    parts = ["".join(secrets.choice(alfa) for _ in range(4)) for _ in range(3)]
    return f"AC-{'-'.join(parts)}"


def _inserir_licenca(
    service_role: str,
    chave: str,
    comprador: str,
    expira_em_iso: str | None,
    email: str | None = None,
) -> tuple[bool, str]:
    url = f"{SUPABASE_URL}/rest/v1/licencas"
    payload: dict = {"chave": chave, "ativo": True, "comprador": comprador or "N/I"}
    if expira_em_iso is None:
        payload["expira_em"] = None
    else:
        payload["expira_em"] = expira_em_iso
    em = (email or "").strip()
    if em:
        payload["email"] = em
    headers = {
        "apikey": service_role,
        "Authorization": f"Bearer {service_role}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

    ok, err = _tentar_post(url, payload, headers)
    if ok:
        return True, _email_salvo_msg(em)

    if em and _erro_indica_coluna_email(err):
        payload.pop("email", None)
        ok2, err2 = _tentar_post(url, payload, headers)
        if ok2:
            return True, (
                "Licença criada, mas o campo e-mail NÃO foi salvo "
                "(a coluna 'email' não existe na tabela). "
                "Rode no Supabase SQL Editor:\n"
                "ALTER TABLE licencas ADD COLUMN IF NOT EXISTS email TEXT;\n"
                f"E-mail do cliente (anote manualmente): {em}"
            )
        return False, err2
    return False, err


def _tentar_post(url: str, payload: dict, headers: dict) -> tuple[bool, str]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        req = Request(url, data=body, headers=headers, method="POST")
        with urlopen(req, timeout=20) as resp:
            resp.read()
        return True, ""
    except HTTPError as e:
        try:
            err = e.read().decode()
        except Exception:
            err = str(e)
        return False, err[:500]
    except URLError as e:
        return False, f"Sem rede: {e}"
    except Exception as e:
        return False, str(e)


def _erro_indica_coluna_email(err: str) -> bool:
    lower = err.lower()
    return "email" in lower and ("column" in lower or "coluna" in lower or "undefined" in lower or "42703" in lower)


def _email_salvo_msg(email: str | None) -> str:
    if email:
        return f"E-mail '{email}' salvo junto com a licença."
    return ""


def _listar_licencas(service_role: str, limit: int = 200) -> tuple[list[dict] | None, str]:
    """GET em licencas (service_role). Retorna (linhas, mensagem_erro)."""
    q = urlencode(
        {
            "select": "*",
            "order": "created_at.desc",
            "limit": str(limit),
        }
    )
    url = f"{SUPABASE_URL}/rest/v1/licencas?{q}"
    headers = {
        "apikey": service_role,
        "Authorization": f"Bearer {service_role}",
    }
    try:
        req = Request(url, headers=headers, method="GET")
        with urlopen(req, timeout=25) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        if not isinstance(data, list):
            return None, "Resposta inválida do servidor."
        return data, ""
    except HTTPError as e:
        try:
            err = e.read().decode()
        except Exception:
            err = str(e)
        return None, err[:500]
    except URLError as e:
        return None, f"Sem rede: {e}"
    except Exception as e:
        return None, str(e)


def _btn_acao(texto: str, cor_fundo: str, cor_texto: str, ao_clicar, altura: int = 52):
    """Container + on_click: em alguns Android ft.Button não dispara; isto é mais confiável."""
    return ft.Container(
        content=ft.Text(texto, color=cor_texto, weight=ft.FontWeight.W_600, size=15, text_align=ft.TextAlign.CENTER),
        bgcolor=cor_fundo,
        border_radius=12,
        height=altura,
        width=400,
        alignment=ft.Alignment(0, 0),
        on_click=ao_clicar,
        ink=True,
        ink_color="#40ffffff",
        padding=ft.padding.symmetric(horizontal=12, vertical=14),
    )


def _btn_acao_com_label(
    label: ft.Text,
    cor_fundo: str,
    cor_texto: str,
    ao_clicar,
    altura: int = 52,
):
    """Igual a _btn_acao, mas o texto do botão pode ser atualizado depois."""
    return ft.Container(
        content=label,
        bgcolor=cor_fundo,
        border_radius=12,
        height=altura,
        width=400,
        alignment=ft.Alignment(0, 0),
        on_click=ao_clicar,
        ink=True,
        ink_color="#40ffffff",
        padding=ft.padding.symmetric(horizontal=12, vertical=14),
    )


_PLANO_TEXTO = {
    "7": "Semanal (7 dias)",
    "30": "Mensal (30 dias)",
    "0": "Parceiro — vitalício (não anunciar)",
}


def _formatar_validade_legivel(exp_iso: str | None) -> str:
    if exp_iso is None:
        return "vitalícia"
    s = str(exp_iso).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%d/%m/%Y %H:%M") + " UTC"
    except ValueError:
        return str(exp_iso)[:19].replace("T", " ")


def _montar_texto_licenca_para_email(
    cliente: str,
    chave: str,
    plano_key: str,
    exp_iso: str | None,
    email_cli: str | None,
) -> str:
    plano_txt = _PLANO_TEXTO.get(plano_key or "7", plano_key or "")
    validade = _formatar_validade_legivel(exp_iso)
    linhas = [
        f"Olá, {cliente}.",
        "",
        "Segue sua chave de licença do Audit Calc:",
        "",
        f"Chave: {chave}",
        f"Plano: {plano_txt}",
        f"Validade: {validade}",
    ]
    em = (email_cli or "").strip()
    if em:
        linhas.append(f"E-mail cadastrado: {em}")
    linhas.extend(
        [
            "",
            "Para ativar, abra o aplicativo, cole a chave e toque em ativar.",
        ]
    )
    return "\n".join(linhas)


def _copiar_texto_tkinter(texto: str) -> bool:
    """Copia para a área de transferência no desktop (Windows/macOS/Linux com Tk)."""
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(texto)
        root.update()
        root.destroy()
        return True
    except Exception:
        return False


def _infer_plano_key_de_row(row: dict) -> str:
    """Infere 7/30/0 a partir de expira_em e created_at (listagem não traz o plano)."""
    exp = row.get("expira_em")
    if exp is None:
        return "0"
    criado = row.get("created_at")
    if not criado:
        return "7"
    try:
        exp_s = str(exp).replace("Z", "+00:00")
        cr_s = str(criado).replace("Z", "+00:00")
        exp_dt = datetime.fromisoformat(exp_s)
        cr_dt = datetime.fromisoformat(cr_s)
        if exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
        if cr_dt.tzinfo is None:
            cr_dt = cr_dt.replace(tzinfo=timezone.utc)
        dias = (exp_dt - cr_dt).days
        if 5 <= dias <= 9:
            return "7"
        if 25 <= dias <= 35:
            return "30"
    except (ValueError, TypeError, OSError):
        pass
    return "7"


def _texto_licenca_de_row(row: dict) -> str:
    """Monta o mesmo texto de e-mail a partir de uma linha da API / licenças."""
    cliente = str(row.get("comprador") or "N/I").strip()
    chave = str(row.get("chave") or "").strip()
    exp_raw = row.get("expira_em")
    exp_iso: str | None = str(exp_raw) if exp_raw is not None else None
    email = str(row.get("email") or "").strip() or None
    plano_key = _infer_plano_key_de_row(row)
    return _montar_texto_licenca_para_email(cliente, chave, plano_key, exp_iso, email)


def main(page: ft.Page):
    page.title = "Audit Gerador"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#0f172a"
    page.padding = 16

    cor_acento = "#3b82f6"
    cor_ok = "#22c55e"
    cor_erro = "#f87171"
    cor_sec = "#94a3b8"

    # Android: value do campo pode atrasar; espelhamos em on_change
    buffer_role = {"texto": ""}

    def _sync_buffer(e):
        buffer_role["texto"] = (e.control.value or "") if e.control else ""

    # Sem password: no Android, senha + colar às vezes não atualiza value até blur
    txt_role = ft.TextField(
        label="Service role (cole uma vez; fica só neste aparelho)",
        password=False,
        multiline=False,
        min_lines=1,
        max_lines=1,
        bgcolor="#0c1424",
        border_color="#475569",
        focused_border_color=cor_acento,
        width=400,
        color="#f8fafc",
        text_size=12,
        on_change=_sync_buffer,
    )
    txt_comprador = ft.TextField(
        label="Cliente (nome ou identificação)",
        bgcolor="#0c1424",
        border_color="#475569",
        focused_border_color=cor_acento,
        width=400,
        color="#f8fafc",
    )
    txt_email = ft.TextField(
        label="E-mail do cliente (opcional — para você copiar e enviar a chave)",
        hint_text="exemplo@email.com",
        keyboard_type=ft.KeyboardType.EMAIL,
        bgcolor="#0c1424",
        border_color="#475569",
        focused_border_color=cor_acento,
        width=400,
        color="#f8fafc",
    )
    dd_plano = ft.Dropdown(
        label="Plano",
        width=400,
        options=[
            ft.dropdown.Option("7", "Semanal (7 dias)"),
            ft.dropdown.Option("30", "Mensal (30 dias)"),
            ft.dropdown.Option("0", "Parceiro — vitalício (não anunciar)"),
        ],
        value="7",
        bgcolor="#0c1424",
        border_color="#475569",
        focused_border_color=cor_acento,
        color="#f8fafc",
    )
    lbl_resultado = ft.Text("", size=14, selectable=True, width=400)
    lbl_chave = ft.Text("", size=18, weight=ft.FontWeight.BOLD, color=cor_ok, selectable=True)
    lbl_copia_feedback = ft.Text("", size=12, color=cor_sec, width=400, text_align=ft.TextAlign.CENTER)

    ultima_licenca: dict | None = None

    lbl_lista_status = ft.Text("", size=12, color=cor_sec, width=400, text_align=ft.TextAlign.CENTER)
    col_lista = ft.Column(
        scroll=ft.ScrollMode.AUTO,
        expand=True,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=0,
    )

    saved = _load_service_role()
    if saved:
        txt_role.value = saved
        buffer_role["texto"] = saved

    txt_btn_salvar_role = ft.Text(
        "Salvar chave neste aparelho",
        color="#f8fafc",
        weight=ft.FontWeight.W_600,
        size=15,
        text_align=ft.TextAlign.CENTER,
    )

    def _texto_service_role() -> str:
        a = (buffer_role.get("texto") or "").strip()
        b = (txt_role.value or "").strip()
        return a if len(a) >= len(b) else b

    def _aplicar_trava_chave_admin(travada: bool) -> None:
        txt_role.password = travada
        txt_role.read_only = travada
        txt_btn_salvar_role.value = (
            "Chave salva nesse aparelho" if travada else "Salvar chave neste aparelho"
        )

    def salvar_chave(_):
        chave_txt = _texto_service_role()
        if not chave_txt:
            lbl_resultado.value = "Cole a service role primeiro."
            lbl_resultado.color = cor_erro
            page.update()
            return
        if txt_role.read_only:
            return
        ok = _save_service_role(chave_txt)
        if ok:
            lbl_resultado.value = "Chave salva neste aparelho."
            lbl_resultado.color = cor_ok
            _aplicar_trava_chave_admin(True)
        else:
            lbl_resultado.value = "Não foi possível gravar em arquivo. Use GERAR mesmo assim (usa o texto colado)."
            lbl_resultado.color = cor_erro
        page.update()

    if saved:
        _aplicar_trava_chave_admin(True)

    async def _copiar_flet_async(texto: str, lista: bool) -> None:
        """Fallback Clipboard Flet quando Tk não está disponível."""
        try:
            clip = ft.Clipboard()
            await clip.set(texto)
            if lista:
                lbl_lista_status.value = "Texto da licença copiado."
                lbl_lista_status.color = cor_ok
            else:
                lbl_copia_feedback.value = "Texto da licença copiado."
                lbl_copia_feedback.color = cor_ok
        except Exception:
            if lista:
                lbl_lista_status.value = "Não foi possível copiar. Copie a chave manualmente."
                lbl_lista_status.color = cor_erro
            else:
                lbl_copia_feedback.value = "Não foi possível copiar. Copie a chave manualmente."
                lbl_copia_feedback.color = cor_erro
        page.update()

    def copiar_texto_generico(texto: str, *, lista: bool) -> None:
        """Tk no desktop; Flet Clipboard no APK. `lista=True` atualiza o rótulo da aba Licenças."""
        if _copiar_texto_tkinter(texto):
            if lista:
                lbl_lista_status.value = "Texto da licença copiado."
                lbl_lista_status.color = cor_ok
            else:
                lbl_copia_feedback.value = "Texto da licença copiado."
                lbl_copia_feedback.color = cor_ok
            page.update()
            return
        page.run_task(_copiar_flet_async, texto, lista)

    def _card_licenca(row: dict) -> ft.Control:
        chave = str(row.get("chave") or "")
        comp = str(row.get("comprador") or "")
        exp = row.get("expira_em")
        ativo = row.get("ativo")
        criado = row.get("created_at") or ""
        aid = row.get("android_id") or row.get("device_id")
        if exp is None:
            exp_txt = "Vitalício / sem data"
        else:
            exp_txt = str(exp)[:19].replace("T", " ")
        ativo_txt = "Ativa" if ativo else "Inativa"
        em = str(row.get("email") or "").strip()
        vinculada = bool(aid)
        cor_borda = cor_ok if ativo and not vinculada else ("#475569" if ativo else cor_erro)
        linhas: list[ft.Control] = [
            ft.Text(chave, weight=ft.FontWeight.BOLD, size=14, color=cor_ok if ativo else cor_erro, selectable=True),
            ft.Text(f"Cliente: {comp}", size=12, color="#e2e8f0"),
        ]
        if em:
            linhas.append(ft.Text(f"E-mail: {em}", size=12, color="#93c5fd", selectable=True))
        linhas.append(ft.Text(f"Expira: {exp_txt}  ·  {ativo_txt}", size=11, color=cor_sec))
        if criado:
            linhas.append(ft.Text(f"Criada: {str(criado)[:19].replace('T', ' ')}", size=10, color=cor_sec))
        if aid:
            linhas.append(ft.Text(f"Android ID: {str(aid)[:48]}…" if len(str(aid)) > 48 else f"Android ID: {aid}", size=10, color=cor_sec))
        if vinculada:
            linhas.append(ft.Text("✔ Já vinculada a um aparelho", size=10, color="#facc15"))

        def _copiar_este_card(_):
            copiar_texto_generico(_texto_licenca_de_row(row), lista=True)

        btn_copiar_card = ft.Container(
            content=ft.Text(
                "COPIAR TEXTO",
                color="#f8fafc",
                weight=ft.FontWeight.W_600,
                size=12,
                text_align=ft.TextAlign.CENTER,
            ),
            bgcolor=cor_acento,
            border_radius=8,
            height=36,
            padding=ft.padding.symmetric(horizontal=14, vertical=8),
            alignment=ft.Alignment(0, 0),
            on_click=_copiar_este_card,
            ink=True,
            ink_color="#40ffffff",
        )
        linhas.append(ft.Container(height=4))
        linhas.append(
            ft.Row(
                [btn_copiar_card],
                alignment=ft.MainAxisAlignment.START,
                width=400,
            )
        )

        return ft.Container(
            content=ft.Column(linhas, tight=True, spacing=4),
            padding=12,
            margin=ft.margin.only(bottom=8),
            bgcolor="#1e293b",
            border=ft.Border.all(1, cor_borda),
            border_radius=10,
            width=400,
        )

    def carregar_lista(_=None):
        role = _texto_service_role()
        if not role:
            lbl_lista_status.value = "Cole a service role na aba Gerar."
            lbl_lista_status.color = cor_erro
            col_lista.controls.clear()
            page.update()
            return
        lbl_lista_status.value = "Carregando…"
        lbl_lista_status.color = cor_sec
        col_lista.controls.clear()
        page.update()
        linhas, err = _listar_licencas(role)
        if err:
            lbl_lista_status.value = f"Erro: {err}"
            lbl_lista_status.color = cor_erro
            page.update()
            return
        lbl_lista_status.value = f"{len(linhas)} licença(s) (mais recentes primeiro)."
        lbl_lista_status.color = cor_ok
        col_lista.controls = [_card_licenca(r) for r in linhas]
        page.update()

    def ao_mudar_aba(e: ft.ControlEvent):
        try:
            idx = int(e.data) if e.data is not None else tabs_ctrl.selected_index
        except (TypeError, ValueError):
            idx = tabs_ctrl.selected_index
        if idx == 1:
            carregar_lista()

    def copiar_texto_licenca(_):
        if not ultima_licenca:
            lbl_copia_feedback.value = "Gere uma licença primeiro."
            lbl_copia_feedback.color = cor_erro
            page.update()
            return
        texto = _montar_texto_licenca_para_email(
            ultima_licenca["cliente"],
            ultima_licenca["chave"],
            ultima_licenca["plano_key"],
            ultima_licenca["exp_iso"],
            ultima_licenca.get("email") or None,
        )
        copiar_texto_generico(texto, lista=False)

    btn_copiar_licenca = ft.Container(
        content=_btn_acao(
            "COPIAR TEXTO DA LICENÇA",
            "#334155",
            cor_acento,
            copiar_texto_licenca,
            48,
        ),
        visible=False,
        width=400,
    )

    def gerar(_):
        nonlocal ultima_licenca
        role = _texto_service_role()
        if not role:
            lbl_resultado.value = "Cole a service role acima (o botão Salvar é opcional)."
            lbl_resultado.color = cor_erro
            page.update()
            return
        _save_service_role(role)
        comprador = (txt_comprador.value or "").strip() or "N/I"
        email_cli = (txt_email.value or "").strip() or None
        plano = dd_plano.value or "7"
        chave = _gerar_chave()

        if plano == "0":
            exp_iso = None
        else:
            dias = int(plano)
            fim = datetime.now(timezone.utc) + timedelta(days=dias)
            fim = fim.replace(hour=23, minute=59, second=59, microsecond=0)
            exp_iso = fim.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00"

        lbl_resultado.value = "Enviando..."
        lbl_resultado.color = cor_sec
        lbl_chave.value = ""
        lbl_copia_feedback.value = ""
        ultima_licenca = None
        btn_copiar_licenca.visible = False
        page.update()

        ok, msg_extra = _inserir_licenca(role, chave, comprador, exp_iso, email_cli)
        if ok:
            aviso_email = ""
            if msg_extra and "NÃO foi salvo" in msg_extra:
                aviso_email = f"\n⚠️ {msg_extra}"
                lbl_resultado.color = cor_erro
            else:
                aviso_email = f"\n{msg_extra}" if msg_extra else ""
                lbl_resultado.color = cor_ok
            lbl_resultado.value = (
                "Registrado no Supabase. Use o botão abaixo para copiar o texto e colar no Gmail."
                f"{aviso_email}"
            )
            lbl_chave.value = chave
            ultima_licenca = {
                "cliente": comprador,
                "chave": chave,
                "plano_key": plano,
                "exp_iso": exp_iso,
                "email": (email_cli or "").strip(),
            }
            btn_copiar_licenca.visible = True
            carregar_lista()
        else:
            lbl_resultado.value = f"Erro: {msg_extra}"
            lbl_resultado.color = cor_erro
        page.update()

    tab_gerar = ft.Column(
        [
            ft.Text("AUDIT GERADOR", size=22, weight=ft.FontWeight.BOLD, color="#f8fafc"),
            ft.Text("Uso exclusivo seu — não distribua este app.", size=12, color=cor_sec),
            ft.Container(height=12),
            txt_role,
            ft.Text(
                "Dica: depois de colar, pode tocar em GERAR mesmo sem Salvar.",
                size=11,
                color=cor_sec,
                text_align=ft.TextAlign.CENTER,
                width=400,
            ),
            _btn_acao_com_label(txt_btn_salvar_role, cor_acento, "#f8fafc", salvar_chave, 52),
            ft.Container(height=16),
            txt_comprador,
            txt_email,
            dd_plano,
            ft.Container(height=8),
            _btn_acao("GERAR E REGISTRAR LICENÇA", cor_ok, "#0f172a", gerar, 52),
            ft.Container(height=12),
            lbl_resultado,
            lbl_chave,
            btn_copiar_licenca,
            lbl_copia_feedback,
        ],
        scroll=ft.ScrollMode.AUTO,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )

    tab_lista = ft.Column(
        [
            ft.Text("Licenças no Supabase", size=18, weight=ft.FontWeight.W_600, color="#f8fafc"),
            ft.Text("Mesma service role do POST; só leitura.", size=11, color=cor_sec, text_align=ft.TextAlign.CENTER, width=400),
            ft.Container(height=8),
            _btn_acao("Atualizar lista", cor_acento, "#f8fafc", carregar_lista, 48),
            lbl_lista_status,
            ft.Container(height=8),
            col_lista,
        ],
        expand=True,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
    )

    tabs_ctrl = ft.Tabs(
        length=2,
        selected_index=0,
        expand=True,
        on_change=ao_mudar_aba,
        content=ft.Column(
            expand=True,
            controls=[
                ft.TabBar(
                    tabs=[
                        ft.Tab(label="Gerar", icon=ft.Icons.ADD_CIRCLE_OUTLINE_ROUNDED),
                        ft.Tab(label="Licenças", icon=ft.Icons.LIST_ROUNDED),
                    ],
                ),
                ft.TabBarView(
                    expand=True,
                    controls=[tab_gerar, tab_lista],
                ),
            ],
        ),
    )

    page.add(ft.SafeArea(expand=True, content=tabs_ctrl))


if __name__ == "__main__":
    ft.app(main)
