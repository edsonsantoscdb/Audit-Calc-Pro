"""Build APK do Audit Calc (clientes) com ícone assets/icon.png; não altera o gerador.

Uso: python scripts/run_build_audit_calc.py

O pyproject.toml deve manter icon = "assets/icon.png" para este app.
Para o Gerador, use sempre: python scripts/run_build_gerador.py (troca para icon_gerador.png).
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ICON_MAIN = ROOT / "assets" / "icon.png"


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
        "--no-rich-output",
        "--yes",
    ]
    return subprocess.call(cmd, cwd=ROOT, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
