"""
Gera icon_gerador.png (512x512) a partir de 'Gerador de Senhas.png' na raiz do projeto.
Rode de novo se trocar o arquivo-fonte do logo.

  python scripts/atualizar_icon_gerador.py
"""
from pathlib import Path

from PIL import Image, ImageOps

_ROOT = Path(__file__).resolve().parent.parent
SRC = _ROOT / "Gerador de Senhas.png"
DST = _ROOT / "icon_gerador.png"


def main():
    if not SRC.is_file():
        print(f"Não achei: {SRC}")
        print("Coloque o PNG do gerador com esse nome na pasta do projeto.")
        return 1
    im = Image.open(SRC).convert("RGBA")
    out = ImageOps.fit(im, (512, 512), method=Image.Resampling.LANCZOS)
    out.save(DST)
    print(f"Salvo: {DST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
