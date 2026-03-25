"""
Sincronização entre SQLite local e Supabase.
- Mensagens sobem para o Supabase em tempo real
- Estado do device é mantido atualizado
- Comandos remotos são recebidos e executados
"""

import os
import threading
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

_available = bool(SUPABASE_URL and SUPABASE_KEY)


def _headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def is_available() -> bool:
    return _available


def _post(table: str, data: dict) -> bool:
    if not _available:
        return False
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=_headers(),
            json=data,
            timeout=5,
        )
        return r.status_code in (200, 201)
    except Exception:
        return False


def _patch(table: str, filters: dict, data: dict) -> bool:
    if not _available:
        return False
    try:
        params = "&".join(f"{k}=eq.{v}" for k, v in filters.items())
        r = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{table}?{params}",
            headers=_headers(),
            json=data,
            timeout=5,
        )
        return r.status_code in (200, 204)
    except Exception:
        return False


def _get(table: str, params: dict = None) -> list:
    if not _available:
        return []
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers={**_headers(), "Prefer": "return=representation"},
            params=params or {},
            timeout=5,
        )
        if r.status_code == 200:
            return r.json()
        return []
    except Exception:
        return []


# ── Sessões ───────────────────────────────────────────────────────────────────

def sync_session_start(device: str = "pc") -> int | None:
    """Cria sessão no Supabase e retorna o ID remoto."""
    if not _available:
        return None
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/sessions",
            headers={**_headers(), "Prefer": "return=representation"},
            json={"device": device, "is_active": True},
            timeout=5,
        )
        if r.status_code in (200, 201):
            data = r.json()
            return data[0]["id"] if isinstance(data, list) else data.get("id")
    except Exception:
        pass
    return None


def sync_session_end(remote_session_id: int) -> None:
    if not remote_session_id:
        return
    _patch("sessions", {"id": remote_session_id}, {
        "ended_at": datetime.now().isoformat(),
        "is_active": False,
    })


# ── Mensagens ─────────────────────────────────────────────────────────────────

def sync_message(
    role: str,
    content: str,
    engine: str = None,
    device: str = "pc",
    remote_session_id: int = None,
) -> None:
    """Sincroniza uma mensagem com o Supabase em thread separada."""
    if not _available or not isinstance(content, str):
        return

    def _upload():
        _post("messages", {
            "role": role,
            "content": content,
            "engine": engine,
            "device": device,
            "session_id": remote_session_id,
        })

    threading.Thread(target=_upload, daemon=True).start()


# ── Device State ──────────────────────────────────────────────────────────────

def update_device_state(device: str) -> None:
    """Atualiza qual device está ativo."""
    if not _available:
        return

    now = datetime.now().isoformat()
    field = "last_seen_pc" if device == "pc" else "last_seen_phone"

    _patch("device_state", {"id": 1}, {
        "active_device": device,
        field: now,
        "updated_at": now,
    })


def get_active_device() -> str:
    """Retorna qual device está ativo no momento."""
    rows = _get("device_state", {"id": "eq.1"})
    if rows:
        return rows[0].get("active_device", "pc")
    return "pc"


def request_handoff(from_device: str, to_device: str) -> bool:
    """Solicita handoff — transfere consciência para outro device."""
    return _post("remote_commands", {
        "from_device": from_device,
        "to_device": to_device,
        "command": "handoff",
        "payload": {"timestamp": datetime.now().isoformat()},
        "status": "pending",
    })


# ── Comandos Remotos ──────────────────────────────────────────────────────────

def get_pending_commands(device: str) -> list:
    """Busca comandos pendentes para este device."""
    return _get("remote_commands", {
        "to_device": f"eq.{device}",
        "status": "eq.pending",
        "order": "created_at.asc",
    })


def mark_command_executed(command_id: int) -> None:
    _patch("remote_commands", {"id": command_id}, {
        "status": "executed",
        "executed_at": datetime.now().isoformat(),
    })


# ── Polling de comandos ───────────────────────────────────────────────────────

_command_callbacks: list = []


def on_command(callback) -> None:
    """Registra callback para quando um comando remoto chegar."""
    _command_callbacks.append(callback)


def start_polling(device: str = "pc", interval: int = 3) -> None:
    """Inicia polling de comandos remotos em background."""
    if not _available:
        return

    def _poll():
        while True:
            try:
                commands = get_pending_commands(device)
                for cmd in commands:
                    for cb in _command_callbacks:
                        cb(cmd)
                    mark_command_executed(cmd["id"])
            except Exception:
                pass
            time.sleep(interval)

    t = threading.Thread(target=_poll, daemon=True)
    t.start()


# ── Histórico remoto ──────────────────────────────────────────────────────────

def fetch_recent_messages(limit: int = 50) -> list[dict]:
    """Busca mensagens recentes do Supabase para sincronizar ao trocar de device."""
    rows = _get("messages", {
        "order": "created_at.desc",
        "limit": str(limit),
    })
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
