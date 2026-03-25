"""
G29 Reader — leitura do volante, pedais e marcha Logitech G29.
Usa pygame para acessar o joystick via DirectInput no Windows.
"""

import threading
import time

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

_state = {
    "steering":   0.0,    # -1.0 (esq) a 1.0 (dir)
    "throttle":   0.0,    # 0.0 a 1.0
    "brake":      0.0,    # 0.0 a 1.0
    "clutch":     0.0,    # 0.0 a 1.0
    "gear":       0,      # 0=neutro, 1-6, -1=re
    "buttons":    {},
    "connected":  False,
    "running":    False,
}

_callbacks = []
_lock = threading.Lock()
_joystick = None

# Mapeamento de eixos do G29 no Windows
AXIS_STEERING  = 0
AXIS_THROTTLE  = 1
AXIS_BRAKE     = 2
AXIS_CLUTCH    = 3

# Botoes do H-shifter (marcha sequencial no G29)
GEAR_BUTTONS = {
    12: 1,   # 1a marcha
    13: 2,   # 2a marcha
    14: 3,   # 3a marcha
    15: 4,   # 4a marcha
    16: 5,   # 5a marcha
    17: 6,   # 6a marcha
    18: -1,  # marcha re
}


def on_input_change(callback):
    _callbacks.append(callback)


def get_state() -> dict:
    with _lock:
        return dict(_state)


def _normalize_axis(value: float, inverted: bool = False) -> float:
    normalized = (value + 1.0) / 2.0
    return 1.0 - normalized if inverted else normalized


def _read_loop():
    global _joystick

    if not PYGAME_AVAILABLE:
        return

    pygame.init()
    pygame.joystick.init()

    if pygame.joystick.get_count() == 0:
        with _lock:
            _state["connected"] = False
        return

    _joystick = pygame.joystick.Joystick(0)
    _joystick.init()

    with _lock:
        _state["connected"] = True

    prev_state = {}

    while _state["running"]:
        pygame.event.pump()

        raw_steering = _joystick.get_axis(AXIS_STEERING)
        raw_throttle = _joystick.get_axis(AXIS_THROTTLE)
        raw_brake    = _joystick.get_axis(AXIS_BRAKE)
        raw_clutch   = _joystick.get_axis(AXIS_CLUTCH) if _joystick.get_numaxes() > 3 else -1.0

        steering = raw_steering  # -1 a 1
        throttle = _normalize_axis(raw_throttle, inverted=True)
        brake    = _normalize_axis(raw_brake, inverted=True)
        clutch   = _normalize_axis(raw_clutch, inverted=True)

        # Detecta marcha pelo H-shifter
        gear = 0
        for btn_idx, gear_val in GEAR_BUTTONS.items():
            if btn_idx < _joystick.get_numbuttons() and _joystick.get_button(btn_idx):
                gear = gear_val
                break

        buttons = {
            i: bool(_joystick.get_button(i))
            for i in range(min(_joystick.get_numbuttons(), 24))
        }

        new_state = {
            "steering":  round(steering, 3),
            "throttle":  round(throttle, 3),
            "brake":     round(brake, 3),
            "clutch":    round(clutch, 3),
            "gear":      gear,
            "buttons":   buttons,
            "connected": True,
        }

        with _lock:
            _state.update(new_state)

        if new_state != prev_state:
            for cb in _callbacks:
                try:
                    cb(new_state)
                except Exception:
                    pass
            prev_state = new_state.copy()

        time.sleep(0.016)  # ~60hz

    pygame.quit()


def start():
    if _state["running"] or not PYGAME_AVAILABLE:
        return
    _state["running"] = True
    threading.Thread(target=_read_loop, daemon=True).start()


def stop():
    _state["running"] = False


def is_connected() -> bool:
    return _state["connected"]


def get_steering_direction() -> str:
    s = _state["steering"]
    if abs(s) < 0.1:
        return "reto"
    if s < -0.5:
        return "muito a esquerda"
    if s < -0.1:
        return "esquerda"
    if s > 0.5:
        return "muito a direita"
    return "direita"
