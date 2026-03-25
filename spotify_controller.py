"""
Spotify Controller — OAuth2 + Web API
Controla reproducao, fila, dispositivos e transferencia.
"""

import os
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID     = os.getenv("SPOTIFY_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
REDIRECT_URI  = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
SCOPE         = (
    "streaming user-read-email user-read-private "
    "user-read-playback-state user-modify-playback-state "
    "playlist-read-private playlist-read-collaborative "
    "playlist-modify-public playlist-modify-private"
)

_token_data: dict = {}
_auth_code: str = ""
_TOKEN_FILE = Path(__file__).parent / ".spotify_token.json"


def _save_token(data: dict) -> None:
    import json
    _TOKEN_FILE.write_text(json.dumps(data), encoding="utf-8")


def _load_token() -> None:
    global _token_data
    import json
    if _TOKEN_FILE.exists():
        try:
            _token_data = json.loads(_TOKEN_FILE.read_text(encoding="utf-8"))
        except Exception:
            _token_data = {}


# Carrega token salvo ao importar
_load_token()


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _auth_code
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if "code" in params:
            _auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html><body style='font-family:Arial;text-align:center;padding:50px'><h2>Spotify autorizado!</h2><p>Pode fechar essa aba.</p></body></html>")
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, *args):
        pass


def _get_auth_url() -> str:
    params = urlencode({
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
    })
    return f"https://accounts.spotify.com/authorize?{params}"


def _exchange_code(code: str) -> dict:
    resp = requests.post(
        "https://accounts.spotify.com/api/token",
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI},
        auth=(CLIENT_ID, CLIENT_SECRET),
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def _refresh_token() -> bool:
    global _token_data
    refresh = _token_data.get("refresh_token")
    if not refresh:
        return False
    try:
        resp = requests.post(
            "https://accounts.spotify.com/api/token",
            data={"grant_type": "refresh_token", "refresh_token": refresh},
            auth=(CLIENT_ID, CLIENT_SECRET),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        _token_data["access_token"] = data["access_token"]
        if "refresh_token" in data:
            _token_data["refresh_token"] = data["refresh_token"]
        _save_token(_token_data)
        return True
    except Exception:
        return False


def authenticate() -> str:
    global _auth_code, _token_data
    if not CLIENT_ID or not CLIENT_SECRET:
        return "Credenciais do Spotify nao configuradas no .env."
    if _token_data.get("access_token"):
        return "Spotify ja autenticado."
    _auth_code = ""
    server = HTTPServer(("127.0.0.1", 8888), _CallbackHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    webbrowser.open(_get_auth_url())
    for _ in range(60):
        if _auth_code:
            break
        time.sleep(1)
    if not _auth_code:
        return "Tempo esgotado. Tenta autorizar de novo."
    try:
        _token_data = _exchange_code(_auth_code)
        _save_token(_token_data)
        return "Spotify autorizado com sucesso!"
    except Exception as e:
        return f"Erro na autenticacao: {e}"


def _get_token() -> str | None:
    token = _token_data.get("access_token")
    if not token:
        _load_token()
        token = _token_data.get("access_token")
    return token


def _headers() -> dict:
    token = _get_token()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _req(method: str, endpoint: str, **kwargs):
    h = _headers()
    if not h:
        return None
    url = f"https://api.spotify.com/v1{endpoint}"
    resp = getattr(requests, method)(url, headers=h, timeout=10, **kwargs)
    if resp.status_code == 401 and _refresh_token():
        h = _headers()
        resp = getattr(requests, method)(url, headers=h, timeout=10, **kwargs)
    return resp


def search_track(query: str) -> dict | None:
    resp = _req("get", "/search", params={"q": query, "type": "track", "limit": 1})
    if not resp or resp.status_code != 200:
        return None
    items = resp.json().get("tracks", {}).get("items", [])
    if not items:
        return None
    t = items[0]
    return {"uri": t["uri"], "name": t["name"], "artist": t["artists"][0]["name"]}


def get_devices() -> list[dict]:
    resp = _req("get", "/me/player/devices")
    if not resp or resp.status_code != 200:
        return []
    return resp.json().get("devices", [])


def _ensure_spotify_open() -> bool:
    """Verifica se tem dispositivo ativo. Se não tiver, abre o Spotify e aguarda."""
    devices = get_devices()
    if devices:
        return True
    # Abre o Spotify
    if os.name == "nt":
        os.system("start spotify")
    else:
        os.system("spotify &")
    # Aguarda até 15s aparecer um dispositivo
    for _ in range(15):
        time.sleep(1)
        devices = get_devices()
        if devices:
            return True
    return False


def get_pc_device_id() -> str | None:
    devices = get_devices()
    for d in devices:
        if d.get("type", "").lower() in ("computer", "desktop"):
            return d["id"]
    for d in devices:
        if not d.get("is_restricted"):
            return d["id"]
    return None


def play_track(query: str, device_id: str = None) -> str:
    if not _get_token():
        return "Spotify nao autenticado. Fala autentica spotify primeiro."
    if not _ensure_spotify_open():
        return "Nao consegui abrir o Spotify. Abre manualmente e tenta de novo."
    track = search_track(query)
    if not track:
        return f"Nao achei '{query}' no Spotify."
    if not device_id:
        device_id = get_pc_device_id()
    endpoint = "/me/player/play"
    if device_id:
        endpoint += f"?device_id={device_id}"
    body = {"uris": [track["uri"]]}
    resp = _req("put", endpoint, json=body)
    if not resp:
        return "Spotify nao autenticado."
    if resp.status_code in (200, 204):
        return f"Tocando: {track['name']} - {track['artist']}"
    return f"Erro ao tocar ({resp.status_code}): {track['name']} - {track['artist']}"


def pause() -> str:
    resp = _req("put", "/me/player/pause")
    if not resp:
        return "Spotify nao autenticado."
    return "Pausado." if resp.status_code in (200, 204) else "Nada tocando."


def resume() -> str:
    resp = _req("put", "/me/player/play")
    if not resp:
        return "Spotify nao autenticado."
    return "Continuando." if resp.status_code in (200, 204) else "Erro."


def next_track() -> str:
    resp = _req("post", "/me/player/next")
    if not resp:
        return "Spotify nao autenticado."
    return "Proxima faixa." if resp.status_code in (200, 204) else "Erro ao pular."


def previous_track() -> str:
    resp = _req("post", "/me/player/previous")
    if not resp:
        return "Spotify nao autenticado."
    return "Faixa anterior." if resp.status_code in (200, 204) else "Erro."


def add_to_queue(query: str) -> str:
    track = search_track(query)
    if not track:
        return f"Nao achei '{query}' no Spotify."
    resp = _req("post", "/me/player/queue", params={"uri": track["uri"]})
    if not resp:
        return "Spotify nao autenticado."
    if resp.status_code in (200, 204):
        return f"Adicionei na fila: {track['name']} - {track['artist']}"
    return f"Erro ao adicionar na fila ({resp.status_code})."


def set_volume(percent: int) -> str:
    percent = max(0, min(100, percent))
    resp = _req("put", "/me/player/volume", params={"volume_percent": percent})
    if not resp:
        return "Spotify nao autenticado."
    return f"Volume em {percent}%." if resp.status_code in (200, 204) else "Erro."


def now_playing() -> str:
    resp = _req("get", "/me/player/currently-playing")
    if not resp or resp.status_code == 204 or not resp.text:
        return "Nada tocando agora."
    data = resp.json()
    if not data or not data.get("item"):
        return "Nada tocando agora."
    item = data["item"]
    status = "tocando" if data.get("is_playing") else "pausado"
    return f"{item['name']} - {item['artists'][0]['name']} ({status})"


def list_devices() -> str:
    devices = get_devices()
    if not devices:
        return "Nenhum dispositivo Spotify ativo. Abre o Spotify em algum dispositivo primeiro."
    lines = ["Dispositivos disponíveis:"]
    for d in devices:
        active = " <- ativo" if d.get("is_active") else ""
        lines.append(f"  - {d['name']} ({d['type']}){active}")
    return "\n".join(lines)


def transfer_to_device(device_name: str) -> str:
    devices = get_devices()
    if not devices:
        return "Nenhum dispositivo encontrado. Abre o Spotify no dispositivo primeiro."
    name_lower = device_name.lower()
    match = None
    for d in devices:
        if name_lower in d["name"].lower():
            match = d
            break
    if not match:
        lines = [f"Nao achei '{device_name}'. Dispositivos disponíveis:"]
        for d in devices:
            lines.append(f"  - {d['name']}")
        return "\n".join(lines)
    resp = _req("put", "/me/player", json={"device_ids": [match["id"]], "play": True})
    if not resp:
        return "Spotify nao autenticado."
    if resp.status_code in (200, 204):
        return f"Transferido para {match['name']}!"
    return f"Erro ao transferir ({resp.status_code})."


def is_authenticated() -> bool:
    # Recarrega do disco caso o token tenha sido salvo por outro processo
    if not _token_data.get("access_token"):
        _load_token()
    return bool(_token_data.get("access_token"))


def recently_played(limit: int = 10, after_track: str = None, before_track: str = None) -> str:
    """Retorna músicas tocadas recentemente."""
    params = {"limit": min(limit, 50)}
    resp = _req("get", "/me/player/recently-played", params=params)
    if not resp or resp.status_code != 200:
        return "Nao consegui buscar o historico agora."
    items = resp.json().get("items", [])
    if not items:
        return "Nenhuma musica no historico."
    lines = ["Tocadas recentemente:"]
    for item in items:
        track = item.get("track", {})
        name = track.get("name", "?")
        artist = track.get("artists", [{}])[0].get("name", "?")
        lines.append(f"  - {name} - {artist}")
    return "\n".join(lines)


def get_playlists() -> list[dict]:
    """Lista playlists do usuario."""
    resp = _req("get", "/me/playlists", params={"limit": 50})
    if not resp or resp.status_code != 200:
        return []
    return resp.json().get("items", [])


def list_playlists() -> str:
    playlists = get_playlists()
    if not playlists:
        return "Nenhuma playlist encontrada."
    lines = ["Suas playlists:"]
    for i, p in enumerate(playlists, 1):
        total = p.get("tracks", {}).get("total", "?") if p.get("tracks") else "?"
        lines.append(f"  {i}. {p['name']} ({total} musicas)")
    return "\n".join(lines)


def add_to_playlist(track_query: str, playlist_name: str) -> str:
    """Adiciona uma musica em uma playlist pelo nome."""
    track = search_track(track_query)
    if not track:
        return f"Nao achei '{track_query}' no Spotify."

    playlists = get_playlists()
    if not playlists:
        return "Nenhuma playlist encontrada."

    name_lower = playlist_name.lower()
    match = None
    for p in playlists:
        if name_lower in p["name"].lower():
            match = p
            break

    if not match:
        lines = [f"Nao achei '{playlist_name}'. Suas playlists:"]
        for p in playlists[:10]:
            lines.append(f"  - {p['name']}")
        return "\n".join(lines)

    resp = _req("post", f"/playlists/{match['id']}/tracks", json={"uris": [track["uri"]]})
    if not resp:
        return "Spotify nao autenticado."
    if resp.status_code in (200, 201):
        return f"Adicionei {track['name']} - {track['artist']} na playlist {match['name']}!"
    return f"Erro ao adicionar ({resp.status_code})."


def add_current_to_playlist(playlist_name: str) -> str:
    """Adiciona a musica atual em uma playlist."""
    resp = _req("get", "/me/player/currently-playing")
    if not resp or resp.status_code == 204 or not resp.text:
        return "Nada tocando agora."
    data = resp.json()
    if not data or not data.get("item"):
        return "Nada tocando agora."
    item = data["item"]
    uri = item["uri"]
    name = item["name"]
    artist = item["artists"][0]["name"]

    playlists = get_playlists()
    name_lower = playlist_name.lower()
    match = None
    for p in playlists:
        if name_lower in p["name"].lower():
            match = p
            break

    if not match:
        lines = [f"Nao achei '{playlist_name}'. Suas playlists:"]
        for p in playlists[:10]:
            lines.append(f"  - {p['name']}")
        return "\n".join(lines)

    resp2 = _req("post", f"/playlists/{match['id']}/tracks", json={"uris": [uri]})
    if not resp2:
        return "Spotify nao autenticado."
    if resp2.status_code in (200, 201):
        return f"Adicionei {name} - {artist} na playlist {match['name']}!"
    return f"Erro ({resp2.status_code})."


def add_multiple_to_playlist(tracks: list[str], playlist_name: str) -> str:
    """Adiciona multiplas musicas em uma playlist de uma vez."""
    playlists = get_playlists()
    if not playlists:
        return "Nenhuma playlist encontrada."

    name_lower = playlist_name.lower()
    match = None
    for p in playlists:
        if name_lower in p["name"].lower():
            match = p
            break

    if not match:
        lines = [f"Nao achei '{playlist_name}'. Suas playlists:"]
        for p in playlists[:10]:
            lines.append(f"  - {p['name']}")
        return "\n".join(lines)

    uris = []
    not_found = []
    for query in tracks:
        track = search_track(query)
        if track:
            uris.append(track["uri"])
        else:
            not_found.append(query)

    if not uris:
        return "Nao achei nenhuma das musicas no Spotify."

    # Spotify aceita ate 100 uris por requisicao
    added = 0
    for i in range(0, len(uris), 100):
        batch = uris[i:i+100]
        resp = _req("post", f"/playlists/{match['id']}/tracks", json={"uris": batch})
        if resp and resp.status_code in (200, 201):
            added += len(batch)

    result = f"Adicionei {added} musica(s) na playlist {match['name']}!"
    if not_found:
        result += f"\nNao encontrei: {', '.join(not_found)}"
    return result