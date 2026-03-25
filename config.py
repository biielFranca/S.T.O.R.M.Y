ASSISTANT_NAME = "Stormy"

WAKE_WORDS = ("stormy ", "stormy,", "stormy:")

EXIT_WORDS = {"sair", "fechar", "encerrar", "exit", "quit"}

# Apps e sites que a Stormy conhece por padrão
BASE_TASKS = {
    "spotify": {
        "type": "system",
        "value": "start spotify",
        "success_message": "Abrindo o Spotify.",
    },
    "youtube": {
        "type": "url",
        "value": "https://www.youtube.com",
        "success_message": "Abrindo o YouTube.",
    },
    "whatsapp": {
        "type": "url",
        "value": "https://web.whatsapp.com",
        "success_message": "Abrindo o WhatsApp Web.",
    },
    "brave": {
        "type": "system",
        "value": "start brave",
        "success_message": "Abrindo o Brave.",
    },
    "notepad": {
        "type": "system",
        "value": "start notepad",
        "success_message": "Abrindo o Bloco de Notas.",
    },
    "bloco de notas": {
        "type": "system",
        "value": "start notepad",
        "success_message": "Abrindo o Bloco de Notas.",
    },
    "github": {
        "type": "url",
        "value": "https://github.com",
        "success_message": "Abrindo o GitHub.",
    },
    "instagram": {
        "type": "url",
        "value": "https://www.instagram.com",
        "success_message": "Abrindo o Instagram.",
    },
    "tiktok": {
        "type": "url",
        "value": "https://www.tiktok.com",
        "success_message": "Abrindo o TikTok.",
    },
}

CUSTOM_TASKS_FILE = "custom_tasks.json"
CUSTOM_KEYWORDS_FILE = "custom_keywords.json"

# Tavily
TAVILY_SEARCH_URL = "https://api.tavily.com/search"
TAVILY_MAX_RESULTS = 3
TAVILY_SEARCH_DEPTH = "basic"
TAVILY_INCLUDE_ANSWER = True

# Histórico de conversa (número de mensagens mantidas)
MEMORY_MAX_MESSAGES = 40
