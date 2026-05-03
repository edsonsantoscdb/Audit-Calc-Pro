# Audit Calc — estrutura do projeto

Tudo o que é **obrigatório** para a lógica está em **`core/`**. O resto são **aplicações** que importam esse núcleo.

## Pastas

| Pasta | Conteúdo |
|-------|-----------|
| **`core/`** | Motor financeiro: `motor_auditoria.py` (CET, veredito, parcela justa). |
| **`desktop/`** | App Windows com CustomTkinter: `interface.py`. |
| **`mobile_flet/`** | App Flet (testar no PC; depois `flet build apk` se quiser APK). |
| **`android/`** | Projeto Kotlin opcional (Android Studio), quando quiser retomar. |
| **`extras/`** | Scripts auxiliares, ex.: `motor_dedo_duro.py` (testes no terminal). |

## Como executar

Na pasta **raiz** do projeto (`CALCULADORA`):

```bash
pip install -r requirements.txt
```

**Desktop (Windows):**

```bash
python desktop/interface.py
```

**Flet (interface parecida com celular, no computador):**

```bash
python mobile_flet/app_mobile.py
```

(Alternativa: `flet run mobile_flet/app_mobile.py` ou `python -m flet run mobile_flet/app_mobile.py`.)

## APK Android (Flet)

**Download oficial (único APK no GitHub)** — mesmo app **Audit Calc**; o nome serve para evitar o telemóvel descarregar uma cópia **antiga** em cache pelo link anterior (~75 MB).

- **`install_audit_calc.apk`** (≈30–32 MB):  
  https://github.com/edsonsantoscdb/Audit-Calc-Pro/raw/main/releases/install_audit_calc.apk

Se ao descarregar ainda vir ~75 MB: apagar dados do browser / GitHub, ou usar aba privada.

Link **fixado a um commit** (não usa `main`, útil quando o cache teima): consulte no GitHub o commit mais recente em `releases/install_audit_calc.apk` → “View raw” ou URL `raw.githubusercontent.com/.../<hash-do-commit>/releases/install_audit_calc.apk`.

Para **gerar** o APK localmente (não é enviado ao GitHub automaticamente):

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
chcp 65001 > $null
python scripts/run_build_audit_calc.py
```

Os artefactos do build ficam em `build/apk/` no teu PC (vários ficheiros por arquitectura); só o ficheiro acima em `releases/` está no GitHub.

### Imagens de fundo

Se quiser ativar imagem no fundo da app, adicione um destes ficheiros:

- `assets/fundo_app.jpg` ou `assets/fundo_app.png`
- `carro.png` ou `moto.png` na raiz (fallback)

## Ficheiros na raiz

- `carro.png` / `moto.png` — opcionais; o desktop procura-os **aqui** (não dentro de `desktop/`).
- `historico_auditoria.csv` — criado ao gravar histórico no desktop; também fica **na raiz**.

## Dependências resumidas

- **Desktop:** `customtkinter`, `numpy-financial`, `Pillow`.
- **Flet:** inclui `flet` no `requirements.txt`.
- **Kotlin/Android:** ver `android/README.md`.
