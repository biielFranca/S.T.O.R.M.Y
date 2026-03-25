"""
service.py — Stormy rodando em background.
- Hotkey Ctrl+↑ abre/fecha o overlay
- Ícone na bandeja com menu
- Sem terminal visível

Para instalar como startup:
  python service.py --install

Para remover:
  python service.py --uninstall

Para rodar diretamente:
  python service.py
"""

import os
import sys
import threading
import argparse

# Garante que imports do projeto funcionam
sys.path.insert(0, os.path.dirname(__file__))

from agent import chat
from memory import ConversationMemory

# Memória persistente durante toda a sessão background
_memory = ConversationMemory()
_overlay = None
_tray = None


def _warmup_ollama():
    """Carrega o modelo Ollama na RAM antes do primeiro uso."""
    import requests
    from agent import OLLAMA_URL, OLLAMA_MODEL
    try:
        requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "messages": [{"role": "user", "content": "oi"}], "stream": False, "keep_alive": -1},
            timeout=120,
        )
        print("[Service] Ollama aquecido e na RAM.")
    except Exception as e:
        print(f"[Service] Ollama não respondeu no warmup: {e}")


def _send_message(message: str) -> str:
    """Processa mensagem e retorna resposta da Stormy."""
    try:
        response, engine = chat(message, _memory)
        if _tray:
            _tray.set_last_response(response)
        return response
    except Exception as e:
        return f"erro: {e}"


def _toggle_overlay():
    """Abre/fecha o overlay (chamado pelo hotkey e pelo tray)."""
    if _overlay:
        # Tkinter deve ser manipulado da thread principal
        _overlay._root.after(0, _overlay.toggle)


def _setup_hotkey():
    """Registra Ctrl+↑ globalmente."""
    try:
        from pynput.keyboard import GlobalHotKeys

        hotkeys = GlobalHotKeys({'<ctrl>+<up>': _toggle_overlay})
        hotkeys.daemon = True
        hotkeys.start()
        print("[Service] Hotkey Ctrl+↑ registrada.")
    except ImportError:
        print("[Service] pynput não instalado. Rode: pip install pynput")
    except Exception as e:
        print(f"[Service] Erro ao registrar hotkey: {e}")


def _install_startup():
    """Adiciona Stormy ao Task Scheduler para iniciar com o Windows."""
    import subprocess
    python = sys.executable
    script = os.path.abspath(__file__)
    task_name = "StormyService"

    cmd = (
        f'schtasks /create /tn "{task_name}" '
        f'/tr "\\"{python}\\" \\"{script}\\"" '
        f'/sc onlogon /rl highest /f'
    )
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"Stormy adicionada ao startup! Task: {task_name}")
        print("Ela vai iniciar automaticamente no próximo login.")
    else:
        print(f"Erro ao criar tarefa: {result.stderr}")


def _uninstall_startup():
    """Remove do Task Scheduler."""
    import subprocess
    result = subprocess.run(
        'schtasks /delete /tn "StormyService" /f',
        shell=True, capture_output=True, text=True
    )
    if result.returncode == 0:
        print("Stormy removida do startup.")
    else:
        print(f"Erro: {result.stderr}")


def _quit():
    """Encerra tudo."""
    print("[Service] Encerrando...")
    if _overlay:
        _overlay.destroy()
    _memory.close()
    os._exit(0)


def main():
    global _overlay, _tray

    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true", help="Adiciona ao startup do Windows")
    parser.add_argument("--uninstall", action="store_true", help="Remove do startup do Windows")
    args = parser.parse_args()

    if args.install:
        _install_startup()
        return
    if args.uninstall:
        _uninstall_startup()
        return

    print("[Service] Iniciando Stormy em background...")

    # Aquece o Ollama em background (carrega modelo na RAM)
    threading.Thread(target=_warmup_ollama, daemon=True).start()

    # Overlay (criado aqui mas mostrado só quando hotkey ativada)
    from overlay import StormyOverlay
    _overlay = StormyOverlay(on_send_callback=_send_message)

    # Tray
    from tray import StormyTray
    _tray = StormyTray(on_open=_toggle_overlay, on_quit=_quit)
    _tray.start()

    # Hotkey
    threading.Thread(target=_setup_hotkey, daemon=True).start()

    print("[Service] Pronta. Ctrl+↑ pra abrir. Ícone na bandeja.")

    # Tkinter DEVE rodar na thread principal
    _overlay.run()


if __name__ == "__main__":
    main()