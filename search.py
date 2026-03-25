import os
import requests
from dotenv import load_dotenv

load_dotenv()


def brave_search(query: str, count: int = 5) -> str:
    api_key = os.getenv("BRAVE_API_KEY")

    if not api_key:
        return "Erro: BRAVE_API_KEY não configurada no .env"

    try:
        response = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": api_key,
            },
            params={
                "q": query,
                "count": count,
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        results = data.get("web", {}).get("results", [])

        if not results:
            return "Nenhum resultado encontrado."

        parts = []
        for r in results:
            title = r.get("title", "")
            url = r.get("url", "")
            description = r.get("description", "")
            if title or description:
                parts.append(f"Fonte: {title}\nURL: {url}\nResumo: {description}")

        return "\n\n---\n\n".join(parts)

    except requests.Timeout:
        return "A busca demorou demais. Tente novamente."
    except Exception as e:
        return f"Erro na busca: {e}"
