import subprocess
import threading
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

import config
from agent import chat
from memory import ConversationMemory
from tts_controller import init as tts_init, speak

console = Console()
memory = ConversationMemory()

ENGINE_LABEL = {
    "lm_studio": "[dim]lm[/dim]",
    "claude":    "[dim]claude[/dim]",
    "local":     "[dim]local[/dim]",
}

_overlay    = None
_tray       = None
_print_lock = threading.Lock()
_wa_ready   = threading.Event()


def strip_wake_word(text: str) -> str:
    normalized = text.lower()
    for wake in config.WAKE_WORDS:
        if normalized.startswith(wake):
            return text[len(wake):].strip()
    return text


def _send_message(message: str) -> str:
    try:
        response, engine = chat(message, memory)
        label = ENGINE_LABEL.get(engine, engine)
        with _print_lock:
            console.print(f"\n[cyan]{config.ASSISTANT_NAME}:[/cyan] {response} [dim]{label}[/dim]")
        speak(response)
        return response
    except Exception as e:
        return f"erro: {e}"


def _toggle_overlay():
    if _overlay and _overlay._root:
        _overlay._root.after(0, _overlay.toggle)


def _start_tray():
    global _tray
    try:
        from tray import StormyTray
        _tray = StormyTray(on_open=_toggle_overlay, on_quit=lambda: None)
        _tray.start()
    except Exception as e:
        print(f"[Tray] Erro: {e}")


def _start_whatsapp():
    project_dir = str(Path(__file__).parent)

    # Flask server (whatsapp.py)
    try:
        from whatsapp import start as wa_start
        wa_start()
    except Exception as e:
        print(f"[WhatsApp] Servidor Python falhou: {e}")

    # Node.js bridge (whatsapp.js)
    try:
        subprocess.Popen(
            ["node", "whatsapp.js"],
            cwd=project_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("[WhatsApp] Bridge Node.js iniciada.")
    except FileNotFoundError:
        print("[WhatsApp] Node.js não encontrado, bridge indisponível.")
    except Exception as e:
        print(f"[WhatsApp] Erro ao iniciar bridge: {e}")

    # Aguarda conexão do WhatsApp, exibe painel e importa contatos
    def _delayed_import():
        import time
        import requests as _req

        # Polling: aguarda connected=true no Node (máx 60s)
        wa_connected = False
        for _ in range(20):
            time.sleep(3)
            try:
                r = _req.get("http://localhost:3001/status", timeout=5)
                if r.ok and r.json().get("connected"):
                    wa_connected = True
                    break
            except Exception:
                pass

        # Exibe painel de boas-vindas
        wa_status = "[green]WhatsApp conectado[/green]" if wa_connected else "[yellow]WhatsApp não conectado[/yellow]"
        if not wa_connected:
            print("[WhatsApp] Timeout — iniciando sem WhatsApp")
        with _print_lock:
            console.print(
                Panel.fit(
                    f"[bold cyan]{config.ASSISTANT_NAME} está pronta.[/bold cyan]\n\n"
                    f"  {wa_status}\n"
                    "[dim]  • Perguntar qualquer coisa — ciência, história, tecnologia...[/dim]\n"
                    "[dim]  • 'abre o spotify' / 'abre o youtube'[/dim]\n"
                    "[dim]  • 'pesquisa o clima em São Paulo hoje'[/dim]\n"
                    "[dim]  • Ctrl+↑ abre o overlay em qualquer momento[/dim]\n"
                    "[dim]  • 'sair' para encerrar[/dim]",
                    border_style="cyan",
                    title="Stormy",
                )
            )
        _wa_ready.set()

        if not wa_connected:
            return

        # Importa contatos
        try:
            from whatsapp import import_contacts_to_db, normalize_chat_names
            from database import get_connection

            try:
                resp = _req.get("http://localhost:3001/contacts", timeout=15)
                if resp.ok:
                    contacts = resp.json()
                    now = __import__("datetime").datetime.now().isoformat()

                    conn = get_connection()
                    conn.execute("DELETE FROM profiles")
                    conn.commit()
                    conn.close()

                    conn = get_connection()
                    count = 0
                    for c in contacts:
                        phone = c.get("number", "")
                        name = c.get("name", "") or phone
                        if not phone:
                            continue
                        conn.execute(
                            """INSERT OR REPLACE INTO profiles
                               (name, phone, created_at, updated_at)
                               VALUES (?, ?, ?, ?)""",
                            (name, phone, now, now),
                        )
                        count += 1
                    conn.commit()
                    conn.close()
                    print(f"[WhatsApp] Contatos atualizados: {count} contatos")
            except Exception as e:
                print(f"[WhatsApp] Erro ao atualizar contatos: {e}")
                import_contacts_to_db()

            normalize_chat_names()
        except Exception:
            pass

    threading.Thread(target=_delayed_import, daemon=True).start()


def _start_hotkey():
    try:
        from pynput.keyboard import GlobalHotKeys

        hotkeys = GlobalHotKeys({"<ctrl>+<Up>": _toggle_overlay})
        hotkeys.daemon = True
        hotkeys.start()
        print("[Stormy] Hotkey Ctrl+↑ registrada.")
    except Exception as e:
        print(f"[Stormy] Hotkey indisponível: {e}")


def _terminal_loop():
    import sys
    import termios
    import tty

    def _flush_stdin():
        """Drena bytes pendentes do stdin antes de cada input."""
        try:
            import select
            while select.select([sys.stdin], [], [], 0)[0]:
                sys.stdin.read(1)
        except Exception:
            pass

    try:
        while True:
            try:
                _flush_stdin()
                with _print_lock:
                    sys.stdout.write("\nVocê: ")
                    sys.stdout.flush()
                user_input = sys.stdin.readline()
                if user_input is None:
                    break
                user_input = user_input.strip()
            except (KeyboardInterrupt, EOFError):
                console.print(f"\n[cyan]{config.ASSISTANT_NAME}:[/cyan] Falou, prc!")
                break

            if not user_input:
                continue

            user_input = strip_wake_word(user_input)

            if user_input.lower() in config.EXIT_WORDS:
                console.print(f"[cyan]{config.ASSISTANT_NAME}:[/cyan] Falou, prc!")
                break

            try:
                response, engine = chat(user_input, memory)
                label = ENGINE_LABEL.get(engine, f"[dim]{engine}[/dim]")
                with _print_lock:
                    console.print(f"\n[cyan]{config.ASSISTANT_NAME}:[/cyan] {response} {label}")
                speak(response)
            except ValueError as e:
                with _print_lock:
                    console.print(f"\n[red]Configuração:[/red] {e}")
                break
            except Exception as e:
                with _print_lock:
                    console.print(f"\n[red]Erro:[/red] {e}")
    finally:
        memory.close()
        import os; os._exit(0)


def main() -> None:
    _start_whatsapp()

    threading.Thread(target=_start_tray, daemon=True).start()
    threading.Thread(target=_start_hotkey, daemon=True).start()
    tts_init()  # carrega XTTS v2 em background

    try:
        from overlay import StormyOverlay
        global _overlay
        _overlay = StormyOverlay(on_send_callback=_send_message)
        threading.Thread(target=_overlay.run, daemon=True).start()
        print("[Stormy] Overlay iniciado em thread separada.")
    except Exception as e:
        print(f"[Overlay] Indisponível ({e}), seguindo só com terminal.")

    _terminal_loop()


if __name__ == "__main__":
    main()
