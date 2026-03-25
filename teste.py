import time, sys
sys.path.insert(0, '.')
from agent import chat
from memory import ConversationMemory

perguntas = [
    "slv",
    "qual o clima hoje na cachoeirinha",
    "quem lidera o brasileirao",
    "me explica o que e machine learning",
]

for p in perguntas:
    memory = ConversationMemory()
    memory.clear()  # ignora histórico anterior — teste limpo
    inicio = time.time()
    resposta, engine = chat(p, memory)
    fim = time.time()
    memory.close()
    print(f"\n[{fim-inicio:.1f}s] '{p}' [{engine}]")
    print(f"Stormy: {resposta[:80]}")