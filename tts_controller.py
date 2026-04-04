"""
TTS Controller — Coqui XTTS v2
Clone de voz em português, roda na CPU.
"""

import os
import re
import queue
import threading
import tempfile
from pathlib import Path

os.environ["COQUI_TOS_AGREED"] = "1"

DEFAULT_VOICE = Path(__file__).parent / "stormy_voice.wav"

_tts     = None
_enabled = True
_voice   = str(DEFAULT_VOICE)
_queue   = queue.Queue()
_ready   = False


def _normalize_text(text: str) -> str:
    # Remove markdown
    text = re.sub(r'\*{1,3}(.+?)\*{1,3}', r'\1', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[-*]\s+', '', text, flags=re.MULTILINE)
    # Remove risadas e abreviações de riso
    text = re.sub(r'\b(kkk+|hauahau+|huehu+|rs)\b', '', text, flags=re.IGNORECASE)
    # Expande abreviações
    abbr = {
        'tbm': 'também', 'mto': 'muito', 'pq': 'porque',
        'hj': 'hoje', 'prc': 'parceiro', 'cz': 'cara',
        'vdd': 'verdade', 'msm': 'mesmo', 'tá': 'tá',
        'tô': 'tô', 'né': 'né', 'po': 'pô',
    }
    for abbr_k, full in abbr.items():
        text = re.sub(rf'\b{abbr_k}\b', full, text, flags=re.IGNORECASE)
    # Remove emojis
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    text = re.sub(r'[\u2600-\u27BF\u2B00-\u2BFF]', '', text)
    # Remove pontuação solta no final
    text = re.sub(r'[\.,!?]+$', '', text.strip())
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _play_audio(path: str):
    try:
        import pygame
        pygame.mixer.init()
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.wait(100)
    except Exception as e:
        print(f"[TTS] Erro ao tocar: {e}")


def _do_speak(text: str):
    if not _tts or not _enabled:
        return
    text = _normalize_text(text)
    if not text.strip():
        return

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp_path = f.name

    try:
        voice = _voice if Path(_voice).exists() else None
        _tts.tts_to_file(
            text=text,
            speaker_wav=voice,
            language="pt",
            file_path=tmp_path,
        )
        _play_audio(tmp_path)
    except Exception as e:
        print(f"[TTS] Erro ao gerar fala: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _speak_worker():
    while True:
        text = _queue.get()
        if text is None:
            break
        try:
            _do_speak(text)
        except Exception as e:
            print(f"[TTS] Erro no worker: {e}")
        finally:
            _queue.task_done()


def _load_model():
    global _tts, _ready
    try:
        from TTS.api import TTS
        print("[TTS] Carregando XTTS v2 (CPU)...")
        _tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
        _ready = True
        print("[TTS] Pronto.")
    except Exception as e:
        print(f"[TTS] Erro ao carregar: {e}")
        _ready = False


def init():
    threading.Thread(target=_load_model, daemon=True).start()
    threading.Thread(target=_speak_worker, daemon=True, name="TTSWorker").start()


def speak(text: str):
    if not _enabled or not _ready:
        return
    _queue.put(text)


def set_voice(wav_path: str) -> str:
    global _voice
    path = Path(wav_path)
    if not path.exists():
        return f"Arquivo não encontrado: {wav_path}"
    _voice = str(path)
    return f"Voz trocada para: {path.name}"


def set_enabled(value: bool) -> str:
    global _enabled
    _enabled = value
    return "TTS ativado." if value else "TTS desativado."


def is_ready() -> bool:
    return _ready


def is_enabled() -> bool:
    return _enabled
