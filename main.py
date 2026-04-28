"""
Ponto de entrada para o Flet (`flet build`).
Importação preguiçosa: se algo falhar no Android, mostra o erro no ecrã.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

import flet as ft

__all__ = ["main"]


def main(page: ft.Page) -> None:
    page.bgcolor = "#0f172a"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 16
    page.update()

    root = Path(__file__).resolve().parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    try:
        import mobile_flet.app_mobile as app_mod
        app_mod.main(page)
    except Exception:
        msg = traceback.format_exc()
        page.controls.clear()
        page.padding = 16

        def reiniciar(_):
            page.controls.clear()
            try:
                import importlib
                importlib.reload(app_mod)
                app_mod.main(page)
            except Exception:
                pass

        page.add(
            ft.SafeArea(
                content=ft.Column(
                    [
                        ft.Text(
                            "Erro ao iniciar",
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color="#f87171",
                        ),
                        ft.Text(
                            msg,
                            color="#f8fafc",
                            size=11,
                            selectable=True,
                        ),
                        ft.Container(height=20),
                        ft.Button(
                            content="TENTAR NOVAMENTE",
                            bgcolor="#3b82f6",
                            color="#f8fafc",
                            width=300,
                            height=50,
                            on_click=reiniciar,
                        ),
                    ],
                    scroll=ft.ScrollMode.AUTO,
                    expand=True,
                ),
            )
        )
        page.update()


ft.app(main)
