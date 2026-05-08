"""
Módulo de licenciamento via Supabase.
Valida chave, vincula ao dispositivo e respeita expira_em (passe semanal/mensal ou vitalício).
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Sem barra final: evita ...co//rest e ...co//functions (502 no gateway em alguns casos).
SUPABASE_URL = os.environ.get(
    "SUPABASE_URL",
    "https://ynixfnrjxuqdhzcralvo.supabase.co",
).strip().rstrip("/")
SUPABASE_KEY = os.environ.get(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InluaXhmbnJqeHVxZGh6Y3JhbHZvIiwi"
    "cm9sZSI6ImFub24iLCJpYXQiOjE3NzU5MzAyNzgsImV4cCI6MjA5MTUwNjI3OH0."
    "cPjjpciTL01GeuhWFnQlG1HLFfgNYY509djSxras8QQ",
).strip()

# URL do checkout Mercado Pago (preferência ou link fixo); definir em build/CI ou deixar vazio.
MERCADOPAGO_CHECKOUT_URL = os.environ.get("AUDITCALC_MP_CHECKOUT_URL", "").strip()

PAYMENT_MODE = "test"  # "test" ou "prod"

unit_price = 69.90  # referência; cobrança real definida na Edge Function create_mercadopago_payment (Supabase)
title = "Audit Calc - Licença Vitalícia"

# Preferência MP: campo "metadata" (ex.: {"metadata": metadata} no JSON).
metadata = {"mode": PAYMENT_MODE}

# Modo gratuito: conta auditorias bem-sucedidas (resultado válido, não erro de formulário).
FREE_AUDITS_LIMIT = 3

_TRIAL_FILE = ".auditcalc_trial.json"

_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

_LICENSE_FILE = ".auditcalcpro_licenca.json"


def _get_device_id():
    """Retorna identificador único do dispositivo (estável entre aberturas do app)."""
    if hasattr(sys, "getandroidapilevel") or "android" in sys.platform:
        import hashlib

        # Junta várias fontes estáveis; não usar só o primeiro ficheiro encontrado
        # (ordem diferente / iSerial vazio mudava o hash entre sessões).
        parts: list[str] = []
        for var in ("HOME", "ANDROID_DATA", "ANDROID_ROOT"):
            v = os.environ.get(var, "")
            if v:
                parts.append(v)
        for prop in ("/proc/sys/kernel/random/boot_id",):
            try:
                if os.path.isfile(prop):
                    with open(prop, encoding="utf-8") as f:
                        parts.append(f.read().strip())
            except OSError:
                pass
        raw = "\0".join(parts) if parts else "android-fallback"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]
    import hashlib
    import platform

    raw = platform.node() + str(os.getenv("USERNAME", "")) + str(os.getenv("COMPUTERNAME", ""))
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _get_device_id_legacy_android() -> str:
    """Hash antigo (antes do fix de estabilidade) — só para aceitar chaves já vinculadas."""
    import hashlib

    raw = ""
    for var in ("ANDROID_DATA", "ANDROID_ROOT", "HOME", "SHELL"):
        raw += os.environ.get(var, "")
    try:
        for prop in (
            "/sys/class/android_usb/android0/iSerial",
            "/proc/sys/kernel/random/boot_id",
        ):
            if os.path.exists(prop):
                with open(prop, encoding="utf-8") as f:
                    raw += f.read().strip()
                break
    except OSError:
        pass
    if not raw:
        raw = "android-fallback"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _android_device_ids_equivalent(stored: str, current: str) -> bool:
    if not stored:
        return True
    if stored == current:
        return True
    if hasattr(sys, "getandroidapilevel") or "android" in sys.platform:
        legacy = _get_device_id_legacy_android()
        if stored == legacy:
            return True
    return False


def _patch_android_id(
    chave: str, device_id: str, android_id_anterior: str | None = None, tentativas: int = 2
) -> None:
    """Atualiza android_id no servidor via RPC (compatível com RLS; não usa PATCH direto na tabela)."""
    payload: dict = {
        "p_chave": chave.strip().upper(),
        "p_android_id": device_id,
    }
    if android_id_anterior:
        payload["p_anterior"] = android_id_anterior
    url = f"{SUPABASE_URL}/rest/v1/rpc/vincular_android_licenca"
    body = json.dumps(payload).encode()
    headers = {**_HEADERS, "Prefer": "return=minimal"}
    for tentativa in range(tentativas):
        try:
            req = Request(url, data=body, headers=headers, method="POST")
            with urlopen(req, timeout=15):
                return
        except HTTPError:
            raise
        except (URLError, OSError):
            if tentativa < tentativas - 1:
                time.sleep(1.5)
                continue
            raise


def _get_license_path(data_dir):
    return os.path.join(data_dir, _LICENSE_FILE) if data_dir else ""


def _is_android_app() -> bool:
    return hasattr(sys, "getandroidapilevel") or "android" in sys.platform


def android_storage_candidate_dirs() -> list[str]:
    """Pastas candidatas no Android onde tentamos ler/gravar a licença."""
    import tempfile

    seen: set[str] = set()
    out: list[str] = []
    # Flet/Flutter (serious_python): diretório persistente do APK — deve vir antes de TMP/cache.
    for key in ("FLET_APP_STORAGE_DATA", "FLET_APP_STORAGE_TEMP"):
        v = (os.environ.get(key) or "").strip()
        if v and v not in seen and os.path.isdir(v):
            seen.add(v)
            out.append(v)
    for key in ("HOME", "ANDROID_APP_DATA", "TMPDIR"):
        v = (os.environ.get(key) or "").strip()
        if v and v not in seen and os.path.isdir(v):
            seen.add(v)
            out.append(v)
    for extra in ("/data/local/tmp", tempfile.gettempdir()):
        ev = (extra or "").strip()
        if ev and ev not in seen and os.path.isdir(ev):
            seen.add(ev)
            out.append(ev)
    return out


def _license_paths_for_lookup(data_dir: str | None) -> list[str]:
    """Todos os ficheiros .auditcalc_licenca.json a considerar (Android: várias pastas)."""
    seen: set[str] = set()
    paths: list[str] = []
    if data_dir:
        p = _get_license_path(data_dir)
        if p and p not in seen:
            seen.add(p)
            paths.append(p)
    if _is_android_app():
        for d in android_storage_candidate_dirs():
            p = _get_license_path(d)
            if p and p not in seen:
                seen.add(p)
                paths.append(p)
    return paths


def _get_trial_path(data_dir: str) -> str:
    return os.path.join(data_dir, _TRIAL_FILE) if data_dir else ""


def _trial_paths_for_lookup(data_dir: str | None) -> list[str]:
    seen: set[str] = set()
    paths: list[str] = []
    if data_dir:
        p = _get_trial_path(data_dir)
        if p and p not in seen:
            seen.add(p)
            paths.append(p)
    if _is_android_app():
        for d in android_storage_candidate_dirs():
            p = _get_trial_path(d)
            if p and p not in seen:
                seen.add(p)
                paths.append(p)
    return paths


def get_free_audits_used(data_dir) -> int:
    """Total de auditorias bem-sucedidas em modo avaliação (por dispositivo)."""
    dev = _get_device_id()
    max_used = 0
    for path in _trial_paths_for_lookup(data_dir):
        if not path or not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                dados = json.load(f)
        except Exception:
            continue
        if (dados.get("device_id") or "") != dev:
            continue
        try:
            u = int(dados.get("audits_used", 0))
        except (TypeError, ValueError):
            u = 0
        max_used = max(max_used, u)
    return max_used


def get_free_audits_remaining(data_dir) -> int:
    if is_activated(data_dir):
        return FREE_AUDITS_LIMIT
    return max(0, FREE_AUDITS_LIMIT - get_free_audits_used(data_dir))


def _save_trial_audits_used(data_dir, audits_used: int) -> bool:
    dev = _get_device_id()
    payload = {"device_id": dev, "audits_used": max(0, audits_used)}
    if _is_android_app():
        dirs = list(android_storage_candidate_dirs())
        if data_dir and os.path.isdir(data_dir):
            if data_dir in dirs:
                dirs.remove(data_dir)
            dirs.insert(0, data_dir)
    else:
        dirs = []
        flet_data = (os.environ.get("FLET_APP_STORAGE_DATA") or "").strip()
        if flet_data and os.path.isdir(flet_data):
            dirs.append(flet_data)
        if data_dir and os.path.isdir(str(data_dir)) and data_dir not in dirs:
            dirs.append(data_dir)

    ok = False
    for d in dirs:
        path = _get_trial_path(d)
        if not path:
            continue
        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            ok = True
        except OSError:
            pass
    return ok


def record_successful_free_audit(data_dir) -> None:
    """Incrementa contador após EXECUTAR AUDITORIA com sucesso quando não há licença paga."""
    if is_activated(data_dir):
        return
    used = get_free_audits_used(data_dir)
    if used >= FREE_AUDITS_LIMIT:
        return
    _save_trial_audits_used(data_dir, used + 1)


def _parse_expira_em(val) -> datetime | None:
    if val is None or val == "":
        return None
    if isinstance(val, str):
        s = val.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            return None
    return None


def _esta_expirado(expira_em_raw) -> bool:
    """True se expira_em está no passado (UTC). None/vazio = vitalício."""
    dt = _parse_expira_em(expira_em_raw)
    if dt is None:
        return False
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return now > dt


def clear_license_local(data_dir):
    """Remove cópias locais da licença (todas as pastas candidatas no Android)."""
    for path in _license_paths_for_lookup(data_dir):
        if path and os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass


def is_activated(data_dir):
    """Verifica se o app já foi ativado localmente."""
    for path in _license_paths_for_lookup(data_dir):
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                dados = json.load(f)
            if dados.get("ativado") is True and dados.get("chave", "") != "":
                return True
        except Exception:
            continue
    return False


def get_saved_key(data_dir):
    """Retorna a chave salva localmente, se existir."""
    for path in _license_paths_for_lookup(data_dir):
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                dados = json.load(f)
            k = dados.get("chave", "")
            if k:
                return k
        except Exception:
            continue
    return ""


def _fetch_licenca(chave: str, tentativas: int = 3) -> tuple[list | None, str | None]:
    """
    Obtém uma linha por chave via RPC (compatível com RLS).
    Retorna (rows, codigo_erro).
    Códigos: None=ok, "network"=sem internet, "server:XXX"=erro HTTP do Supabase.
    """
    url = f"{SUPABASE_URL}/rest/v1/rpc/get_licenca_por_chave"
    body = json.dumps({"p_chave": chave}).encode()
    ultimo_erro: str | None = None
    for tentativa in range(tentativas):
        try:
            req = Request(url, data=body, headers=_HEADERS, method="POST")
            with urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode()), None
        except HTTPError as e:
            try:
                corpo = e.read().decode()
            except Exception:
                corpo = ""
            detail = ""
            try:
                obj = json.loads(corpo)
                detail = obj.get("message") or obj.get("hint") or corpo[:200]
            except Exception:
                detail = corpo[:200] if corpo else str(e.code)
            ultimo_erro = f"server:{e.code}:{detail}"
            if e.code < 500:
                return None, ultimo_erro
        except (URLError, OSError):
            ultimo_erro = "network"
        except Exception as e:
            ultimo_erro = f"server:0:{str(e)[:200]}"
        if tentativa < tentativas - 1:
            time.sleep(1.5 * (tentativa + 1))
    return None, ultimo_erro


def revalidate_license(data_dir) -> tuple[bool, str]:
    """
    Consulta o servidor com a chave salva.
    Retorna (continuar_uso, codigo_mensagem).
    continuar_uso False => limpou licença local; código: expired, revoked, device, invalid, server_error
    continuar_uso True => ok ou sem rede (mantém uso offline)
    """
    chave = get_saved_key(data_dir)
    if not chave:
        return True, ""

    rows, err = _fetch_licenca(chave)

    if err == "network":
        return True, ""
    if err and err.startswith("server:"):
        return True, ""

    if rows is None:
        return True, ""

    if not rows:
        clear_license_local(data_dir)
        return False, "invalid"

    row = rows[0]
    device_id = _get_device_id()

    if not row.get("ativo", False):
        clear_license_local(data_dir)
        return False, "revoked"

    existing = row.get("android_id") or ""
    if existing and not _android_device_ids_equivalent(existing, device_id):
        clear_license_local(data_dir)
        return False, "device"

    if _esta_expirado(row.get("expira_em")):
        clear_license_local(data_dir)
        return False, "expired"

    if existing and existing != device_id and _android_device_ids_equivalent(existing, device_id):
        try:
            _patch_android_id(chave, device_id, android_id_anterior=existing)
        except Exception:
            pass

    _save_local(
        data_dir,
        chave,
        device_id,
        expira_em=row.get("expira_em"),
    )
    return True, ""


def activate(chave, data_dir):
    """
    Ativa licença: valida chave, dispositivo, ativo e expiração.
    """
    chave = chave.strip().upper()
    if not chave:
        return False, "Digite uma chave de ativação."

    device_id = _get_device_id()
    rows, err = _fetch_licenca(chave)

    if err == "network":
        return False, "Sem conexão com a internet. Conecte-se e tente novamente."
    if err and err.startswith("server:"):
        partes = err.split(":", 2)
        codigo = partes[1] if len(partes) > 1 else "?"
        detalhe = partes[2] if len(partes) > 2 else ""
        return False, (
            f"Erro no servidor Supabase (HTTP {codigo}). "
            f"{'Detalhe: ' + detalhe + '. ' if detalhe else ''}"
            "Tente novamente em alguns minutos. Se persistir, entre em contato com o suporte."
        )
    if not rows:
        return False, "Chave inválida. Verifique e tente novamente."

    row = rows[0]

    if not row.get("ativo", False):
        return False, "Esta chave foi desativada. Entre em contato com o suporte."

    if _esta_expirado(row.get("expira_em")):
        return False, "Esta chave já expirou. Adquira um novo passe."

    existing_device = row.get("android_id") or ""
    if existing_device and not _android_device_ids_equivalent(existing_device, device_id):
        return False, "Esta chave já está vinculada a outro dispositivo."

    precisa_gravar_supabase = (not existing_device) or (
        existing_device != device_id and _android_device_ids_equivalent(existing_device, device_id)
    )
    if precisa_gravar_supabase:
        try:
            anterior = (
                existing_device
                if (existing_device and existing_device != device_id)
                else None
            )
            _patch_android_id(chave, device_id, android_id_anterior=anterior)
        except HTTPError as e:
            try:
                corpo = e.read().decode()[:200]
            except Exception:
                corpo = str(e.code)
            return False, (
                f"Chave válida, mas erro ao vincular ao aparelho (HTTP {e.code}: {corpo}). "
                "Tente novamente."
            )
        except (URLError, OSError):
            pass

    if not _save_local(data_dir, chave, device_id, expira_em=row.get("expira_em")):
        return (
            False,
            "A chave foi aceita, mas não deu para gravar no aparelho. "
            "Toque em «Guardar chave neste aparelho» de novo ou verifique o espaço em disco.",
        )
    return True, "Chave guardada neste aparelho. Pode fechar e abrir o app."


def _save_local(data_dir, chave, device_id, expira_em=None) -> bool:
    """Grava JSON da licença. No Android tenta várias pastas para pelo menos uma persistir."""
    payload = {
        "ativado": True,
        "chave": chave,
        "device_id": device_id,
        "expira_em": expira_em,
    }
    if _is_android_app():
        dirs = list(android_storage_candidate_dirs())
        if data_dir and os.path.isdir(data_dir):
            if data_dir in dirs:
                dirs.remove(data_dir)
            dirs.insert(0, data_dir)
    else:
        dirs = []
        flet_data = (os.environ.get("FLET_APP_STORAGE_DATA") or "").strip()
        if flet_data and os.path.isdir(flet_data):
            dirs.append(flet_data)
        if data_dir and os.path.isdir(str(data_dir)) and data_dir not in dirs:
            dirs.append(data_dir)

    ok = False
    for d in dirs:
        path = _get_license_path(d)
        if not path:
            continue
        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            ok = True
        except OSError:
            pass
    return ok


def try_claim_license_after_mercadopago(data_dir) -> tuple[bool, str | None]:
    """
    Fluxo opcional por chave: RPC claim_licenca_por_dispositivo quando existe pending_android_id.
    Para licença só por e‑mail (+ validar_acesso), este passo pode não existir ou não aplicar —
    nesse caso devolve (False, None) para o UI não insistir na chave manual.
    """
    device_id = _get_device_id()
    url = f"{SUPABASE_URL}/rest/v1/rpc/claim_licenca_por_dispositivo"
    body = json.dumps({"p_android_id": device_id}).encode()
    try:
        req = Request(url, data=body, headers=_HEADERS, method="POST")
        with urlopen(req, timeout=15) as resp:
            raw = resp.read().decode()
            rows = json.loads(raw) if raw.strip() else []
    except HTTPError as e:
        try:
            corpo = e.read().decode()
        except Exception:
            corpo = ""
        hint = ""
        try:
            obj = json.loads(corpo) if corpo else {}
            hint = str(obj.get("message") or obj.get("hint") or "")
        except Exception:
            hint = corpo[:200]
        low = (hint + corpo).lower()
        opcional_sem_rpc = e.code == 404 or (
            "could not find" in low and "function" in low
        ) or ("function" in low and ("not exist" in low or "does not exist" in low))
        if opcional_sem_rpc:
            return False, None
        return False, f"Não foi possível verificar agora (HTTP {e.code}). Tente de novo."
    except (URLError, OSError):
        return False, "Sem internet. Conecte-se e tente novamente."

    # Sem linha com pending_android_id = fluxo só por e-mail (validar_acesso), não é erro.
    if not rows:
        return False, None

    row = rows[0] if isinstance(rows, list) else rows
    if not isinstance(row, dict):
        return False, "Resposta inválida do servidor."

    chave = str(row.get("chave", "") or "").strip().upper()
    if not chave:
        return False, "Resposta do servidor sem chave."

    return activate(chave, data_dir)


def validar_acesso_remoto(
    p_email: str,
    p_device_id: str,
    tentativas: int = 2,
    *,
    timeout_seg: float = 15.0,
) -> tuple[dict | None, str | None]:
    """
    POST /rest/v1/rpc/validar_acesso
    Retorna ({"status","tipo","usos_restantes","mensagem"}, None) em sucesso ou (None, erro).
    erros possíveis: sem_email | rede | server:codigo:mensagem
    """
    em = (p_email or "").strip().lower()
    if not em:
        return None, "sem_email"
    url = f"{SUPABASE_URL}/rest/v1/rpc/validar_acesso"
    body_obj = {"p_email": em, "p_device_id": p_device_id or ""}
    body = json.dumps(body_obj).encode()
    ultimo_erro: str | None = None

    for tentativa in range(tentativas):
        try:
            req = Request(url, data=body, headers=_HEADERS, method="POST")
            with urlopen(req, timeout=timeout_seg) as resp:
                raw = resp.read().decode()
                data = json.loads(raw) if raw.strip() else []
        except HTTPError as e:
            try:
                corpo = e.read().decode()
            except Exception:
                corpo = ""
            detail = ""
            try:
                obj = json.loads(corpo)
                detail = obj.get("message") or obj.get("hint") or corpo[:200]
            except Exception:
                detail = corpo[:200] if corpo else str(e.code)
            ultimo_erro = f"server:{e.code}:{detail}"
            if e.code < 500:
                return None, ultimo_erro
            if tentativa < tentativas - 1:
                time.sleep(1.0 * (tentativa + 1))
                continue
            return None, ultimo_erro
        except (URLError, OSError):
            ultimo_erro = "rede"
            if tentativa < tentativas - 1:
                time.sleep(1.5 * (tentativa + 1))
                continue
            return None, "rede"
        except Exception as e:
            return None, f"server:0:{str(e)[:200]}"

        row: dict | None = None
        if isinstance(data, list) and data and isinstance(data[0], dict):
            row = data[0]
        elif isinstance(data, dict):
            row = data
        if not row:
            return None, "server:0:resposta vazia"
        return {
            "status": str(row.get("status", "") or ""),
            "tipo": str(row.get("tipo", "") or "") if row.get("tipo") is not None else None,
            "usos_restantes": row.get("usos_restantes"),
            "mensagem": str(row.get("mensagem", "") or "") if row.get("mensagem") is not None else None,
        }, None

    return None, ultimo_erro or "rede"


def consumir_auditoria_remoto(p_email: str, p_device_id: str, tentativas: int = 2) -> tuple[dict | None, str | None]:
    """
    POST /rest/v1/rpc/consumir_auditoria — decremento / autorização no servidor.
    Retorno com status, opcional tipo, mensagem conforme definido na RPC.
    """
    em = (p_email or "").strip().lower()
    if not em:
        return None, "sem_email"
    url = f"{SUPABASE_URL}/rest/v1/rpc/consumir_auditoria"
    body = json.dumps({"p_email": em, "p_device_id": p_device_id or ""}).encode()
    ultimo_erro: str | None = None

    for tentativa in range(tentativas):
        try:
            req = Request(url, data=body, headers=_HEADERS, method="POST")
            with urlopen(req, timeout=15) as resp:
                raw = resp.read().decode()
                data = json.loads(raw) if raw.strip() else []
        except HTTPError as e:
            try:
                corpo = e.read().decode()
            except Exception:
                corpo = ""
            detail = ""
            try:
                obj = json.loads(corpo)
                detail = obj.get("message") or obj.get("hint") or corpo[:200]
            except Exception:
                detail = corpo[:200] if corpo else str(e.code)
            ultimo_erro = f"server:{e.code}:{detail}"
            if e.code < 500:
                return None, ultimo_erro
            if tentativa < tentativas - 1:
                time.sleep(1.0 * (tentativa + 1))
                continue
            return None, ultimo_erro
        except (URLError, OSError):
            ultimo_erro = "rede"
            if tentativa < tentativas - 1:
                time.sleep(1.5 * (tentativa + 1))
                continue
            return None, "rede"
        except Exception as e:
            return None, f"server:0:{str(e)[:200]}"

        row: dict | None = None
        if isinstance(data, list) and data and isinstance(data[0], dict):
            row = data[0]
        elif isinstance(data, dict):
            row = data
        if not row:
            return None, "server:0:resposta vazia"
        return {
            "status": str(row.get("status", "") or ""),
            "tipo": str(row.get("tipo", "") or "") if row.get("tipo") is not None else None,
            "usos_restantes": row.get("usos_restantes"),
            "mensagem": str(row.get("mensagem", "") or "") if row.get("mensagem") is not None else None,
        }, None

    return None, ultimo_erro or "rede"


def chamar_consumir_auditoria() -> tuple[dict | None, str | None]:
    """Usa e-mail e device_id gravados localmente."""
    from mobile_flet.app_identity import get_device_id, get_email_salvo

    return consumir_auditoria_remoto(get_email_salvo(), get_device_id())


def chamar_validar_acesso() -> tuple[dict | None, str | None]:
    """Usa email e device_id gravados localmente."""
    from mobile_flet.app_identity import get_device_id, get_email_salvo

    return validar_acesso_remoto(get_email_salvo(), get_device_id())


def mensagem_falha_rpc_validar_acesso(erro: str) -> str:
    """Texto apresentável quando a RPC falha (rede já tratada antes)."""
    if erro == "sem_email":
        return (
            "Sem e-mail neste aparelho. Volte ao primeiro ecrã, confirme o e-mail e tente «JÁ PAGUEI» "
            "(tem de ser o mesmo e-mail do Mercado Pago)."
        )
    low = erro.lower()
    if erro.startswith("server:401"):
        return (
            "O servidor recusou a ligação (credenciais). Atualize a app para a última versão ou "
            "contacte o suporte."
        )
    if erro.startswith("server:403"):
        return "Acesso negado pelo servidor. Verifique a Internet ou contacte o suporte."
    if erro.startswith("server:429") or "too many requests" in low:
        return "Servidor ocupado demasiado rápido. Aguarde 1 minuto e tente de novo."
    if "resposta vazia" in low:
        return "Resposta inesperada do servidor. Tente dentro de poucos instantes."
    if erro.startswith("server:5"):
        return "O servidor falhou temporariamente. Tente de novo daqui a alguns minutos."
    if erro.startswith("server:"):
        partes = erro.split(":", 2)
        cod = partes[1] if len(partes) > 1 else "?"
        det = partes[2] if len(partes) > 2 else ""
        return f"Erro ao falar com o servidor (HTTP {cod}). {det.strip()[:200]}"
    return erro.strip()[:250] if erro else "Erro ao contactar o servidor."


def chamar_validar_acesso_apos_checkout(
    *,
    max_tentativas: int = 7,
    intervalo_seg: float = 3.0,
) -> tuple[dict | None, str | None]:
    """
    Revalidações após Mercado Pago: retenta apenas quando faz sentido (webhook em atraso).
    Erros HTTP 4xx não são repetidos de propósito.
    """
    from mobile_flet.app_identity import get_device_id, get_email_salvo

    em = (get_email_salvo() or "").strip()
    if not em:
        return None, "sem_email"
    dev = get_device_id()
    última_resp: dict | None = None
    último_erro: str | None = None

    for tentativa in range(max(1, int(max_tentativas))):
        resp, err = validar_acesso_remoto(
            em.lower(),
            dev,
            tentativas=4,
            timeout_seg=28.0,
        )
        última_resp, último_erro = resp, err

        if err == "rede":
            return última_resp, "rede"

        if err:
            if err.startswith("server:429") or err.startswith("server:5"):
                if tentativa < max_tentativas - 1:
                    time.sleep(max(1.5, float(intervalo_seg)))
                    continue
                return última_resp, err
            return última_resp, err

        if resp and resp.get("status") == "liberado":
            return resp, None

        if tentativa < max_tentativas - 1:
            time.sleep(max(0.5, float(intervalo_seg)))

    return última_resp, último_erro


def mensagem_pos_revalidacao(codigo: str) -> str:
    return {
        "expired": "Sua licença expirou. Adquira um novo passe e digite a nova chave.",
        "revoked": "Esta licença foi desativada. Entre em contato com o suporte.",
        "device": "Esta licença está vinculada a outro aparelho.",
        "invalid": "Licença não encontrada. Digite uma chave válida.",
    }.get(codigo, "")


def get_create_mercadopago_payment_function_url() -> str:
    """URL completa opcional; caso contrário usa SUPABASE_URL/functions/v1/create_mercadopago_payment."""
    override = os.environ.get("AUDITCALC_MP_CREATE_PAYMENT_FUNCTION_URL", "").strip().rstrip("/")
    if override:
        return override
    return f"{SUPABASE_URL}/functions/v1/create_mercadopago_payment"


def criar_preferencia_mercadopago_via_edge(email: str) -> tuple[str | None, str | None]:
    """
    Chama Edge Function create_mercadopago_payment (POST JSON {"email"}).
    Retorna (init_point, None) em caso de sucesso, ou (None, código interno não amigável).
    Não altera BD nem estado local.
    """
    em = (email or "").strip()
    if not em:
        return None, "sem_email"

    url = get_create_mercadopago_payment_function_url()
    body = json.dumps({"email": em}).encode("utf-8")
    req_headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }

    try:
        req = Request(url, data=body, headers=req_headers, method="POST")
        with urlopen(req, timeout=35) as resp:
            raw = resp.read().decode()
    except HTTPError as e:
        return None, f"http_{e.code}"
    except (URLError, OSError):
        return None, "rede"

    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return None, "bad_json"

    init = data.get("init_point")
    if isinstance(init, str) and init.strip():
        return init.strip(), None
    return None, "sem_init_point"
