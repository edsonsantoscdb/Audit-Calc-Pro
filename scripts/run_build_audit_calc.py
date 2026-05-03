"""Build APK do Audit Calc (clientes) com ícone assets/icon.png; não altera o gerador.

Uso: python scripts/run_build_audit_calc.py

Cada APK por CPU (split-per-abi): entregue audit_calc-arm64-v8a.apk à maioria dos telemóveis.
O pyproject exclui releases/, supabase/, *.apk do pacote Python — evita APK dentro do APK.

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
    """Com --split-per-abi o Flutter também pode gerar APK universal grande; remover duplicado."""
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
    # Cópia principal para distribuição (telefónicos modernos 64‑bit ARM)
    arm64 = OUT_APK_DIR / "audit_calc-arm64-v8a.apk"
    prontos_dir = ROOT / "build" / "apk_prontos"
    if arm64.is_file():
        prontos_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(arm64, prontos_dir / "audit_calc.apk")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
