"""
WhatsApp bridge — recebe mensagens do whatsapp.js (Node.js)
e expõe funções para o agent/tools enviar mensagens.
"""

import threading
from collections import deque
from datetime import datetime

import requests
from flask import Flask, request, jsonify

from database import get_connection, init_db

NODE_URL = "http://localhost:3001"

# ── Fila de notificações ────────────────────────────────────────────────────

_notification_queue = deque(maxlen=20)

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

    # Adiciona à fila de notificações (com filtro)
    _GRUPO_SPAM = (
        "promoç", "oferta", "cupom", "tech", "news", "notícia",
        "esporte", "lance", "uol", "g1", "tnt", "pack", "figurinha", "meme",
    )
    _should_notify = True
    _is_only_numbers = sender_name.strip().isdigit()

    if _is_only_numbers:
        _should_notify = False
    elif is_group:
        chat_lower = chat_name.lower()
        if any(spam in chat_lower for spam in _GRUPO_SPAM):
            _should_notify = False
        else:
            # Só notifica se o sender está nos profiles (contato conhecido)
            try:
                conn2 = get_connection()
                known = conn2.execute(
                    "SELECT id FROM profiles WHERE phone = ? LIMIT 1",
                    (sender_phone,),
                ).fetchone()
                conn2.close()
                _should_notify = known is not None
            except Exception:
                _should_notify = False

    if _should_notify:
        _notification_queue.append({
            "sender_name": sender_name,
            "chat_name": chat_name,
            "is_group": bool(is_group),
            "message_type": message_type,
        })

    return jsonify({"ok": True})


# ── Notificações ────────────────────────────────────────────────────────────

def get_pending_notifications() -> list[dict]:
    """Retorna notificações pendentes e limpa a fila."""
    items = list(_notification_queue)
    _notification_queue.clear()
    return items


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


def get_contacts() -> list[dict]:
    try:
        r = requests.get(f"{NODE_URL}/contacts", timeout=15)
        if r.ok:
            return r.json()
        return [{"error": r.json().get("error", r.status_code)}]
    except requests.ConnectionError:
        return [{"error": "WhatsApp offline — o whatsapp.js não está rodando."}]
    except Exception as e:
        return [{"error": str(e)}]


def import_contacts_to_db() -> str:
    contacts = get_contacts()
    if contacts and "error" in contacts[0]:
        return contacts[0]["error"]

    imported = 0
    try:
        conn = get_connection()
        now = datetime.now().isoformat()
        for c in contacts:
            phone = c.get("number", "")
            name = c.get("name", "") or phone
            if not phone:
                continue
            existing = conn.execute(
                "SELECT id FROM profiles WHERE phone = ?", (phone,)
            ).fetchone()
            if not existing:
                conn.execute(
                    """INSERT INTO profiles (name, phone, relation, created_at, updated_at)
                       VALUES (?, ?, 'unknown', ?, ?)""",
                    (name, phone, now, now),
                )
                imported += 1
        conn.commit()
        conn.close()
    except Exception as e:
        return f"Erro ao importar: {e}"
    return f"{imported} contatos importados pro banco."


def find_contact_by_name(name: str) -> str:
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT name, phone FROM profiles WHERE name LIKE ? LIMIT 5",
            (f"%{name}%",),
        ).fetchall()
        conn.close()
        if not rows:
            return f"Nenhum contato encontrado com '{name}'."
        lines = [f"{r['name']} — {r['phone']}" for r in rows]
        return "\n".join(lines)
    except Exception as e:
        return f"Erro ao buscar contato: {e}"


def get_chat_id_by_name(name: str) -> str | None:
    """Busca chat_id na tabela whatsapp_messages pelo chat_name ou pelo phone via profiles."""
    try:
        conn = get_connection()
        # Tenta nome completo primeiro
        row = conn.execute(
            "SELECT chat_id FROM whatsapp_messages WHERE chat_name LIKE ? LIMIT 1",
            (f"%{name}%",),
        ).fetchone()
        if row:
            conn.close()
            return row["chat_id"]
        # Tenta cada palavra separadamente
        for word in name.split():
            if len(word) < 2:
                continue
            row = conn.execute(
                "SELECT chat_id FROM whatsapp_messages WHERE chat_name LIKE ? LIMIT 1",
                (f"%{word}%",),
            ).fetchone()
            if row:
                conn.close()
                return row["chat_id"]
        # Busca phone na tabela profiles pelo nome
        profile = conn.execute(
            "SELECT phone FROM profiles WHERE name LIKE ? LIMIT 1",
            (f"%{name}%",),
        ).fetchone()
        if profile and profile["phone"]:
            phone = profile["phone"]
            row = conn.execute(
                "SELECT chat_id FROM whatsapp_messages WHERE chat_id LIKE ? OR chat_name LIKE ? LIMIT 1",
                (f"%{phone}%", f"%{phone}%"),
            ).fetchone()
            if row:
                conn.close()
                return row["chat_id"]
        conn.close()
        return None
    except Exception:
        return None


def get_recent_messages(chat_id: str, limit: int = 20) -> list[dict]:
    try:
        conn = get_connection()
        rows = conn.execute(
            """SELECT sender_name, message_type, content, created_at
               FROM whatsapp_messages
               WHERE chat_id = ? AND message_type = 'text'
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


if __name__ == "__main__":
    start()
    import time
    while True:
        time.sleep(1)
