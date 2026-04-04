"""
TTS Controller — Coqui XTTS v2
Clone de voz em português, roda na CPU.

Instalar: pip install TTS pygame
Sample de voz: coloca um arquivo WAV em stormy_voice.wav (mesma pasta deste arquivo).
"""

import os
import re
import queue
import threading
import tempfile
from pathlib import Path

# Aceita a licença do Coqui automaticamente antes de qualquer import do TTS
os.environ["COQUI_TOS_AGREED"] = "1"

DEFAULT_VOICE = Path(__file__).parent / "stormy_voice.wav"

_tts      = None
_enabled  = True
_voice_wav = str(DEFAULT_VOICE)
_queue    = queue.Queue()
_ready    = False

# Regex para remover emojis
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002700-\U000027BF"
    "\U0001F900-\U0001F9FF"
    "\U00002600-\U000026FF"
    "\U00010000-\U0010FFFF"
    "]+",
    flags=re.UNICODE,
)

# Abreviações para expandir (ordem importa: mais longas primeiro)
_ABBREVS = [
    ("hauahau", ""),
    ("haha",    ""),
    ("kkk+",    ""),  # tratado via regex abaixo
    ("tbm",     "também"),
    ("mto",     "muito"),
    ("pq",      "porque"),
    ("hj",      "hoje"),
    ("prc",     "parceiro"),
    ("cz",      "cara"),
    ("vdd",     "verdade"),
    ("msm",     "mesmo"),
    ("rs",      ""),
]


def _normalize_text(text: str) -> str:
    # Remove blocos de código e markdown
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]+`", "", text)
    # Remove negrito/itálico markdown
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)
    # Remove links markdown [texto](url) → texto
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove URLs
    text = re.sub(r"https?://\S+", "", text)

    # Remove emojis
    text = _EMOJI_RE.sub("", text)

    # Expande abreviações (word boundary)
    text = re.sub(r"\bk{3,}\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bhauahau\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\brs\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\btbm\b", "também", text, flags=re.IGNORECASE)
    text = re.sub(r"\bmto\b", "muito", text, flags=re.IGNORECASE)
    text = re.sub(r"\bpq\b", "porque", text, flags=re.IGNORECASE)
    text = re.sub(r"\bhj\b", "hoje", text, flags=re.IGNORECASE)
    text = re.sub(r"\bprc\b", "parceiro", text, flags=re.IGNORECASE)
    text = re.sub(r"\bcz\b", "cara", text, flags=re.IGNORECASE)
    text = re.sub(r"\bvdd\b", "verdade", text, flags=re.IGNORECASE)
    text = re.sub(r"\bmsm\b", "mesmo", text, flags=re.IGNORECASE)

    # Remove pontuação solta no final (., ,, !, ? isolados)
    text = re.sub(r"\s+[.,!?]\s*$", "", text)

    # Normaliza espaços
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _load_model():
    global _tts, _ready
    try:
        from TTS.api import TTS
        print("[TTS] Carregando Coqui XTTS v2 na CPU...")
        _tts = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2", progress_bar=False).to("cpu")
        _ready = True
        print("[TTS] Coqui XTTS v2 pronto.")
    except Exception as e:
        print(f"[TTS] Erro ao carregar modelo: {e}")
        _ready = False


def _play_audio(path: str):
    try:
        import pygame
        pygame.mixer.init()
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.wait(100)
    except Exception as e:
        print(f"[TTS] Erro ao tocar áudio: {e}")


def _do_speak(text: str):
    if not _tts or not _enabled:
        return
    text = _normalize_text(text)
    if not text.strip():
        return

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp_path = f.name

    try:
        speaker_wav = _voice_wav if Path(_voice_wav).exists() else None
        _tts.tts_to_file(
            text=text,
            speaker_wav=speaker_wav,
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


# ── Interface pública ──────────────────────────────────────────────────────────

def init():
    threading.Thread(target=_load_model, daemon=True, name="TTSLoader").start()
    threading.Thread(target=_speak_worker, daemon=True, name="TTSWorker").start()


def speak(text: str):
    if not _ready or not _enabled:
        return
    _queue.put(text)


def set_voice(wav_path: str) -> str:
    global _voice_wav
    path = Path(wav_path)
    if not path.exists():
        return f"Arquivo não encontrado: {wav_path}"
    _voice_wav = str(path)
    return f"Voz trocada para: {path.name}"


def set_enabled(value: bool) -> str:
    global _enabled
    _enabled = value
    return "TTS ativado." if value else "TTS desativado."


def is_ready() -> bool:
    return _ready


def is_enabled() -> bool:
    return _enabled
