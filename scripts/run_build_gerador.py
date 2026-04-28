"""Build APK do Gerador com logo próprio (icon_gerador.png na raiz); restaura pyproject.

Uso: python scripts/run_build_gerador.py

Sempre troca [tool.flet] icon para icon_gerador.png durante o build e volta ao valor
original no fim — assim o Audit Calc pode usar assets/icon.png e o gerador outro logo.

Para o app dos clientes: python scripts/run_build_audit_calc.py
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOML = ROOT / "pyproject.toml"
ICON_LINE = re.compile(r'^(\s*icon\s*=\s*)"([^"]+)"(\s*)$', re.MULTILINE)
GERADOR_ICON = "icon_gerador.png"


def main() -> int:
    icon_path = ROOT / GERADOR_ICON
    if not icon_path.is_file():
        print(f"Falta {GERADOR_ICON} na raiz do projeto ({ROOT}).")
        return 1

    raw = TOML.read_text(encoding="utf-8-sig")
    m = ICON_LINE.search(raw)
    if not m:
        print('pyproject: não achei linha icon = "..." em [tool.flet] — abortando.')
        return 1
    original_icon = m.group(2)
    if original_icon == GERADOR_ICON:
        gerador_toml = raw
    else:
        gerador_toml = ICON_LINE.sub(
            rf'\1"{GERADOR_ICON}"\3',
            raw,
            count=1,
        )

    try:
        if gerador_toml != raw:
            TOML.write_text(gerador_toml, encoding="utf-8", newline="\n")
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
            "gerador_apk",
            "--product",
            "Audit Gerador",
            "--org",
            "com.auditcalc",
            "--bundle-id",
            "com.auditcalc.gerador",
            "--artifact",
            "audit_gerador",
            "--no-rich-output",
            "--yes",
        ]
        return subprocess.call(cmd, cwd=ROOT, env=env)
    finally:
        TOML.write_text(raw, encoding="utf-8", newline="\n")
        print(f"pyproject.toml restaurado (icon = {original_icon!r}).")


if __name__ == "__main__":
    raise SystemExit(main())
