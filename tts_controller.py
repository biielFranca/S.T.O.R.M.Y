"""
TTS Controller — Qwen3-TTS (Alibaba)
Clone de voz com 3s de audio, suporta português, open source.

Instalar: pip install qwen-tts

Sample de voz:
    Coloca um arquivo WAV em:
    D:/PROJETOS/S.T.O.R.M.Y/app/stormy_voice.wav
"""

import os
import re
import queue
import threading
import tempfile
from pathlib import Path

DEFAULT_VOICE = Path(__file__).parent / "stormy_voice.wav"
MODEL_ID      = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"  # mais leve, CPU friendly

_model       = None
_enabled     = True
_voice_wav   = str(DEFAULT_VOICE)
_queue       = queue.Queue()
_ready       = False


def _load_model():
    global _model, _ready
    try:
        from qwen_tts import Qwen3TTSModel
        import torch
        print(f"[TTS] Carregando {MODEL_ID}...")
        _model = Qwen3TTSModel.from_pretrained(
            MODEL_ID,
            device_map="cpu",
            dtype=torch.float32,
        )
        _ready = True
        print("[TTS] Qwen3-TTS pronto.")
    except Exception as e:
        print(f"[TTS] Erro ao carregar: {e}")
        _ready = False


def _normalize_text(text: str) -> str:
    replacements = {
        "kkk": "", "kkkk": "", "hauahau": "", "rs": "",
        "tbm": "também", "mto": "muito", "vdd": "verdade",
        "msm": "mesmo", "hj": "hoje", "pq": "porque",
        "prc": "parceiro", "cz": "cara",
    }
    for abbr, full in replacements.items():
        text = text.replace(abbr, full)
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
    if not _model or not _enabled:
        return
    text = _normalize_text(text)
    if not text.strip():
        return

    import soundfile as sf

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp_path = f.name

    try:
        voice = _voice_wav if Path(_voice_wav).exists() else None

        if voice:
            wavs, sr = _model.generate_voice_clone(
                text=text,
                language="Portuguese",
                ref_audio=voice,
            )
        else:
            # Sem sample — usa voz padrão do modelo via clone com audio dummy
            wavs, sr = _model.generate_voice_clone(
                text=text,
                language="Portuguese",
                ref_audio="hf://Qwen/Qwen3-TTS-voices/female_1.wav",
            )

        sf.write(tmp_path, wavs[0], sr)
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
    threading.Thread(target=_load_model, daemon=True).start()
    threading.Thread(target=_speak_worker, daemon=True, name="TTSWorker").start()


def speak(text: str):
    if not _enabled or not _ready:
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