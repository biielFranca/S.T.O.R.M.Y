"""
Memória da Stormy — RAM (sessão atual) + SQLite (local) + Supabase (sync).
"""

import config
from database import end_session, load_recent_messages, save_message, start_session
from sync import (
    is_available,
    start_polling,
    sync_message,
    sync_session_end,
    sync_session_start,
    update_device_state,
)


class ConversationMemory:
    def __init__(self, device: str = "pc") -> None:
        self._messages: list[dict] = []
        self._device = device

        # Sessão local
        self._session_id = start_session(device)

        # Sessão remota (Supabase)
        self._remote_session_id = sync_session_start(device) if is_available() else None

        # Atualiza device ativo no Supabase
        if is_available():
            update_device_state(device)
            start_polling(device)

        # Carrega histórico
        self._load_history()

    def _load_history(self) -> None:
        history = load_recent_messages(limit=config.MEMORY_MAX_MESSAGES)
        self._messages = history

    def add_user(self, text: str) -> None:
        self._messages.append({"role": "user", "content": text})
        save_message(self._session_id, "user", text)
        sync_message("user", text, device=self._device,
                     remote_session_id=self._remote_session_id)
        self._trim()

    def add_assistant(self, content: str | list, engine: str = None) -> None:
        if isinstance(content, str):
            text_to_save = content
        elif isinstance(content, list):
            parts = [b.text for b in content if hasattr(b, "text")]
            text_to_save = " ".join(parts).strip() if parts else None
        else:
            text_to_save = None

        if text_to_save:
            save_message(self._session_id, "assistant", text_to_save, engine)
            sync_message("assistant", text_to_save, engine=engine,
                         device=self._device,
                         remote_session_id=self._remote_session_id)

        self._messages.append({"role": "assistant", "content": content})
        self._trim()

    def add_tool_results(self, results: list[dict]) -> None:
        self._messages.append({"role": "user", "content": results})

    def get(self) -> list[dict]:
        return list(self._messages)

    def clear(self) -> None:
        self._messages.clear()

    def close(self) -> None:
        end_session(self._session_id)
        if self._remote_session_id:
            sync_session_end(self._remote_session_id)

    def _trim(self) -> None:
        while len(self._messages) > config.MEMORY_MAX_MESSAGES:
            self._messages.pop(0)
