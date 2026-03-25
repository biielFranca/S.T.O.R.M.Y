"""
Tray da Stormy — ícone na bandeja do sistema (system tray).
Menu: Abrir, Última resposta, Sair.
"""

import threading
from PIL import Image, ImageDraw


def _make_icon() -> Image.Image:
    """Gera ícone simples: círculo azul ciano com S."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Círculo de fundo
    draw.ellipse([2, 2, size - 2, size - 2], fill=(0, 191, 255, 220))
    # Letra S
    draw.text((20, 14), "S", fill=(10, 10, 10), font=None)
    return img


class StormyTray:
    def __init__(self, on_open, on_quit):
        self._on_open = on_open
        self._on_quit = on_quit
        self._tray = None
        self._last_response = "Nenhuma resposta ainda."

    def set_last_response(self, text: str):
        self._last_response = text[:80]

    def start(self):
        """Inicia o tray em thread separada."""
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            import pystray
        except ImportError:
            print("[Tray] pystray não instalado. Rode: pip install pystray")
            return

        icon_img = _make_icon()

        def open_overlay(icon, item):
            self._on_open()

        def show_last(icon, item):
            pass  # pystray não tem tooltip fácil, usa notificação futura

        def quit_app(icon, item):
            icon.stop()
            self._on_quit()

        menu = pystray.Menu(
            pystray.MenuItem("Abrir Stormy", open_overlay, default=True),
            pystray.MenuItem(lambda text: f"[{self._last_response[:40]}]", show_last, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Sair", quit_app),
        )

        self._tray = pystray.Icon(
            name="Stormy",
            icon=icon_img,
            title="Stormy",
            menu=menu,
        )
        self._tray.run()

    def stop(self):
        if self._tray:
            self._tray.stop()
