# Build do APK "Audit Gerador" (ícone icon_gerador.png, restaura pyproject ao terminar).
# Uso: .\scripts\build_apk_gerador.ps1

$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $proj

if (-not (Test-Path "icon_gerador.png")) {
    Write-Host "Gerando icon_gerador.png..."
    python scripts/atualizar_icon_gerador.py
}

python scripts/run_build_gerador.py
