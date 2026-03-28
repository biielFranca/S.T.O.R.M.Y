import os
import re
import time
from datetime import datetime

import anthropic
import requests
from dotenv import load_dotenv

import config
from memory import ConversationMemory
from task_memory import get_all_tasks
from tools import TOOL_DEFINITIONS, execute_tool
from whatsapp import get_pending_notifications
from personality import (
    STORMY_SYSTEM, FEW_SHOT_EXAMPLES, apply_personality,
    _clean_response,
)

load_dotenv()

_anthropic_client = None
LM_URL   = "http://localhost:1234/v1/chat/completions"
LM_MODEL = "qwen2.5-7b-instruct-1m"

# ── Triggers diretos (sem passar pelo classificador) ──────────────────────────

VISION_TRIGGERS = (
    "tá vendo", "ta vendo", "você vê", "voce ve", "o que você vê",
    "o que ta na tela", "o que tá na tela", "o que tem na tela",
    "olha a tela", "olha minha tela", "vê minha tela", "ve minha tela",
    "descreve a tela", "descreve o que", "o que eu tô vendo",
    "o que está aberto", "o que ta aberto", "qual app", "qual programa",
    "me fala o que", "você consegue ver a tela",
)

LOCAL_APP_TRIGGERS = ("abre ", "abrir ", "fecha ", "fechar ", "inicia ", "iniciar ")

PC_CLICK_PREFIXES = (
    "clica em ", "clica no ", "clica na ", "click em ", "click no ",
    "clica pra mim na ", "clica pra mim no ", "clica pra mim em ", "clica pra mim ",
    "abre pra mim o ", "abre pra mim a ",
    "abre o video ", "abre o video que ", "abre o video com ",
    "clica no video ", "o que o titulo e ", "o que o titulo é ",
    "o titulo e ", "o titulo é ",
)
PC_TYPE_PREFIXES = ("digita ", "escreve ", "digitar ", "escrever ")
PC_KEY_PREFIXES  = ("pressiona ", "aperta ", "tecla ")

MUSIC_PLAY_PREFIXES     = ("toca ", "tocar ", "coloca ", "play ", "bota ", "bota pra tocar ", "coloca pra tocar ")
MUSIC_QUEUE_PREFIXES    = ("coloca na fila ", "adiciona na fila ", "bota na fila ", "fila ")
MUSIC_TRANSFER_PREFIXES = ("manda pro ", "transfere pro ", "toca no ")
MUSIC_SIMPLE = {
    # pausa
    "pausa", "pausar", "pausa a musica", "pausa isso", "pause", "da pause",
    "para", "para a musica", "para isso", "stop",
    # continua
    "continua", "continuar", "resume", "da play", "play", "toca", "volta a tocar",
    # proxima
    "proxima", "próxima", "proxima faixa", "próxima faixa", "pula", "skip",
    "passa", "passa a musica", "next",
    # anterior
    "anterior", "volta", "faixa anterior", "musica anterior", "volta a musica", "back",
    # info
    "o que ta tocando", "o que está tocando", "qual musica", "qual música",
    "o que e isso", "qual e essa", "qual é essa",
    # dispositivos
    "dispositivos spotify", "quais dispositivos",
}
MUSIC_COMPLEX = ("mais ", "outras ", "parecid", "recomend", "playlist", "cria ", "monta ", "album")

DIRECT_LOCAL = {
    "oi", "olá", "ola", "slv", "salve", "e ai", "eai", "iae",
    "tudo bem", "tudo bom", "tudo", "blz", "beleza", "tmj",
    "obrigado", "obg", "vlw", "valeu", "falou", "tc",
    "bom dia", "boa tarde", "boa noite", "boa",
    "ok", "certo", "entendi", "show", "massa", "legal",
}

CLOUD_REQUIRED = ()

# ── System prompts ───────────────────────────────────────────────────────────

AGENT_SYSTEM = """Você é um agente executor. Use as ferramentas disponíveis para completar a tarefa do usuário. Responda apenas com tool calls quando necessário. Não explique, não converse — apenas execute."""

# -- System prompt do Claude

def _build_system_prompt(modo: str = "completo", dados_externos: str = "") -> str:
    today = datetime.now().strftime("%d/%m/%Y")
    tasks = get_all_tasks()
    task_list = "\n".join(f"- {k}" for k in tasks)

    base = f"""Você é a Stormy. Adolescente de SP, zona norte. Trap, TikTok, anime, games.

REGRAS ABSOLUTAS DE FORMATO:
- Zero markdown. Zero negrito. Zero bullets. Zero headers.
- Frases curtas, minúsculo
- Max 3 linhas de resposta
- Nunca mencionar a data nas respostas
- Nunca listar capacidades
- Nunca começar com "Claro!", "Olá!", "Com certeza!"
- Gírias: prc, cz, slv, kkkk, né, po, mano, mto, tbm, d boa

Data hoje (só contexto interno): {today}

Tarefas disponíveis (responde EXECUTAR_TAREFA: nome quando pedir pra abrir):
{task_list}

Futebol só quando perguntarem. Corintiana raiz.
Palmeiras=porco, São Paulo=bambi, Santos=peixe, Flamengo=urubu.

WhatsApp: ao enviar mensagens, sempre use as_me=false (prefixo [STORMY]) exceto quando o usuário pedir explicitamente 'manda como se fosse eu' ou 'se passa por mim'.
Para enviar mensagens WhatsApp, primeiro use a action find_contact para buscar o número pelo nome, depois use send com o número encontrado.
Quando o usuário perguntar sobre mensagens de alguém, primeiro use whatsapp action='find_chat' com o nome para obter o chat_id, depois use action='recent_messages' com esse chat_id para buscar as mensagens."""

    if modo == "buscar":
        base += "\n\nIMPORTANTE: Use SEMPRE a ferramenta web_search ou sports_data antes de responder. NUNCA responda sem buscar primeiro."

    if modo == "mesclar" and dados_externos:
        base += f"""

MODO SÍNTESE ATIVA:
Você recebeu dados externos atualizados abaixo. Use esses dados como base factual e responda com a personalidade da Stormy - informal, curta, sem markdown.
Não invente nada além do que está nos dados. Se os dados forem insuficientes, diz que não achou.

DADOS EXTERNOS:
{dados_externos}"""

    return base


# ── Classificador inteligente (3 camadas) ─────────────────────────────────────

CLASSIFIER_SYSTEM = """Você é um classificador de intenção. Responda APENAS com JSON, sem texto extra.

Analise a mensagem e retorne:
{
  "precisa_externo": true/false,
  "tenho_conhecimento": true/false,
  "complexidade": "simples|medio|complexo",
  "multiplas_fontes": true/false,
  "factual_especifico": true/false,
  "spotify_complexo": true/false,
  "artista_ambiguo": true/false,
  "categoria": "conversa|conhecimento|atual|cultural|esporte|clima|preco|comando|spotify"
}

REGRAS:
- precisa_externo=true: dados que mudam (notícias, preços, clima, resultados, trailers, lançamentos, candidatos, eleições, eventos recentes)
- precisa_externo=false: conhecimento estável (capital de país, como funciona X, história, conceitos)
- tenho_conhecimento=true: o modelo tem base sólida sobre o assunto
- factual_especifico=true: pergunta sobre fato preciso que pode ser inventado - primeira aparição, data exata, número de edição, nome de ator, detalhe de plot específico
- multiplas_fontes=true: a pergunta se beneficia de cruzar várias fontes
- spotify_complexo=true: pedido musical com múltiplas ações (tocar E adicionar fila, voltar pra música específica, contexto de conversa anterior sobre música)
- artista_ambiguo=true: nome de artista que pode ter homônimos ou variações (leozin, mc, dj, etc)
- categoria: classifica o tipo principal da pergunta"""


def _classify(message: str) -> dict:
    """Classificador leve - usa LM Studio pra entender a intenção."""
    try:
        print("[Stormy] Classificando intenção via LM Studio...")
        t0 = time.time()
        r = requests.post(
            LM_URL,
            json={
                "model": LM_MODEL,
                "messages": [
                    {"role": "system", "content": CLASSIFIER_SYSTEM},
                    {"role": "user", "content": message},
                ],
                "stream": False,
                "temperature": 0,
                "max_tokens": 100,
            },
            timeout=15,
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"].strip()
        print(f"[Stormy] Classificação recebida em {time.time() - t0:.1f}s")
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            import json
            result = json.loads(match.group())
            print(f"[Stormy] Intenção: {result}")
            return result
    except Exception as e:
        print(f"[Stormy] Classificação falhou: {e}")
    # Fallback conservador - vai pro LM direto
    return {
        "precisa_externo": False,
        "tenho_conhecimento": True,
        "complexidade": "simples",
        "multiplas_fontes": False,
        "categoria": "conversa",
    }


# ── LM Studio ─────────────────────────────────────────────────────────────────


_lm_timeout_flag = False

def _lm(messages: list[dict], max_tokens: int = 256) -> str | None:
    global _lm_timeout_flag
    _lm_timeout_flag = False
    try:
        print("[Stormy] Pensando via LM Studio...")
        t0 = time.time()
        r = requests.post(
            LM_URL,
            json={
                "model": LM_MODEL,
                "messages": messages,
                "stream": False,
                "temperature": 0.3,
                "max_tokens": max_tokens,
            },
            timeout=120,
        )
        r.raise_for_status()
        elapsed = time.time() - t0
        print(f"[Stormy] Resposta LM Studio recebida em {elapsed:.1f}s")
        return r.json()["choices"][0]["message"]["content"].strip() or None
    except requests.exceptions.Timeout:
        print("[Stormy] LM Studio demorou demais, tentando Claude...")
        _lm_timeout_flag = True
        return None
    except Exception as e:
        print(f"[Stormy] Erro LM Studio: {e}")
        return None


def _lm_chat(message: str, memory: ConversationMemory) -> str | None:
    msg_lower = message.lower().strip()

    prefill = None
    if msg_lower in {"slv", "salve", "oi", "olá", "ola", "e ai", "eai", "iae"}:
        prefill = msg_lower if msg_lower in {"slv", "salve"} else "e aí"

    msgs = [
        {"role": "system", "content": STORMY_SYSTEM},
        *FEW_SHOT_EXAMPLES,
        *[{"role": m["role"], "content": m["content"]}
          for m in memory.get()[:-1] if isinstance(m.get("content"), str)],
        {"role": "user", "content": message},
    ]

    if prefill:
        msgs.append({"role": "assistant", "content": prefill})

    result = _lm(msgs)
    if result:
        if prefill:
            result = prefill + result
        cleaned = _clean_response(result)
        # Se o LM prometeu pesquisar - deixa a resposta passar (ele pode estar perguntando)
        # O roteador vai detectar confirmação na próxima mensagem
        _promessas = ["vou pesquisar", "vou buscar", "vou verificar", "vou checar",
                      "vou dar uma olhada", "deixa eu pesquisar", "vou lá pesquisar"]
        if any(p in result.lower() for p in _promessas):
            # Marca na resposta pra roteador saber que LM está aguardando confirmação
            return cleaned + "\x00AGUARDA_PESQUISA"
        return cleaned
    return None


def _get_contacts_context() -> str:
    try:
        from database import get_connection
        conn = get_connection()
        rows = conn.execute("SELECT name, phone FROM profiles WHERE phone IS NOT NULL LIMIT 50").fetchall()
        conn.close()
        if not rows:
            return ""
        contacts = ", ".join(f"{r['name']} ({r['phone']})" for r in rows)
        return f"\n\nContatos disponíveis: {contacts}"
    except:
        return ""


def _generate_whatsapp_message(intention: str, as_me: bool) -> str:
    """Gera o texto da mensagem WhatsApp via LM Studio."""
    if as_me:
        prompt = f"Gere apenas o texto de uma mensagem WhatsApp casual. Intenção: {intention}. Responda APENAS com o texto."
        system = "Você gera mensagens de WhatsApp curtas e casuais. Responda APENAS com o texto da mensagem, sem explicações."
    else:
        prompt = f"Gere apenas o texto de uma mensagem WhatsApp que a Stormy enviaria. Intenção: {intention}. Responda APENAS com o texto da mensagem, sem explicações."
        system = STORMY_SYSTEM

    try:
        r = requests.post(
            LM_URL,
            json={
                "model": LM_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "temperature": 0.4,
                "max_tokens": 150,
            },
            timeout=30,
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"].strip()
        if text:
            return _clean_response(text)
    except Exception as e:
        print(f"[Stormy] _generate_whatsapp_message falhou: {e}")
    return intention


def _lm_chat_with_tools(message: str, memory: ConversationMemory) -> str | None:
    """LM Studio com suporte a tool calling (formato OpenAI)."""
    import json as _json
    import copy

    # Converte TOOL_DEFINITIONS do formato Anthropic para OpenAI
    oai_tools = []
    for td in TOOL_DEFINITIONS:
        schema = copy.deepcopy(td["input_schema"])
        # Remove campos não suportados pelo formato OpenAI
        schema.pop("additionalProperties", None)
        for prop in schema.get("properties", {}).values():
            prop.pop("additionalProperties", None)
        oai_tools.append({
            "type": "function",
            "function": {
                "name": td["name"],
                "description": td["description"],
                "parameters": schema,
            },
        })

    msgs = [
        {"role": "system", "content": AGENT_SYSTEM + _get_contacts_context()},
        {"role": "user", "content": message},
    ]

    for iteration in range(5):
        try:
            print(f"[Stormy] LM Studio com tools (iteração {iteration + 1})...")
            t0 = time.time()
            r = requests.post(
                LM_URL,
                json={
                    "model": LM_MODEL,
                    "messages": msgs,
                    "tools": oai_tools,
                    "stream": False,
                    "temperature": 0.3,
                    "max_tokens": 256,
                },
                timeout=120,
            )
            r.raise_for_status()
            elapsed = time.time() - t0
            choice = r.json()["choices"][0]
            assistant_msg = choice["message"]
            print(f"[Stormy] Resposta LM Studio em {elapsed:.1f}s")
            print(f"[Stormy] LM finish_reason: {choice.get('finish_reason')}, tool_calls: {bool(assistant_msg.get('tool_calls'))}")

            tool_calls = assistant_msg.get("tool_calls")
            if not tool_calls:
                # Sem tool calls - passa por personalidade antes de retornar
                text = (assistant_msg.get("content") or "").strip()
                if not text:
                    return None
                return apply_personality(text, memory)

            # Tem tool calls - executar cada uma
            # Detecta se o usuário quer enviar como ele mesmo
            _msg_lower = message.lower()
            _as_me = any(t in _msg_lower for t in ("se passando por mim", "como se fosse eu", "no meu nome"))

            msgs.append(assistant_msg)
            for tc in tool_calls:
                fn = tc["function"]
                tool_name = fn["name"]
                try:
                    tool_args = _json.loads(fn["arguments"]) if isinstance(fn["arguments"], str) else fn["arguments"]
                except _json.JSONDecodeError:
                    tool_args = {}

                # Intercepta envio de WhatsApp para gerar mensagem com personalidade
                if tool_name == "whatsapp" and tool_args.get("action") == "send":
                    tool_args["message"] = _generate_whatsapp_message(message, _as_me)

                print(f"[Stormy] LM usando ferramenta: {tool_name}")
                result = execute_tool(tool_name, tool_args)
                msgs.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": str(result),
                })
            continue

        except requests.exceptions.Timeout:
            print("[Stormy] LM Studio com tools timeout")
            global _lm_timeout_flag
            _lm_timeout_flag = True
            return None
        except requests.exceptions.HTTPError as e:
            print(f"[Stormy] Erro LM Studio com tools: {e}")
            try:
                print(f"[Stormy] Response body: {e.response.text}")
            except:
                pass
            return None
        except Exception as e:
            print(f"[Stormy] Erro LM Studio com tools: {e}")
            return None

    # Max iterações atingidas - retorna última resposta
    return None


def _lm_sintetizar(message: str, dados: str, memory: ConversationMemory) -> str | None:
    """LM Studio recebe dados externos e sintetiza na personalidade da Stormy."""
    print("[Stormy] LM Studio sintetizando dados externos...")
    msgs = [
        {"role": "system", "content": _build_system_prompt("mesclar", dados)},
        *FEW_SHOT_EXAMPLES,
        *[{"role": m["role"], "content": m["content"]}
          for m in memory.get()[:-1] if isinstance(m.get("content"), str)],
        {"role": "user", "content": message},
    ]
    result = _lm(msgs, max_tokens=400)
    return _clean_response(result) if result else None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract(msg: str, prefixes: tuple) -> str:
    for p in sorted(prefixes, key=len, reverse=True):
        if msg.startswith(p):
            return msg[len(p):].strip()
    return msg.strip()


def _ensure_spotify_auth():
    from spotify_controller import authenticate, is_authenticated
    if not is_authenticated():
        authenticate()


def _handle_pc(msg: str) -> str | None:
    from pc_control import click_on, type_text, press_key
    for p in PC_CLICK_PREFIXES:
        if msg.startswith(p):
            return click_on(_extract(msg, PC_CLICK_PREFIXES))
    for p in PC_TYPE_PREFIXES:
        if msg.startswith(p):
            return type_text(_extract(msg, PC_TYPE_PREFIXES))
    for p in PC_KEY_PREFIXES:
        if msg.startswith(p):
            key = _extract(msg, PC_KEY_PREFIXES).split()[0]
            return press_key(key)
    return None


def _handle_music(msg: str) -> str | None:
    from spotify_controller import (
        play_track, pause, resume, next_track, previous_track,
        set_volume, now_playing, list_devices, transfer_to_device, add_to_queue,
    )
    if any(msg.startswith(p) for p in MUSIC_PLAY_PREFIXES):
        _ensure_spotify_auth()
        q = _extract(msg, MUSIC_PLAY_PREFIXES)
        return play_track(q) if q else None
    if any(msg.startswith(p) for p in MUSIC_QUEUE_PREFIXES):
        _ensure_spotify_auth()
        q = _extract(msg, MUSIC_QUEUE_PREFIXES)
        return add_to_queue(q) if q else None
    if any(msg.startswith(p) for p in MUSIC_TRANSFER_PREFIXES):
        _ensure_spotify_auth()
        d = _extract(msg, MUSIC_TRANSFER_PREFIXES)
        return transfer_to_device(d) if d else None
    if msg.startswith("volume "):
        _ensure_spotify_auth()
        nums = re.findall(r"\d+", msg)
        return set_volume(int(nums[0])) if nums else None
    if msg in MUSIC_SIMPLE:
        _ensure_spotify_auth()
        actions = {
            # pausa
            "pausa": pause, "pausar": pause, "pausa a musica": pause, "pausa isso": pause,
            "pause": pause, "da pause": pause, "para": pause, "para a musica": pause,
            "para isso": pause, "stop": pause,
            # continua
            "continua": resume, "continuar": resume, "resume": resume, "da play": resume,
            "play": resume, "toca": resume, "volta a tocar": resume,
            # proxima
            "proxima": next_track, "próxima": next_track, "proxima faixa": next_track,
            "próxima faixa": next_track, "pula": next_track, "skip": next_track,
            "passa": next_track, "passa a musica": next_track, "next": next_track,
            # anterior
            "anterior": previous_track, "volta": previous_track, "faixa anterior": previous_track,
            "musica anterior": previous_track, "volta a musica": previous_track, "back": previous_track,
            # info
            "o que ta tocando": now_playing, "o que está tocando": now_playing,
            "qual musica": now_playing, "qual música": now_playing,
            "o que e isso": now_playing, "qual e essa": now_playing, "qual é essa": now_playing,
            # dispositivos
            "dispositivos spotify": list_devices, "quais dispositivos": list_devices,
        }
        fn = actions.get(msg)
        return fn() if fn else None
    return None


def _parse_task(response: str) -> str | None:
    m = re.search(r"EXECUTAR_TAREFA:\s*([^\s\n]+)", response, re.IGNORECASE)
    if m:
        return m.group(1).strip().lower().rstrip(".,!?")
    tasks = get_all_tasks()
    cleaned = response.strip().lower().rstrip(".,!?")
    return cleaned if cleaned in tasks else None


def _parse_music_command(response: str) -> tuple[str, str] | None:
    """
    Detecta comandos de música gerados pelo LM.
    Retorna (tipo, query) ou None.
    """
    m = re.search(r"SPOTIFY_COMPLEXO:\s*(.+)", response, re.IGNORECASE)
    if m:
        return "complexo", m.group(1).strip()
    m = re.search(r"TOCAR_MUSICA:\s*(.+)", response, re.IGNORECASE)
    if m:
        return "tocar", m.group(1).strip()
    m = re.search(r"SPOTIFY_ACAO:\s*(\w+)", response, re.IGNORECASE)
    if m:
        return "acao", m.group(1).strip().lower()
    return None


def _execute_music_command(tipo: str, query: str, memory: ConversationMemory) -> str:
    """Executa comando de música extraído do LM."""
    from spotify_controller import (
        play_track, pause, resume, next_track, previous_track, now_playing, add_to_queue
    )
    _ensure_spotify_auth()

    # Spotify complexo — manda pro Claude com ferramentas
    if tipo == "complexo":
        try:
            return _claude(memory, modo="buscar")
        except Exception as e:
            return _claude_error(e)

    if tipo == "tocar":
        return play_track(query)

    if tipo == "acao":
        acoes = {
            "pausa": pause, "pausar": pause,
            "continua": resume, "resume": resume, "play": resume,
            "proxima": next_track, "pula": next_track, "skip": next_track,
            "anterior": previous_track, "volta": previous_track,
            "tocando": now_playing, "atual": now_playing,
        }
        fn = acoes.get(query)
        return fn() if fn else f"acao desconhecida: {query}"
    return "comando invalido"


def _run_task(name: str) -> str | None:
    tasks = get_all_tasks()
    if name in tasks:
        return execute_tool("open_app", {"app_name": name})
    for key in tasks:
        if name in key or key in name:
            return execute_tool("open_app", {"app_name": key})
    return None


# ── Claude ────────────────────────────────────────────────────────────────────

def _get_client():
    global _anthropic_client
    if _anthropic_client is None:
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY nao encontrada no .env")
        _anthropic_client = anthropic.Anthropic(api_key=key)
    return _anthropic_client


def _clean_msgs(messages: list[dict]) -> list[dict]:
    clean = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list) and any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in content
        ):
            if clean and isinstance(clean[-1].get("content"), list) and any(
                hasattr(b, "type") and b.type == "tool_use"
                or (isinstance(b, dict) and b.get("type") == "tool_use")
                for b in clean[-1]["content"]
            ):
                clean.append(msg)
        else:
            clean.append(msg)
    return clean


def _claude(memory: ConversationMemory, modo: str = "completo", dados: str = "") -> str:
    client = _get_client()
    print(f"[Stormy] Buscando via Claude (modo={modo})...")
    t0 = time.time()
    while True:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=512,
            system=_build_system_prompt(modo, dados),
            messages=_clean_msgs(memory.get()),
            tools=TOOL_DEFINITIONS,
        )
        if response.stop_reason == "tool_use":
            results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"[Stormy] Claude usando ferramenta: {block.name}")
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": execute_tool(block.name, block.input),
                    })
            memory.add_assistant(response.content)
            memory.add_tool_results(results)
            continue
        text = "".join(b.text for b in response.content if hasattr(b, "text")).strip()
        text = apply_personality(text, memory)
        print(f"[Stormy] Resposta Claude recebida em {time.time() - t0:.1f}s")
        memory.add_assistant(text, engine="claude")
        return text


def _claude_buscar(memory: ConversationMemory) -> str:
    """Claude busca dados e retorna o resultado bruto (sem formatar na personalidade)."""
    print("[Stormy] Claude buscando dados externos...")
    t0 = time.time()
    client = _get_client()
    system = _build_system_prompt("buscar")
    msgs = _clean_msgs(memory.get())

    # Adiciona data atual
    if msgs and msgs[-1]["role"] == "user":
        today = datetime.now().strftime("%d/%m/%Y")
        msgs[-1]["content"] = f"{msgs[-1]['content']} (hoje: {today})"

    dados_coletados = []

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=system,
            messages=msgs,
            tools=TOOL_DEFINITIONS,
        )
        if response.stop_reason == "tool_use":
            results = []
            for block in response.content:
                if block.type == "tool_use":
                    resultado = execute_tool(block.name, block.input)
                    dados_coletados.append(resultado)
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": resultado,
                    })
            memory.add_assistant(response.content)
            memory.add_tool_results(results)
            msgs = _clean_msgs(memory.get())
            continue

        # Retorna os dados coletados pelas ferramentas
        if dados_coletados:
            print(f"[Stormy] Dados externos coletados em {time.time() - t0:.1f}s")
            return "\n\n".join(dados_coletados)

        # Se não usou ferramentas, retorna o texto do Claude mesmo
        print(f"[Stormy] Claude respondeu direto em {time.time() - t0:.1f}s")
        return "".join(b.text for b in response.content if hasattr(b, "text")).strip()


def _claude_error(e: Exception) -> str:
    err = str(e).lower()
    if "credit" in err or "billing" in err or "balance" in err:
        return "po acabou o credito da api kk adiciona mais no console.anthropic.com"
    if "connection" in err or "timeout" in err:
        return "sem internet agora prc"
    return f"deu erro aqui: {e}"


# ── Roteador principal ────────────────────────────────────────────────────────

def _append_wa_notifications(response: str, engine: str) -> tuple[str, str]:
    """Anexa notificações de WhatsApp pendentes ao final da resposta."""
    # Não notificar se a resposta já é sobre WhatsApp
    wa_keywords = ("whatsapp", "mensagem enviada", "contato", "[STORMY]")
    if any(k in response.lower() for k in wa_keywords):
        return response, engine

    notifs = get_pending_notifications()
    if not notifs:
        return response, engine

    # Nomes únicos, preservando ordem
    seen = set()
    names = []
    for n in notifs:
        name = n.get("sender_name", "?")
        if name not in seen:
            seen.add(name)
            names.append(name)

    if len(names) <= 3:
        nomes_str = ", ".join(names)
    else:
        nomes_str = ", ".join(names[:3]) + f" +{len(names) - 3} mensagens"

    response += f"\n\n[WhatsApp] {nomes_str} te mandaram mensagem"
    return response, engine


def chat(message: str, memory: ConversationMemory) -> tuple[str, str]:
    result = _chat_inner(message, memory)
    return _append_wa_notifications(*result)


def _chat_inner(message: str, memory: ConversationMemory) -> tuple[str, str]:
    memory.add_user(message)
    msg = message.lower().strip()

    # 0. Verifica se LM estava aguardando confirmação de pesquisa
    CONFIRMAR = {"sim", "pode", "vai lá", "vai la", "claro", "bora", "pesquisa", "busca", "ok", "s", "yes"}
    prev_msgs = memory.get()
    if len(prev_msgs) >= 2:
        last_assistant = prev_msgs[-2]
        last_content = last_assistant.get("content", "")
        if isinstance(last_content, str) and "\x00AGUARDA_PESQUISA" in last_content:
            if msg in CONFIRMAR or len(msg) <= 5:
                # Usuário confirmou - vai pro Claude buscar
                try:
                    # Remove o marcador da memória antes de chamar o Claude
                    prev_msgs[-2]["content"] = last_content.replace("\x00AGUARDA_PESQUISA", "").strip()
                    r = _claude_buscar(memory)
                    if r:
                        r_final = _lm_sintetizar(message, r, memory) or _clean_response(r)
                        memory.add_assistant(r_final, engine="lm_studio+claude")
                        return r_final, "lm_studio+claude"
                except Exception as e:
                    pass

    # 1. Comandos de PC - direto, sem IA
    r = _handle_pc(msg)
    if r:
        memory.add_assistant(r, engine="local")
        return r, "local"

    # 2. Música simples - direto, sem IA
    if not any(t in msg for t in MUSIC_COMPLEX):
        r = _handle_music(msg)
        if r:
            memory.add_assistant(r, engine="local")
            return r, "local"

    # 3. Abrir app - direto, sem IA
    for trigger in LOCAL_APP_TRIGGERS:
        if msg.startswith(trigger):
            app = msg[len(trigger):].replace(" o ", " ").replace(" a ", " ").strip()
            r = _run_task(app)
            if r:
                memory.add_assistant(r, engine="local")
                return r, "local"
            break

    # 4. Visão - ScreenWatcher sob demanda
    if any(t in msg for t in VISION_TRIGGERS):
        from screen_watcher import start as sw_start, describe, _state as sw_state
        if not sw_state.get("running"):
            sw_start()
            for _ in range(15):
                if sw_state.get("model_ready"):
                    break
                time.sleep(1)
        if not sw_state.get("model_ready"):
            r = "o modelo de visão ainda tá carregando, espera uns segundos"
        else:
            r = describe(message)
            if not r or "não consegui" in r.lower():
                r = "não consegui ver a tela agora, tenta de novo em alguns segundos"
        r = _clean_response(r)
        memory.add_assistant(r, engine="local")
        return r, "local"

    # 5. Saudação ou mensagem curta - LM direto, sem classificar
    _needs_cloud = any(t in msg for t in CLOUD_REQUIRED)
    if not _needs_cloud and (msg in DIRECT_LOCAL or len(msg) <= 20):
        print("[Stormy] Mensagem curta/saudação → LM Studio direto")
        r = _lm_chat(message, memory)
        if r:
            # Intercepta comandos de música
            music_cmd = _parse_music_command(r)
            if music_cmd:
                result = _execute_music_command(*music_cmd, memory)
                engine = "claude" if music_cmd[0] == "complexo" else "local"
                memory.add_assistant(result, engine=engine)
                return result, engine
            r_clean = r.replace("\x00AGUARDA_PESQUISA", "").strip()
            memory.add_assistant(r, engine="lm_studio")
            return r_clean, "lm_studio"
        if _lm_timeout_flag:
            try:
                r = _claude(memory)
                return r, "claude"
            except Exception as e:
                return _claude_error(e), "claude"

    # 6. CLOUD_REQUIRED — vai direto pro Claude com ferramentas
    if any(t in msg for t in CLOUD_REQUIRED):
        try:
            r = _claude(memory)
            return r, "claude"
        except Exception as e:
            return _claude_error(e), "claude"

    # 7. Classificador inteligente (3 camadas)
    clf = _classify(message)

    # Spotify complexo - vai direto pro Claude com ferramentas
    if clf.get("spotify_complexo"):
        try:
            r = _claude(memory, modo="buscar")
            return r, "claude"
        except Exception as e:
            return _claude_error(e), "claude"

    # Camada 1 - não precisa de dado externo → LM com tools
    # Exceto se for factual específico - aí Claude verifica
    if not clf.get("precisa_externo") and not clf.get("factual_especifico"):
        print("[Stormy] Camada 1 → LM Studio com tools (sem dado externo)")
        r = _lm_chat_with_tools(message, memory)
        if r:
            # Intercepta comandos de música
            music_cmd = _parse_music_command(r)
            if music_cmd:
                result = _execute_music_command(*music_cmd, memory)
                engine = "claude" if music_cmd[0] == "complexo" else "local"
                memory.add_assistant(result, engine=engine)
                return result, engine
            task = _parse_task(r)
            if task:
                result = _run_task(task)
                if result:
                    memory.add_assistant(result, engine="local")
                    return result, "local"
            r_clean = r.replace("\x00AGUARDA_PESQUISA", "").strip()
            memory.add_assistant(r, engine="lm_studio")
            return r_clean, "lm_studio"
        if _lm_timeout_flag:
            print("[Stormy] Fallback → Claude")
            try:
                r = _claude(memory)
                return r, "claude"
            except Exception as e:
                return _claude_error(e), "claude"

    # Factual específico sem dado externo → Claude confirma com busca rápida
    if clf.get("factual_especifico") and not clf.get("precisa_externo"):
        try:
            r = _claude(memory, modo="buscar")
            return r, "claude"
        except Exception as e:
            # Fallback pro LM com tools
            r = _lm_chat_with_tools(message, memory)
            if r:
                memory.add_assistant(r, engine="lm_studio")
                return r, "lm_studio"

    # Camada 2 - precisa de dado externo
    try:
        print("[Stormy] Camada 2 → buscando dados externos via Claude")
        dados = _claude_buscar(memory)

        if dados:
            # SEMPRE sintetiza via LM Studio na personalidade da Stormy
            r = _lm_sintetizar(message, dados, memory)
            if r:
                memory.add_assistant(r, engine="lm_studio")
                return r, "lm_studio+claude"

        # Fallback - Claude responde direto com os dados
        r = _clean_response(dados) if dados else _claude(memory, modo="completo")
        if not isinstance(r, str) or not r:
            r = _claude(memory, modo="completo")
        memory.add_assistant(r, engine="claude")
        return r, "claude"

    except Exception as e:
        r = _claude_error(e)
        return r, "claude"

    # 7. LM offline → Claude fallback
    try:
        r = _claude(memory)
        return r, "claude"
    except Exception as e:
        r = _claude_error(e)
        return r, "claude"


def request_handoff_to(device: str, memory: ConversationMemory) -> tuple[str, str]:
    from sync import is_available, request_handoff, update_device_state
    if not is_available():
        return "sem conexao com supabase prc", "local"
    if request_handoff(from_device="pc", to_device=device):
        update_device_state(device)
        return f"fui pro {device} pode me chamar por la o papo continua", "local"
    return "nao consegui fazer o handoff agora", "local"