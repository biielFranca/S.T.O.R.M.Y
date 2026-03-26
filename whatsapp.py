"""
WhatsApp bridge — recebe mensagens do whatsapp.js (Node.js)
e expõe funções para o agent/tools enviar mensagens.
"""

import threading
from datetime import datetime

import requests
from flask import Flask, request, jsonify

from database import get_connection, init_db

NODE_URL = "http://localhost:3001"

# ── Flask server ─────────────────────────────────────────────────────────────

_app = Flask(__name__)
_app.logger.disabled = True

import logging
logging.getLogger("werkzeug").setLevel(logging.ERROR)


@_app.route("/whatsapp/incoming", methods=["POST"])
def incoming():
    data = request.json
    if not data:
        return jsonify({"error": "payload vazio"}), 400

    chat_id = data.get("chat_id", "")
    chat_name = data.get("chat_name", "")
    sender_phone = data.get("sender_phone", "")
    sender_name = data.get("sender_name", "")
    message_id = data.get("message_id", "")
    message_type = data.get("message_type", "text")
    content = data.get("content", "")
    is_group = 1 if data.get("is_group") else 0
    timestamp = data.get("timestamp", 0)

    now = datetime.now().isoformat()

    # Salva no SQLite
    try:
        conn = get_connection()
        conn.execute(
            """INSERT OR IGNORE INTO whatsapp_messages
               (chat_id, chat_name, sender_phone, sender_name,
                message_id, message_type, content, is_group, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (chat_id, chat_name, sender_phone, sender_name,
             message_id, message_type, content, is_group, now),
        )

        # Áudio → fila de transcrição
        if message_type == "audio" and content:
            conn.execute(
                """INSERT INTO audio_transcriptions
                   (source, file_path, transcription, speaker_name, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                ("whatsapp", content, "pendente", sender_name, now),
            )

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[WhatsApp] Erro ao salvar no banco: {e}")

    # Print no terminal
    prefix = f"[{chat_name}] " if is_group else ""
    print(f"[WhatsApp] {prefix}{sender_name}: {content}")

    return jsonify({"ok": True})


# ── Funções públicas ─────────────────────────────────────────────────────────

def send_message(phone: str, message: str) -> str:
    try:
        r = requests.post(
            f"{NODE_URL}/send",
            json={"phone": phone, "message": message},
            timeout=15,
        )
        if r.ok:
            return f"Mensagem enviada para {phone}."
        return f"Erro ao enviar: {r.json().get('error', r.status_code)}"
    except requests.ConnectionError:
        return "WhatsApp offline — o whatsapp.js não está rodando."
    except Exception as e:
        return f"Erro ao enviar: {e}"


def send_to_group(group_id: str, message: str) -> str:
    try:
        r = requests.post(
            f"{NODE_URL}/send_to_group",
            json={"group_id": group_id, "message": message},
            timeout=15,
        )
        if r.ok:
            return f"Mensagem enviada no grupo."
        return f"Erro ao enviar: {r.json().get('error', r.status_code)}"
    except requests.ConnectionError:
        return "WhatsApp offline — o whatsapp.js não está rodando."
    except Exception as e:
        return f"Erro ao enviar: {e}"


def get_status() -> str:
    try:
        r = requests.get(f"{NODE_URL}/status", timeout=5)
        data = r.json()
        if data.get("connected"):
            return f"WhatsApp conectado — número: {data.get('number')}"
        return "WhatsApp desconectado."
    except requests.ConnectionError:
        return "WhatsApp offline — o whatsapp.js não está rodando."
    except Exception as e:
        return f"Erro ao checar status: {e}"


def get_recent_messages(chat_id: str, limit: int = 20) -> list[dict]:
    try:
        conn = get_connection()
        rows = conn.execute(
            """SELECT sender_name, message_type, content, created_at
               FROM whatsapp_messages
               WHERE chat_id = ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (chat_id, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in reversed(rows)]
    except Exception as e:
        return [{"error": str(e)}]


# ── Start server ─────────────────────────────────────────────────────────────

def start():
    """Inicia o servidor Flask em thread separada."""
    init_db()
    t = threading.Thread(
        target=lambda: _app.run(host="0.0.0.0", port=5000, debug=False),
        daemon=True,
    )
    t.start()
    print("[WhatsApp] Servidor Flask rodando na porta 5000.")
