"""
Input Mapper — converte input do G29 em teclas do teclado.
Permite jogar qualquer jogo com o volante mesmo sem suporte nativo.
Suporta mapeamento manual, automatico e aprendizado por observacao.
"""

import json
import threading
import time
from pathlib import Path

import pyautogui

from g29_reader import get_state, on_input_change, start as start_g29

MAPS_FILE = Path(__file__).parent / "input_maps.json"

# Mapeamento padrao (pode ser sobrescrito por jogo)
DEFAULT_MAP = {
    "steering_left_mild":   ["a"],          # 10-40% esquerda
    "steering_left_strong": ["a"],          # 40%+ esquerda
    "steering_right_mild":  ["d"],          # 10-40% direita
    "steering_right_strong":["d"],          # 40%+ direita
    "throttle":             ["w"],          # acelerar
    "brake":                ["s"],          # frear
    "clutch":               [],             # embreagem (maioria ignora)
    "gear_1":               [],
    "gear_2":               [],
    "gear_3":               [],
    "gear_4":               [],
    "gear_5":               [],
    "gear_6":               [],
    "gear_r":               ["b"],          # marcha re
    "handbrake":            ["space"],      # freio de mao (botao 23 do G29)
}

_active_map: dict  = dict(DEFAULT_MAP)
_active_keys: set  = set()
_running:     bool = False
_lock              = threading.Lock()
_game_maps:   dict = {}


def load_maps() -> None:
    global _game_maps
    if MAPS_FILE.exists():
        try:
            _game_maps = json.loads(MAPS_FILE.read_text(encoding="utf-8"))
        except Exception:
            _game_maps = {}


def save_maps() -> None:
    MAPS_FILE.write_text(
        json.dumps(_game_maps, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def set_map_for_game(game_name: str, mapping: dict) -> None:
    _game_maps[game_name.lower()] = mapping
    save_maps()


def activate_map(game_name: str = "") -> str:
    global _active_map
    game_lower = game_name.lower()
    if game_lower and game_lower in _game_maps:
        _active_map = _game_maps[game_lower]
        return f"Mapa de controles ativado para {game_name}."
    _active_map = dict(DEFAULT_MAP)
    return "Mapa de controles padrao ativado."


def _press(key: str) -> None:
    if key and key not in _active_keys:
        pyautogui.keyDown(key)
        _active_keys.add(key)


def _release(key: str) -> None:
    if key and key in _active_keys:
        pyautogui.keyUp(key)
        _active_keys.discard(key)


def _release_all() -> None:
    for key in list(_active_keys):
        try:
            pyautogui.keyUp(key)
        except Exception:
            pass
    _active_keys.clear()


def _apply_state(state: dict) -> None:
    steering = state.get("steering", 0)
    throttle = state.get("throttle", 0)
    brake    = state.get("brake", 0)
    gear     = state.get("gear", 0)
    buttons  = state.get("buttons", {})

    # Volante
    if steering < -0.4:
        for k in _active_map.get("steering_right_mild", []):
            _release(k)
        for k in _active_map.get("steering_right_strong", []):
            _release(k)
        keys = "steering_left_strong" if steering < -0.7 else "steering_left_mild"
        for k in _active_map.get(keys, []):
            _press(k)
    elif steering > 0.4:
        for k in _active_map.get("steering_left_mild", []):
            _release(k)
        for k in _active_map.get("steering_left_strong", []):
            _release(k)
        keys = "steering_right_strong" if steering > 0.7 else "steering_right_mild"
        for k in _active_map.get(keys, []):
            _press(k)
    else:
        for k in (
            _active_map.get("steering_left_mild", []) +
            _active_map.get("steering_left_strong", []) +
            _active_map.get("steering_right_mild", []) +
            _active_map.get("steering_right_strong", [])
        ):
            _release(k)

    # Acelerador
    if throttle > 0.1:
        for k in _active_map.get("throttle", []):
            _press(k)
    else:
        for k in _active_map.get("throttle", []):
            _release(k)

    # Freio
    if brake > 0.1:
        for k in _active_map.get("brake", []):
            _press(k)
    else:
        for k in _active_map.get("brake", []):
            _release(k)

    # Marcha
    gear_map = {1: "gear_1", 2: "gear_2", 3: "gear_3",
                4: "gear_4", 5: "gear_5", 6: "gear_6", -1: "gear_r"}
    if gear in gear_map:
        for k in _active_map.get(gear_map[gear], []):
            _press(k)

    # Freio de mao (botao 23 do G29)
    if buttons.get(23):
        for k in _active_map.get("handbrake", []):
            _press(k)
    else:
        for k in _active_map.get("handbrake", []):
            _release(k)


def start(game_name: str = "") -> str:
    global _running
    if _running:
        return "Mapeamento ja ativo."
    load_maps()
    activate_map(game_name)
    start_g29()
    _running = True

    def _loop(state):
        if _running:
            _apply_state(state)

    on_input_change(_loop)
    return f"Controle G29 ativado! Mapa: {game_name or 'padrao'}"


def stop() -> str:
    global _running
    _running = False
    _release_all()
    return "Controle G29 desativado."


def create_custom_map(game_name: str, mappings: dict) -> str:
    set_map_for_game(game_name, mappings)
    return f"Mapa salvo para {game_name}. Usa 'ativa controle para {game_name}' pra ativar."


def list_games_with_maps() -> str:
    load_maps()
    if not _game_maps:
        return "Nenhum mapa de jogo salvo ainda."
    lines = ["Jogos com mapa configurado:"]
    for game in _game_maps:
        lines.append(f"  - {game}")
    return "\n".join(lines)


def is_active() -> bool:
    return _running
