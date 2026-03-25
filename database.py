"""
Banco de dados local da Stormy — SQLite.
Guarda tudo para sempre: conversas, perfis, fatos, sessões,
mensagens do WhatsApp, transcrições de áudio e impressões vocais.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import config

DB_PATH = Path(__file__).parent / "stormy.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # melhor performance
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Cria todas as tabelas se não existirem."""
    conn = get_connection()
    c = conn.cursor()

    # ── Sessões ──────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at  TEXT NOT NULL,
            ended_at    TEXT,
            device      TEXT DEFAULT 'pc',
            notes       TEXT
        )
    """)

    # ── Mensagens da conversa com a Stormy ───────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER REFERENCES sessions(id),
            role        TEXT NOT NULL,   -- 'user' | 'assistant'
            content     TEXT NOT NULL,
            engine      TEXT,            -- 'ollama' | 'claude'
            created_at  TEXT NOT NULL
        )
    """)

    # ── Perfis de pessoas ─────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            nickname        TEXT,
            phone           TEXT UNIQUE,
            relation        TEXT,        -- 'owner' | 'friend' | 'family' | 'work' | 'unknown'
            voice_sample    TEXT,        -- caminho do arquivo de amostra vocal
            voice_embedding TEXT,        -- JSON com vetor de impressão vocal
            avatar          TEXT,        -- caminho da foto
            notes           TEXT,
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        )
    """)

    # ── Fatos aprendidos sobre pessoas ───────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS facts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id  INTEGER REFERENCES profiles(id),
            category    TEXT,   -- 'preference' | 'habit' | 'info' | 'event'
            key         TEXT NOT NULL,
            value       TEXT NOT NULL,
            source      TEXT,   -- 'conversation' | 'whatsapp' | 'voice' | 'manual'
            confidence  REAL DEFAULT 1.0,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
    """)

    # ── Mensagens do WhatsApp ─────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS whatsapp_messages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id         TEXT NOT NULL,   -- ID do chat no WhatsApp
            chat_name       TEXT,            -- nome do grupo ou contato
            sender_phone    TEXT,
            sender_name     TEXT,
            message_id      TEXT UNIQUE,     -- ID original do WhatsApp
            message_type    TEXT,            -- 'text' | 'audio' | 'image' | 'video' | 'doc'
            content         TEXT,            -- texto ou caminho do arquivo
            transcription   TEXT,            -- transcrição se for áudio
            is_group        INTEGER DEFAULT 0,
            created_at      TEXT NOT NULL,
            processed       INTEGER DEFAULT 0
        )
    """)

    # ── Transcrições de áudio ─────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS audio_transcriptions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            source          TEXT,       -- 'whatsapp' | 'microphone' | 'system'
            file_path       TEXT,
            transcription   TEXT NOT NULL,
            speaker_id      INTEGER REFERENCES profiles(id),
            speaker_name    TEXT,
            duration_sec    REAL,
            language        TEXT DEFAULT 'pt',
            confidence      REAL,
            created_at      TEXT NOT NULL
        )
    """)

    # ── Impressões vocais (para identificar pessoas pela voz) ─────
    c.execute("""
        CREATE TABLE IF NOT EXISTS voice_profiles (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id  INTEGER REFERENCES profiles(id) UNIQUE,
            embedding   TEXT NOT NULL,   -- JSON com vetor da voz
            samples     INTEGER DEFAULT 0,
            updated_at  TEXT NOT NULL
        )
    """)

    # ── Preferências e configurações da Stormy ───────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key         TEXT PRIMARY KEY,
            value       TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
    """)

    # ── Eventos e ações executadas ────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            type        TEXT NOT NULL,   -- 'app_opened' | 'search' | 'task_learned' | etc
            detail      TEXT,            -- JSON com detalhes
            profile_id  INTEGER REFERENCES profiles(id),
            created_at  TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()
    print(f"Banco inicializado em {DB_PATH}")


# ── Sessions ──────────────────────────────────────────────────────────────────

def start_session(device: str = "pc") -> int:
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO sessions (started_at, device) VALUES (?, ?)",
        (datetime.now().isoformat(), device)
    )
    session_id = c.lastrowid
    conn.commit()
    conn.close()
    return session_id


def end_session(session_id: int) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE sessions SET ended_at = ? WHERE id = ?",
        (datetime.now().isoformat(), session_id)
    )
    conn.commit()
    conn.close()


# ── Messages ──────────────────────────────────────────────────────────────────

def save_message(
    session_id: int,
    role: str,
    content: str,
    engine: str = None,
) -> None:
    if not isinstance(content, str):
        return
    conn = get_connection()
    conn.execute(
        "INSERT INTO messages (session_id, role, content, engine, created_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, role, content, engine, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def load_recent_messages(limit: int = 50) -> list[dict]:
    """Carrega as últimas N mensagens para contexto."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def search_messages(query: str, limit: int = 20) -> list[dict]:
    """Busca mensagens por conteúdo."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT role, content, created_at FROM messages WHERE content LIKE ? ORDER BY id DESC LIMIT ?",
        (f"%{query}%", limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Profiles ──────────────────────────────────────────────────────────────────

def get_or_create_profile(name: str, phone: str = None, relation: str = "unknown") -> int:
    conn = get_connection()
    now = datetime.now().isoformat()

    if phone:
        row = conn.execute("SELECT id FROM profiles WHERE phone = ?", (phone,)).fetchone()
    else:
        row = conn.execute("SELECT id FROM profiles WHERE name = ?", (name,)).fetchone()

    if row:
        conn.close()
        return row["id"]

    c = conn.cursor()
    c.execute(
        "INSERT INTO profiles (name, phone, relation, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (name, phone, relation, now, now)
    )
    profile_id = c.lastrowid
    conn.commit()
    conn.close()
    return profile_id


def update_profile(profile_id: int, **kwargs) -> None:
    kwargs["updated_at"] = datetime.now().isoformat()
    fields = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [profile_id]
    conn = get_connection()
    conn.execute(f"UPDATE profiles SET {fields} WHERE id = ?", values)
    conn.commit()
    conn.close()


def get_profile(profile_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_profiles() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM profiles ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Facts ─────────────────────────────────────────────────────────────────────

def save_fact(
    profile_id: int,
    key: str,
    value: str,
    category: str = "info",
    source: str = "conversation",
) -> None:
    now = datetime.now().isoformat()
    conn = get_connection()

    existing = conn.execute(
        "SELECT id FROM facts WHERE profile_id = ? AND key = ?",
        (profile_id, key)
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE facts SET value = ?, updated_at = ? WHERE id = ?",
            (value, now, existing["id"])
        )
    else:
        conn.execute(
            "INSERT INTO facts (profile_id, category, key, value, source, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (profile_id, category, key, value, source, now, now)
        )

    conn.commit()
    conn.close()


def get_facts(profile_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM facts WHERE profile_id = ? ORDER BY category, key",
        (profile_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── WhatsApp ──────────────────────────────────────────────────────────────────

def save_whatsapp_message(
    chat_id: str,
    chat_name: str,
    sender_phone: str,
    sender_name: str,
    message_id: str,
    message_type: str,
    content: str,
    is_group: bool = False,
) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO whatsapp_messages
               (chat_id, chat_name, sender_phone, sender_name, message_id,
                message_type, content, is_group, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (chat_id, chat_name, sender_phone, sender_name, message_id,
             message_type, content, int(is_group), datetime.now().isoformat())
        )
        conn.commit()
    finally:
        conn.close()


def save_audio_transcription(
    transcription: str,
    source: str = "whatsapp",
    file_path: str = None,
    speaker_name: str = None,
    speaker_id: int = None,
    duration_sec: float = None,
) -> int:
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """INSERT INTO audio_transcriptions
           (source, file_path, transcription, speaker_id, speaker_name, duration_sec, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (source, file_path, transcription, speaker_id, speaker_name,
         duration_sec, datetime.now().isoformat())
    )
    trans_id = c.lastrowid
    conn.commit()
    conn.close()
    return trans_id


# ── Settings ──────────────────────────────────────────────────────────────────

def get_setting(key: str, default: str = None) -> str | None:
    conn = get_connection()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    now = datetime.now().isoformat()
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
        (key, value, now)
    )
    conn.commit()
    conn.close()


# ── Events ────────────────────────────────────────────────────────────────────

def log_event(event_type: str, detail: dict = None, profile_id: int = None) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO events (type, detail, profile_id, created_at) VALUES (?, ?, ?, ?)",
        (event_type, json.dumps(detail or {}), profile_id, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


# Inicializa o banco ao importar
init_db()
