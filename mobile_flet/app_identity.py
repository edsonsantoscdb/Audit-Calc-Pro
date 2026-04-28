"""Identidade local: e-mail do utilizador e device_id persistentes para o backend."""

from __future__ import annotations

import json
import os

from mobile_flet.supabase_license import android_storage_candidate_dirs, _is_android_app

_EMAIL_FILE = ".auditcalc_perfil_email.json"
_DEVICE_CACHE_FILE = ".auditcalc_device.json"

_storage_root: str = ""


def set_storage_root(path: str) -> None:
    """Chamar desde app_mobile assim que existir pasta de dados gravável."""
    global _storage_root
    _storage_root = (path or "").strip()


def _dirs_gravacao() -> list[str]:
    dirs: list[str] = []
    seen: set[str] = set()
    if _storage_root and os.path.isdir(_storage_root):
        seen.add(_storage_root)
        dirs.append(_storage_root)
    if _is_android_app():
        for d in android_storage_candidate_dirs():
            if d and d not in seen and os.path.isdir(d):
                seen.add(d)
                dirs.append(d)
    else:
        flet_data = (os.environ.get("FLET_APP_STORAGE_DATA") or "").strip()
        if flet_data and os.path.isdir(flet_data):
            if flet_data not in seen:
                seen.add(flet_data)
                dirs.append(flet_data)
        if _storage_root and _storage_root not in seen and os.path.isdir(_storage_root):
            dirs.insert(0, _storage_root)
    return dirs


def email_basico_valido(email: str) -> bool:
    """Validação simples pedida pelo produto (conter «@» e «.»)."""
    if not isinstance(email, str):
        return False
    e = email.strip()
    if len(e) < 3:
        return False
    return "@" in e and "." in e


def get_email_salvo() -> str:
    """E-mail gravado ou string vazia."""
    for d in _dirs_gravacao():
        path = os.path.join(d, _EMAIL_FILE)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                dct = json.load(f)
            em = str(dct.get("email", "") or "").strip().lower()
            if email_basico_valido(em):
                return em
        except Exception:
            continue
    for base in android_storage_candidate_dirs() if _is_android_app() else []:
        path = os.path.join(base, _EMAIL_FILE)
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    dct = json.load(f)
                em = str(dct.get("email", "") or "").strip().lower()
                if email_basico_valido(em):
                    return em
            except Exception:
                pass
    return ""


def salvar_email(email: str) -> bool:
    """Grava após Continuar no primeiro uso (várias cópias no Android onde possível)."""
    em = email.strip().lower()
    if not email_basico_valido(em):
        return False
    payload = {"email": em}
    ok = False
    for d in _dirs_gravacao():
        path = os.path.join(d, _EMAIL_FILE)
        try:
            os.makedirs(d, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            ok = True
        except OSError:
            continue
    return ok


def get_device_id() -> str:
    """
    Identificador estável: lê disco se já existir; senão calcula (mesmo método que licença) e grava.
    """
    from mobile_flet.supabase_license import _get_device_id as computar_hash

    for d in _dirs_gravacao():
        path = os.path.join(d, _DEVICE_CACHE_FILE)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            did = str(data.get("device_id", "") or "").strip()
            if len(did) >= 16:
                return did[:128]
        except Exception:
            continue

    did = computar_hash()
    payload = {"device_id": did}
    for d in _dirs_gravacao():
        path = os.path.join(d, _DEVICE_CACHE_FILE)
        try:
            os.makedirs(d, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
        except OSError:
            continue
    return did
