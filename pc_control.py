"""
PC Control — controla mouse e teclado programaticamente.
Usa pyautogui para cliques, digitação e rolagem.
"""

import time
import pyautogui
from screen_watcher import find_element_on_screen, get_best_screenshot, get_recent_screenshots

# Segurança — movimento suave e failsafe ativo
pyautogui.PAUSE    = 0.05
pyautogui.FAILSAFE = True  # mover mouse pro canto superior esquerdo para


def click(x: int, y: int, button: str = "left", clicks: int = 1) -> str:
    try:
        pyautogui.click(x, y, button=button, clicks=clicks, interval=0.1)
        return f"Cliquei em ({x}, {y})."
    except Exception as e:
        return f"Erro ao clicar: {e}"


# Elementos comuns do Windows com coordenadas aproximadas
KNOWN_ELEMENTS = {
    'botao windows': (15, -1),    # -1 = calcular pela altura da tela
    'botao iniciar': (15, -1),
    'iniciar': (15, -1),
    'windows': (15, -1),
    'barra de tarefas': (500, -1),
    'area de trabalho': (500, 500),
    'fechar janela': (-50, 10),   # -50 = calcular pela largura
    'minimizar': (-150, 10),
    'maximizar': (-100, 10),
}


def _resolve_coords(x: int, y: int):
    import pyautogui
    sw, sh = pyautogui.size()
    rx = sw + x if x < 0 else x
    ry = sh + y if y < 0 else y
    return rx, ry


def click_on(description: str) -> str:
    """Encontra um elemento na tela pela descricao e clica nele."""
    # Verifica elementos conhecidos primeiro (instantaneo)
    desc_lower = description.lower().strip()
    for key, (kx, ky) in KNOWN_ELEMENTS.items():
        if key in desc_lower or desc_lower in key:
            x, y = _resolve_coords(kx, ky)
            return click(x, y)

    # Fallback: visao computacional
    coords = find_element_on_screen(description)
    if not coords:
        return f"Nao encontrei '{description}' na tela."
    x, y = coords
    return click(x, y)


def double_click(x: int, y: int) -> str:
    try:
        pyautogui.doubleClick(x, y)
        return f"Clique duplo em ({x}, {y})."
    except Exception as e:
        return f"Erro: {e}"


def right_click(x: int, y: int) -> str:
    try:
        pyautogui.rightClick(x, y)
        return f"Clique direito em ({x}, {y})."
    except Exception as e:
        return f"Erro: {e}"


def type_text(text: str, interval: float = 0.05) -> str:
    try:
        pyautogui.typewrite(text, interval=interval)
        return f"Digitei: {text}"
    except Exception as e:
        return f"Erro ao digitar: {e}"


def press_key(key: str) -> str:
    try:
        pyautogui.press(key)
        return f"Tecla pressionada: {key}"
    except Exception as e:
        return f"Erro: {e}"


def hotkey(*keys: str) -> str:
    try:
        pyautogui.hotkey(*keys)
        return f"Atalho: {'+'.join(keys)}"
    except Exception as e:
        return f"Erro: {e}"


def scroll(x: int, y: int, amount: int) -> str:
    try:
        pyautogui.scroll(amount, x=x, y=y)
        direction = "cima" if amount > 0 else "baixo"
        return f"Rolei pra {direction}."
    except Exception as e:
        return f"Erro: {e}"


def move_mouse(x: int, y: int, duration: float = 0.3) -> str:
    try:
        pyautogui.moveTo(x, y, duration=duration)
        return f"Mouse movido para ({x}, {y})."
    except Exception as e:
        return f"Erro: {e}"


def drag(x1: int, y1: int, x2: int, y2: int, duration: float = 0.5) -> str:
    try:
        pyautogui.drag(x2 - x1, y2 - y1, duration=duration, button="left")
        return f"Arrastei de ({x1},{y1}) para ({x2},{y2})."
    except Exception as e:
        return f"Erro: {e}"


def get_mouse_position() -> tuple[int, int]:
    return pyautogui.position()


def screenshot_region(x: int, y: int, w: int, h: int) -> str:
    """Tira print de uma regiao especifica da tela."""
    import base64
    from io import BytesIO
    img = pyautogui.screenshot(region=(x, y, w, h))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()
