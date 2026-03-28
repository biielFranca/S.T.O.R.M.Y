import os
import webbrowser

import config
from api_finder import find_hidden_api, find_public_api
from keyword_memory import add_custom_keyword
from search import brave_search
from sports import get_news, get_scoreboard, get_standings, get_team_schedule, get_top_scorers
from weather import get_weather
from spotify_controller import (
    authenticate as spotify_auth,
    play_track, pause, resume,
    next_track, previous_track,
    set_volume, now_playing,
    list_devices, transfer_to_device,
    add_to_queue, list_playlists,
    add_to_playlist, add_current_to_playlist,
    add_multiple_to_playlist, is_authenticated,
    recently_played,
)
from pc_control import (
    click, click_on, double_click, right_click,
    type_text, press_key, hotkey, scroll, move_mouse,
)
from screen_watcher import (
    get_current_context, find_element_on_screen,
    start as start_screen_watcher, get_screenshot_b64,
    set_focus_mode,
)
from input_mapper import (
    start as start_g29, stop as stop_g29,
    create_custom_map, list_games_with_maps,
    activate_map, is_active as g29_active,
)
from self_manager import (
    propose_api_key, propose_code_change,
    confirm_pending, cancel_pending,
    get_current_keys, has_pending,
)
from task_memory import add_custom_task, get_all_tasks
from whatsapp import (
    send_message as wa_send, send_to_group as wa_send_group,
    get_status as wa_status, get_recent_messages as wa_recent,
    get_contacts as wa_contacts, import_contacts_to_db as wa_import_contacts,
)

TOOL_DEFINITIONS = [
    {
        "name": "web_search",
        "description": (
            "Busca informações atualizadas na internet. "
            "USE para: notícias gerais, clima, preços, eventos. "
            "NÃO USE para dados esportivos — use sports_data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Consulta em português."}
            },
            "required": ["query"],
        },
    },
    {
        "name": "sports_data",
        "description": (
            "Busca dados esportivos via ESPN API. Sem chave, gratuito. "
            "SEMPRE use para: tabela, resultados, artilharia, notícias esportivas, próximos jogos. "
            "Ligas: brasileirao, serie b, libertadores, sul-americana, champions, premier league, la liga, bundesliga."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo": {
                    "type": "string",
                    "enum": ["tabela", "resultados", "artilharia", "noticias", "jogos_time"],
                    "description": (
                        "'tabela' = classificação | "
                        "'resultados' = placares | "
                        "'artilharia' = top goleadores | "
                        "'noticias' = últimas notícias | "
                        "'jogos_time' = próximos jogos de um time"
                    ),
                },
                "liga": {
                    "type": "string",
                    "description": "Nome da liga. Padrão: brasileirao.",
                },
                "time": {
                    "type": "string",
                    "description": "Nome do time. Obrigatório só para 'jogos_time'.",
                },
            },
            "required": ["tipo"],
        },
    },
    {
        "name": "find_api",
        "description": (
            "Busca APIs públicas e gratuitas. "
            "USE quando precisar de um dado que não tem — cotação, clima, música, etc. "
            "Pesquisa GitHub, Stack Overflow e Reddit."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "necessidade": {
                    "type": "string",
                    "description": "O que precisa buscar (ex: 'cotação do dólar', 'placar ao vivo')",
                }
            },
            "required": ["necessidade"],
        },
    },
    {
        "name": "find_hidden_api",
        "description": (
            "Descobre APIs não documentadas de um serviço específico. "
            "USE quando quiser integrar com um site sem API oficial — "
            "ex: 'o GE tem API?', 'como acessar dados do SofaScore?'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "servico": {
                    "type": "string",
                    "description": "Nome do serviço (ex: 'ESPN', 'SofaScore', 'Globo Esporte')",
                }
            },
            "required": ["servico"],
        },
    },
    {
        "name": "weather",
        "description": (
            "Busca clima atual e previsao do tempo via Open-Meteo. "
            "SEMPRE use para: clima, temperatura, previsao do tempo, vai chover, faz frio. "
            "Funciona para qualquer cidade ou bairro brasileiro. Sem necessidade de API key."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "Nome do bairro, cidade ou regiao (ex: Cachoeirinha SP, Sao Paulo, Limao ZN)",
                }
            },
            "required": ["location"],
        },
    },
    {
        "name": "spotify",
        "description": (
            "Controla o Spotify: tocar musica, pausar, continuar, proxima, anterior, volume, ver o que ta tocando. "
            "USE para qualquer comando de musica. "
            "Se nao autenticado, autentica primeiro automaticamente."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["play", "pause", "resume", "next", "previous", "queue", "volume", "now_playing", "devices", "transfer", "playlists", "add_to_playlist", "add_current_to_playlist", "add_multiple_to_playlist", "recently_played", "auth"],
                    "description": "Acao a executar",
                },
                "query": {"type": "string", "description": "Musica ou artista para tocar (so para action=play)"},
                "volume": {"type": "integer", "description": "Volume de 0 a 100 (so para action=volume)"},
                "device": {"type": "string", "description": "Nome do dispositivo para transferir (so para action=transfer)"},
                "playlist": {"type": "string", "description": "Nome da playlist"},
                "tracks": {"type": "array", "items": {"type": "string"}, "description": "Lista de musicas para adicionar (para add_multiple_to_playlist)"},
                "after_track": {"type": "string", "description": "Musica inicial do intervalo (para recently_played)"},
                "before_track": {"type": "string", "description": "Musica final do intervalo (para recently_played)"},
                "limit": {"type": "integer", "description": "Quantidade de musicas no historico (padrao 50)"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "pc_control",
        "description": (
            "Controla o mouse e teclado do PC. "
            "USE para: clicar em elementos, digitar texto, pressionar teclas, rolar pagina. "
            "Pode encontrar elementos na tela pela descricao e clicar neles."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["click", "click_on", "double_click", "right_click",
                              "type", "press_key", "hotkey", "scroll", "move"],
                    "description": "Acao a executar",
                },
                "x": {"type": "integer", "description": "Coordenada X"},
                "y": {"type": "integer", "description": "Coordenada Y"},
                "text": {"type": "string", "description": "Texto para digitar ou elemento para encontrar"},
                "key": {"type": "string", "description": "Tecla para pressionar (ex: enter, space, ctrl)"},
                "keys": {"type": "array", "items": {"type": "string"}, "description": "Teclas para atalho"},
                "amount": {"type": "integer", "description": "Quantidade de scroll (positivo=cima, negativo=baixo)"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "screen_context",
        "description": (
            "Retorna o contexto atual da tela — qual app esta aberto e o que esta acontecendo. "
            "USE quando precisar saber o que o usuario esta vendo antes de agir."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "focus_mode",
        "description": (
            "Ativa ou desativa o modo foco. "
            "Modo foco usa LLaVA (mais preciso, mais lento). "
            "Modo normal usa Moondream (rapido, uso geral). "
            "USE quando o usuario pedir para focar em algo especifico na tela."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "active": {"type": "boolean", "description": "true = foco (LLaVA), false = rapido (Moondream)"},
            },
            "required": ["active"],
        },
    },
    {
        "name": "g29_control",
        "description": (
            "Controla o mapeamento do volante G29 para jogos sem suporte nativo. "
            "USE para: ativar controle, criar mapa para jogo, listar jogos configurados."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["start", "stop", "create_map", "list_games", "activate"],
                },
                "game": {"type": "string", "description": "Nome do jogo"},
                "mapping": {"type": "object", "description": "Mapeamento de controles"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "save_api_key",
        "description": (
            "Salva uma chave de API no .env e ativa o servico. "
            "USE quando o usuario mandar uma chave de API pra integrar. "
            "Sempre pede confirmacao antes de salvar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key_name": {"type": "string", "description": "Nome da variavel (ex: OPENWEATHER_API_KEY)"},
                "key_value": {"type": "string", "description": "Valor da chave"},
                "description": {"type": "string", "description": "Descricao do servico"},
            },
            "required": ["key_name", "key_value"],
        },
    },
    {
        "name": "confirm_action",
        "description": (
            "Confirma ou cancela uma acao pendente. "
            "USE quando o usuario responder confirma ou cancela apos uma proposta."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["confirmar", "cancelar"],
                    "description": "confirmar = executa, cancelar = descarta",
                }
            },
            "required": ["action"],
        },
    },
    {
        "name": "list_api_keys",
        "description": "Lista as chaves de API configuradas no .env (valores mascarados).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "open_app",
        "description": (
            "Abre app ou site no computador. "
            "Apps padrão: spotify, youtube, whatsapp, brave, notepad, github, instagram, tiktok. "
            "NUNCA usar para resultados de busca."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "app_name": {"type": "string", "description": "Nome do app."}
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "open_url",
        "description": "Abre URL no navegador. Só usar quando o usuário pedir explicitamente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL completa com https://"}
            },
            "required": ["url"],
        },
    },
    {
        "name": "whatsapp",
        "description": (
            "Interage com o WhatsApp. "
            "USE para: enviar mensagem, ver status da conexão, ver mensagens recentes de um chat. "
            "O WhatsApp precisa estar conectado via whatsapp.js."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["send", "send_to_group", "status", "recent_messages", "get_contacts", "import_contacts"],
                    "description": "Ação a executar",
                },
                "phone": {
                    "type": "string",
                    "description": "Número do telefone com DDI (ex: 5511999999999). Só para action=send.",
                },
                "group_id": {
                    "type": "string",
                    "description": "ID do grupo no WhatsApp. Só para action=send_to_group.",
                },
                "message": {
                    "type": "string",
                    "description": "Texto da mensagem para enviar.",
                },
                "chat_id": {
                    "type": "string",
                    "description": "ID do chat para buscar mensagens. Só para action=recent_messages.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Quantidade de mensagens recentes (padrão 20). Só para action=recent_messages.",
                },
                "as_me": {
                    "type": "boolean",
                    "description": "Se true, envia sem prefixo [STORMY], como se fosse o próprio usuário. Usar apenas quando o usuário pedir explicitamente para se passar por ele.",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "learn_task",
        "description": "Salva nova tarefa para uso futuro.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nome da tarefa"},
                "value": {"type": "string", "description": "URL ou comando do sistema."},
                "task_type": {
                    "type": "string",
                    "enum": ["url", "system"],
                    "description": "'url' para sites, 'system' para programas.",
                },
            },
            "required": ["name", "value", "task_type"],
        },
    },
]


def _sports_data(tipo: str, liga: str = "brasileirao", time: str = "") -> str:
    match tipo:
        case "tabela":
            return get_standings(liga)
        case "resultados":
            return get_scoreboard(liga)
        case "artilharia":
            return get_top_scorers(liga)
        case "noticias":
            return get_news(liga)
        case "jogos_time":
            return get_team_schedule(time, liga)
        case _:
            return "Tipo inválido."


def _open_app(app_name: str) -> str:
    tasks = get_all_tasks()
    name = app_name.lower().strip()
    task = tasks.get(name)

    if not task:
        for key, val in tasks.items():
            if name in key or key in name:
                task = val
                break

    if not task:
        return f"Não conheço '{app_name}'. Me ensina: 'aprenda a abrir {app_name} = URL'."

    try:
        if task["type"] == "url":
            webbrowser.open(task["value"])
        elif task["type"] == "system":
            os.system(task["value"])
        return task.get("success_message", f"Abrindo {app_name}.")
    except Exception as e:
        return f"Erro ao abrir {app_name}: {e}"


def _open_url(url: str) -> str:
    try:
        webbrowser.open(url)
        return f"Abrindo {url}."
    except Exception as e:
        return f"Erro: {e}"


def _learn_task(name: str, value: str, task_type: str) -> str:
    action_name = name.lower().strip().replace(" ", "_")
    success = add_custom_task(
        action_name=action_name,
        task_type=task_type,
        value=value,
        success_message=f"Abrindo {name}.",
    )
    if not success:
        return "Não consegui salvar."
    add_custom_keyword(name.lower(), action_name)
    return f"Aprendi a abrir '{name}'. É só pedir!"


def execute_tool(name: str, inputs: dict) -> str:
    match name:
        case "spotify":
            action = inputs.get("action", "")
            if not is_authenticated() and action != "auth":
                auth_result = spotify_auth()
                if "sucesso" not in auth_result.lower():
                    return auth_result
            if action == "play":
                return play_track(inputs.get("query", ""))
            elif action == "pause":
                return pause()
            elif action == "resume":
                return resume()
            elif action == "next":
                return next_track()
            elif action == "previous":
                return previous_track()
            elif action == "volume":
                return set_volume(inputs.get("volume", 50))
            elif action == "now_playing":
                return now_playing()
            elif action == "devices":
                return list_devices()
            elif action == "queue":
                return add_to_queue(inputs.get("query", ""))
            elif action == "transfer":
                return transfer_to_device(inputs.get("device", ""))
            elif action == "playlists":
                return list_playlists()
            elif action == "add_to_playlist":
                return add_to_playlist(inputs.get("query", ""), inputs.get("playlist", ""))
            elif action == "add_multiple_to_playlist":
                return add_multiple_to_playlist(inputs.get("tracks", []), inputs.get("playlist", ""))
            elif action == "add_current_to_playlist":
                return add_current_to_playlist(inputs.get("playlist", ""))
            elif action == "recently_played":
                return recently_played(
                    limit=inputs.get("limit", 50),
                    after_track=inputs.get("after_track", ""),
                    before_track=inputs.get("before_track", ""),
                )
            elif action == "auth":
                return spotify_auth()
            return "Acao desconhecida."
        case "pc_control":
            action = inputs.get("action", "")
            x, y = inputs.get("x", 0), inputs.get("y", 0)
            if action == "click":
                return click(x, y)
            elif action == "click_on":
                return click_on(inputs.get("text", ""))
            elif action == "double_click":
                return double_click(x, y)
            elif action == "right_click":
                return right_click(x, y)
            elif action == "type":
                return type_text(inputs.get("text", ""))
            elif action == "press_key":
                return press_key(inputs.get("key", ""))
            elif action == "hotkey":
                return hotkey(*inputs.get("keys", []))
            elif action == "scroll":
                return scroll(x, y, inputs.get("amount", 3))
            elif action == "move":
                return move_mouse(x, y)
            return "Acao desconhecida."
        case "screen_context":
            ctx = get_current_context()
            return f"App: {ctx.get('current_app', '?')}, Contexto: {ctx.get('last_description', '?')}"
        case "focus_mode":
            return set_focus_mode(inputs.get("active", False))
        case "g29_control":
            action = inputs.get("action", "")
            if action == "start":
                return start_g29(inputs.get("game", ""))
            elif action == "stop":
                return stop_g29()
            elif action == "create_map":
                return create_custom_map(inputs.get("game", ""), inputs.get("mapping", {}))
            elif action == "list_games":
                return list_games_with_maps()
            elif action == "activate":
                return activate_map(inputs.get("game", ""))
            return "Acao desconhecida."
        case "save_api_key":
            return propose_api_key(
                inputs.get("key_name", ""),
                inputs.get("key_value", ""),
                inputs.get("description", ""),
            )
        case "confirm_action":
            if inputs.get("action") == "confirmar":
                return confirm_pending()
            return cancel_pending()
        case "list_api_keys":
            return get_current_keys()
        case "weather":
            return get_weather(inputs.get("location", ""))
        case "web_search":
            return brave_search(inputs.get("query", ""))
        case "sports_data":
            return _sports_data(
                inputs.get("tipo", "tabela"),
                inputs.get("liga", "brasileirao"),
                inputs.get("time", ""),
            )
        case "find_api":
            return find_public_api(inputs.get("necessidade", ""))
        case "find_hidden_api":
            return find_hidden_api(inputs.get("servico", ""))
        case "whatsapp":
            action = inputs.get("action", "")
            if action == "send":
                msg = inputs.get("message", "")
                if not inputs.get("as_me"):
                    msg = f"[STORMY]: {msg}"
                return wa_send(inputs.get("phone", ""), msg)
            elif action == "send_to_group":
                return wa_send_group(inputs.get("group_id", ""), inputs.get("message", ""))
            elif action == "status":
                return wa_status()
            elif action == "recent_messages":
                msgs = wa_recent(inputs.get("chat_id", ""), inputs.get("limit", 20))
                if msgs and "error" in msgs[0]:
                    return f"Erro: {msgs[0]['error']}"
                lines = [f"{m['sender_name']}: {m['content']}" for m in msgs]
                return "\n".join(lines) if lines else "Nenhuma mensagem encontrada."
            elif action == "get_contacts":
                contacts = wa_contacts()
                if contacts and "error" in contacts[0]:
                    return f"Erro: {contacts[0]['error']}"
                lines = [f"{c.get('name', '?')} — {c.get('number', '?')}" for c in contacts]
                return "\n".join(lines) if lines else "Nenhum contato encontrado."
            elif action == "import_contacts":
                return wa_import_contacts()
            return "Ação desconhecida."
        case "open_app":
            return _open_app(inputs.get("app_name", ""))
        case "open_url":
            return _open_url(inputs.get("url", ""))
        case "learn_task":
            return _learn_task(
                inputs.get("name", ""),
                inputs.get("value", ""),
                inputs.get("task_type", "url"),
            )
        case _:
            return f"Ferramenta desconhecida: {name}"
