"""Build APK do Audit Calc (clientes) com ícone assets/icon.png; não altera o gerador.

Uso: python scripts/run_build_audit_calc.py

Saída em build/apk/:
- audit_calc.apk — mesmo nome de antes; conteúdo = ARM64 (audit_calc-arm64-v8a.apk), uso principal em telemóveis.
- audit_calc-armeabi-v7a.apk e audit_calc-x86_64.apk — inalterados (propaganda: contactar para estes).

Para o Gerador, use sempre: python scripts/run_build_gerador.py
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ICON_MAIN = ROOT / "assets" / "icon.png"
OUT_APK_DIR = ROOT / "build" / "apk"


def _remove_legacy_fat_apk_if_splits_exist() -> None:
    """Com split-per-abi, remove APK universal antigo (>80MB) se ainda existir na pasta."""
    if not OUT_APK_DIR.is_dir():
        return
    splits = list(OUT_APK_DIR.glob("audit_calc-*.apk"))
    fat = OUT_APK_DIR / "audit_calc.apk"
    if splits and fat.is_file():
        mb = fat.stat().st_size / (1024 * 1024)
        if mb > 80:
            fat.unlink(missing_ok=True)
            hs = OUT_APK_DIR / "audit_calc.apk.sha1"
            if hs.is_file():
                hs.unlink(missing_ok=True)


def _publish_main_apk_as_audit_calc() -> None:
    """audit_calc.apk = cópia do arm64-v8a (nome único para propaganda / link único)."""
    arm64 = OUT_APK_DIR / "audit_calc-arm64-v8a.apk"
    main_apk = OUT_APK_DIR / "audit_calc.apk"
    if not arm64.is_file():
        print("Aviso: audit_calc-arm64-v8a.apk não encontrado; audit_calc.apk não foi gerado.", file=sys.stderr)
        return
    shutil.copy2(arm64, main_apk)
    h_src = OUT_APK_DIR / "audit_calc-arm64-v8a.apk.sha1"
    h_dst = OUT_APK_DIR / "audit_calc.apk.sha1"
    if h_src.is_file():
        shutil.copy2(h_src, h_dst)
    else:
        h_dst.unlink(missing_ok=True)


def main() -> int:
    if not ICON_MAIN.is_file():
        print(f"Falta {ICON_MAIN} — coloque o ícone da calculadora em assets/icon.png")
        return 1
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    flet_exe = shutil.which("flet")
    if not flet_exe:
        print("Comando 'flet' não encontrado no PATH.")
        return 1
    cmd = [
        flet_exe,
        "build",
        "apk",
        str(ROOT),
        "--module-name",
        "main",
        "--product",
        "Audit Calc",
        "--org",
        "com.auditcalc",
        "--bundle-id",
        "com.auditcalc",
        "--artifact",
        "audit_calc",
        "--split-per-abi",
        "--cleanup-app",
        "--cleanup-packages",
        "--no-rich-output",
        "--yes",
    ]
    code = subprocess.call(cmd, cwd=ROOT, env=env)
    if code != 0:
        return code
    _remove_legacy_fat_apk_if_splits_exist()
    _publish_main_apk_as_audit_calc()
    prontos_dir = ROOT / "build" / "apk_prontos"
    main_apk = OUT_APK_DIR / "audit_calc.apk"
    if main_apk.is_file():
        prontos_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(main_apk, prontos_dir / "audit_calc.apk")
        h = OUT_APK_DIR / "audit_calc.apk.sha1"
        if h.is_file():
            shutil.copy2(h, prontos_dir / "audit_calc.apk.sha1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
