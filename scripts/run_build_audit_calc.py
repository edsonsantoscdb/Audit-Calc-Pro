"""Build APK do Audit Calc (clientes) com ícone assets/icon.png; não altera o gerador.

Uso: python scripts/run_build_audit_calc.py

Saída em build/apk/ (artefactos do Flet) + cópias com nomes estáveis:

- audit_calc.apk — ARM64 (principal; cópia de audit_calc-arm64-v8a.apk).
- audit_calc_arm32.apk — cópia de audit_calc-armeabi-v7a.apk (aparelhos 32-bit ARM).
- audit_calc_x86_64.apk — cópia de audit_calc-x86_64.apk (emuladores / raros x86).

Também: build/apk_prontos/ com os mesmos 3 ficheiros; build/audit_calc_tres_arquiteturas.zip com os 3.

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
BUILD_DIR = ROOT / "build"

# Dois APKs não-ARM64 com nomes estáveis (para partilha sem depender do sufixo Flet exacto).
ALIAS_ARM32 = "audit_calc_arm32.apk"
ALIAS_X86_64 = "audit_calc_x86_64.apk"


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
    """build/apk/audit_calc.apk = arm64 local; releases/install_audit_calc.apk = cópia para GitHub."""
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
    # Cópia única para GitHub: apenas o APK (sem .sha1 em releases/).
    rel = ROOT / "releases"
    rel.mkdir(parents=True, exist_ok=True)
    shutil.copy2(arm64, rel / "install_audit_calc.apk")
    (rel / "audit_calc.apk").unlink(missing_ok=True)
    old_sha = rel / "audit_calc.apk.sha1"
    old_sha.unlink(missing_ok=True)


def _alias_extra_splits() -> None:
    """Cria cópias com nomes audit_calc_arm32.apk e audit_calc_x86_64.apk em build/apk/."""
    v7 = OUT_APK_DIR / "audit_calc-armeabi-v7a.apk"
    x86 = OUT_APK_DIR / "audit_calc-x86_64.apk"
    if v7.is_file():
        shutil.copy2(v7, OUT_APK_DIR / ALIAS_ARM32)
    else:
        print(f"Aviso: {v7.name} não gerado — {ALIAS_ARM32} omitido.", file=sys.stderr)
    if x86.is_file():
        shutil.copy2(x86, OUT_APK_DIR / ALIAS_X86_64)
    else:
        print(f"Aviso: {x86.name} não gerado — {ALIAS_X86_64} omitido.", file=sys.stderr)


def _package_prontos_e_zip() -> None:
    """build/apk_prontos/: os 3 APKs estáveis + ZIP em build/audit_calc_tres_arquiteturas.zip."""
    prontos = BUILD_DIR / "apk_prontos"
    prontos.mkdir(parents=True, exist_ok=True)
    for velho in list(prontos.glob("*")):
        velho.unlink(missing_ok=True)
    triple = [
        ("audit_calc.apk", OUT_APK_DIR / "audit_calc.apk"),
        (ALIAS_ARM32, OUT_APK_DIR / ALIAS_ARM32),
        (ALIAS_X86_64, OUT_APK_DIR / ALIAS_X86_64),
    ]
    zip_path = BUILD_DIR / "audit_calc_tres_arquiteturas"
    ok_any = False
    for nome, caminho in triple:
        if caminho.is_file():
            shutil.copy2(caminho, prontos / nome)
            ok_any = True
    # Sha1 opcional só do principal para diagnóstico local
    h = OUT_APK_DIR / "audit_calc.apk.sha1"
    if h.is_file():
        shutil.copy2(h, prontos / "audit_calc.apk.sha1")
    if not ok_any:
        return
    # Recria ZIP sempre com o mesmo nome (sem lixo dentro)
    arquivo = shutil.make_archive(
        str(zip_path),
        "zip",
        root_dir=str(prontos),
    )
    # make_archive pode devolver .zip já com nome; garantir só .zip único na raíz build/
    esperado = Path(str(zip_path) + ".zip")
    if Path(arquivo) != esperado and Path(arquivo).is_file():
        shutil.move(arquivo, esperado)


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
    _alias_extra_splits()
    _package_prontos_e_zip()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
