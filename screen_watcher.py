"""
Screen Watcher — captura e analisa a tela continuamente.
Usa qwen2.5vl:3b via LM Studio (Vulkan — GPU AMD).

LM Studio expõe API compatível com OpenAI em localhost:1234.
Formato de imagem: content como lista com type image_url + base64.
"""

import base64
import json
import re
import threading
import time
from io import BytesIO

import pyautogui
import requests
from PIL import Image

LM_STUDIO_URL  = "http://localhost:1234/v1/chat/completions"
LM_STUDIO_MODELS = "http://localhost:1234/v1/models"

# Nome do modelo exatamente como aparece no LM Studio
# Ajusta se necessário após carregar o modelo lá
VISION_MODEL = "qwen2.5vl-3b"

CALL_TIMEOUT     = 120
CAPTURE_INTERVAL = 5
ANALYZE_EVERY    = 3
HISTORY_MAX      = 5

# Modo foco — troca pra modelo maior se quiser
_focus_mode  = False
FAST_MODEL   = "qwen2.5vl-3b"
FOCUS_MODEL  = "qwen2.5vl-7b"   # se baixar o 7b no LM Studio

_state = {
    "last_description": "",
    "last_screenshot":  None,
    "running":          False,
    "model_ready":      False,
    "has_car_game":     False,
    "current_app":      "",
}

_screenshot_history: list[dict] = []
_callbacks: list = []
_lock = threading.Lock()
_ollama_lock = threading.Lock()


# ── Modo de foco ───────────────────────────────────────────────────────────────

def set_focus_mode(active: bool) -> str:
    global _focus_mode
    _focus_mode = active
    return f"Modo {'foco' if active else 'rapido'} ativado."


def get_vision_model() -> str:
    return FOCUS_MODEL if _focus_mode else FAST_MODEL


# ── Callbacks ──────────────────────────────────────────────────────────────────

def on_context_change(callback) -> None:
    _callbacks.append(callback)


def get_current_context() -> dict:
    with _lock:
        return dict(_state)


# ── Captura ────────────────────────────────────────────────────────────────────

def _screenshot_b64(scale: float = 0.75) -> str:
    img = pyautogui.screenshot()
    w, h = img.size
    if w * scale > 1280:
        scale = 1280 / w
    img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


def get_screenshot_b64() -> str:
    with _lock:
        cached = _state.get("last_screenshot")
    return cached if cached else _screenshot_b64()


def get_best_screenshot() -> str:
    with _lock:
        if _screenshot_history:
            return _screenshot_history[-1]["b64"]
    return _screenshot_b64()


def get_recent_screenshots(n: int = 3) -> list[dict]:
    with _lock:
        return list(_screenshot_history[-n:])


# ── Chamada LM Studio ──────────────────────────────────────────────────────────

def _lm_stream(model: str, prompt: str, b64: str, timeout: int = CALL_TIMEOUT) -> str:
    """
    Chamada ao LM Studio com stream=True.
    Formato OpenAI: imagem como image_url com data URI base64.
    """
    try:
        resp = requests.post(
            LM_STUDIO_URL,
            json={
                "model": model,
                "messages": [{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64}"
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }],
                "stream": True,
                "temperature": 0,
                "max_tokens": 512,
            },
            timeout=timeout,
            stream=True,
        )
        resp.raise_for_status()

        result = ""
        for line in resp.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8") if isinstance(line, bytes) else line
            if line.startswith("data: "):
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    result += delta.get("content", "")
                except Exception:
                    continue
        return result.strip()

    except Exception as e:
        print(f"[ScreenWatcher] Erro na chamada: {e}")
        return ""


def _warmup_model() -> bool:
    """Verifica se o LM Studio tá rodando e o modelo carregado."""
    print(f"[ScreenWatcher] Verificando LM Studio...")
    try:
        resp = requests.get(LM_STUDIO_MODELS, timeout=10)
        if resp.status_code == 200:
            models = [m.get("id", "") for m in resp.json().get("data", [])]
            print(f"[ScreenWatcher] LM Studio online. Modelos: {models}")
            if models:
                # Usa o primeiro modelo disponível se o configurado não estiver
                global FAST_MODEL
                model_lower = [m.lower() for m in models]
                for m in models:
                    if "qwen" in m.lower() and "vl" in m.lower():
                        FAST_MODEL = m
                        break
                else:
                    FAST_MODEL = models[0]
                print(f"[ScreenWatcher] Usando modelo: {FAST_MODEL}")
            return True
    except Exception as e:
        print(f"[ScreenWatcher] LM Studio não encontrado ({e}).")
        print(f"[ScreenWatcher] Abre o LM Studio, carrega o modelo e reinicia.")
        return False
    return False


# ── Análise de contexto (não-bloqueante) ───────────────────────────────────────

def _analyze_screen_nonblocking(b64: str) -> dict | None:
    acquired = _ollama_lock.acquire(blocking=False)
    if not acquired:
        return None

    try:
        prompt = (
            "Analise essa tela e responda em JSON com os campos:\n"
            "- app: nome do app ou jogo aberto\n"
            "- context: descricao curta (max 20 palavras)\n"
            "- has_car_game: true se for jogo de corrida\n"
            "- has_racing_wheel: true se volante seria util\n"
            "- clickable_elements: lista dos 3 elementos mais relevantes\n"
            "Responda APENAS o JSON, sem texto extra."
        )
        text = _lm_stream(get_vision_model(), prompt, b64)
        if not text:
            return None
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    finally:
        _ollama_lock.release()

    return None


# ── Busca de elemento ──────────────────────────────────────────────────────────

def find_element_on_screen(description: str):
    """
    Encontra elemento na tela pela descrição e retorna (x, y) ou None.
    """
    FIND_SCALE = 0.75
    img_full = pyautogui.screenshot()
    w, h = img_full.size

    if w * FIND_SCALE > 1280:
        FIND_SCALE = 1280 / w

    w_scaled = int(w * FIND_SCALE)
    h_scaled = int(h * FIND_SCALE)

    img_resized = img_full.resize((w_scaled, h_scaled), Image.LANCZOS)
    buf = BytesIO()
    img_resized.save(buf, format="JPEG", quality=80)
    b64 = base64.b64encode(buf.getvalue()).decode()

    prompt = (
        f"Nessa tela, encontre o elemento: '{description}'\n"
        f"A imagem tem {w_scaled}x{h_scaled} pixels.\n"
        f"Responda APENAS com JSON: {{\"x\": numero, \"y\": numero, \"found\": true/false}}\n"
        f"x e y sao as coordenadas do centro do elemento em pixels nessa imagem."
    )

    with _ollama_lock:
        text = _lm_stream(get_vision_model(), prompt, b64)

    if not text:
        return None

    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            data = json.loads(match.group())
            if data.get("found") and data.get("x") and data.get("y"):
                real_x = int(data["x"] / FIND_SCALE)
                real_y = int(data["y"] / FIND_SCALE)
                return real_x, real_y
    except Exception:
        pass

    return None


# ── Descrição sob demanda ──────────────────────────────────────────────────────

def describe(prompt: str = "O que está acontecendo nessa tela? Descreva brevemente.") -> str:
    if not _state.get("model_ready"):
        return "Modelo de visão ainda carregando, aguarde."
    b64 = get_screenshot_b64()
    with _ollama_lock:
        result = _lm_stream(get_vision_model(), prompt, b64)
    return result if result else "Não consegui analisar a tela agora."


# ── Loop principal ─────────────────────────────────────────────────────────────

def _watch_loop():
    ready = _warmup_model()
    with _lock:
        _state["model_ready"] = ready

    last_app = ""
    tick = 0

    while _state["running"]:
        try:
            b64 = _screenshot_b64()
            with _lock:
                _state["last_screenshot"] = b64

            if tick % ANALYZE_EVERY == 0 and ready:
                result = _analyze_screen_nonblocking(b64)

                if result:
                    with _lock:
                        _state["last_description"] = result.get("context", "")
                        _state["has_car_game"]      = result.get("has_car_game", False)
                        _state["current_app"]       = result.get("app", "")
                        _screenshot_history.append({
                            "b64":         b64,
                            "description": result.get("context", ""),
                            "app":         result.get("app", ""),
                            "timestamp":   time.time(),
                        })
                        if len(_screenshot_history) > HISTORY_MAX:
                            _screenshot_history.pop(0)

                    current_app = result.get("app", "")
                    if current_app != last_app:
                        last_app = current_app
                        for cb in _callbacks:
                            try:
                                cb(result)
                            except Exception:
                                pass

        except Exception as e:
            print(f"[ScreenWatcher] Erro no loop: {e}")

        tick += 1
        time.sleep(CAPTURE_INTERVAL)


# ── Interface pública ──────────────────────────────────────────────────────────

_auto_stop_timer = None
AUTO_STOP_SECONDS = 300  # 5 minutos


def _schedule_auto_stop():
    global _auto_stop_timer
    if _auto_stop_timer:
        _auto_stop_timer.cancel()
    _auto_stop_timer = threading.Timer(AUTO_STOP_SECONDS, stop)
    _auto_stop_timer.daemon = True
    _auto_stop_timer.start()


def start() -> None:
    global _auto_stop_timer
    if _state["running"]:
        _schedule_auto_stop()  # renova o timer se já tiver rodando
        return
    _state["running"] = True
    threading.Thread(target=_watch_loop, daemon=True, name="ScreenWatcher").start()
    print("[ScreenWatcher] Iniciado.")
    _schedule_auto_stop()


def stop() -> None:
    global _auto_stop_timer
    _state["running"] = False
    if _auto_stop_timer:
        _auto_stop_timer.cancel()
        _auto_stop_timer = None
    print("[ScreenWatcher] Parado.")