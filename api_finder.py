"""
Busca APIs públicas, ocultas e gratuitas que a comunidade de devs já descobriu.
Pesquisa em GitHub, Stack Overflow, Reddit e RapidAPI.
"""

from search import brave_search


def find_public_api(need: str) -> str:
    """
    Recebe uma descrição do que precisa e retorna sugestões de APIs
    públicas, gratuitas ou não documentadas que a comunidade já descobriu.
    """

    searches = [
        f"{need} free API no key required",
        f"{need} hidden API endpoint site:github.com",
        f"{need} API gratuita sem cadastro",
        f"{need} undocumented API site:stackoverflow.com OR site:reddit.com",
    ]

    all_results = []

    for query in searches[:2]:
        result = brave_search(query, count=3)
        if result and "Erro" not in result and "Nenhum resultado" not in result:
            all_results.append(result)

    if not all_results:
        return "Não encontrei APIs específicas pra isso agora. Tenta reformular o que precisa."

    combined = "\n\n---\n\n".join(all_results)
    return combined


def find_hidden_api(service: str) -> str:
    """
    Tenta descobrir APIs não documentadas de um serviço específico.
    Ex: 'ESPN', 'Globo Esporte', 'SofaScore'
    """

    searches = [
        f"{service} hidden API endpoint documentation site:github.com",
        f"{service} unofficial API free site:stackoverflow.com",
        f"how to use {service} API without key reddit",
    ]

    all_results = []

    for query in searches[:2]:
        result = brave_search(query, count=3)
        if result and "Erro" not in result and "Nenhum resultado" not in result:
            all_results.append(result)

    if not all_results:
        return f"Não achei uma API oculta pra {service} agora."

    return "\n\n---\n\n".join(all_results)
