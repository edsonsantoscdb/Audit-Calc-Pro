"""Ponto de entrada do APK Audit Gerador (Flet exige módulo na raiz do projeto)."""
import flet as ft

from mobile_flet.admin_gerador import main

if __name__ == "__main__":
    ft.app(main)
