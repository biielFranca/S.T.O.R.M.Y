"""
Dados esportivos via ESPN API oculta — gratuita, sem chave.
Endpoints mapeados pela comunidade em:
github.com/pseudo-r/Public-ESPN-API
gist.github.com/akeaswaran/b48b02f1c94f873c6655e7129910fc3b
"""

import requests
from datetime import datetime

SITE_API   = "https://site.api.espn.com/apis/site/v2/sports"
WEB_API    = "https://site.web.api.espn.com/apis/v2/sports"
CORE_API   = "https://sports.core.api.espn.com/v2/sports"

LEAGUES = {
    "brasileirao": "bra.1",
    "brasileirão": "bra.1",
    "serie a": "bra.1",
    "serie b": "bra.2",
    "série b": "bra.2",
    "copa do brasil": "bra.cup",
    "libertadores": "conmebol.libertadores",
    "sul-americana": "conmebol.sudamericana",
    "sulamericana": "conmebol.sudamericana",
    "champions": "uefa.champions",
    "premier league": "eng.1",
    "la liga": "esp.1",
    "serie a italiana": "ita.1",
    "bundesliga": "ger.1",
    "ligue 1": "fra.1",
}


def _get_league_id(query: str) -> str:
    q = query.lower().strip()
    for key, val in LEAGUES.items():
        if key in q:
            return val
    return "bra.1"


def get_standings(league_query: str = "brasileirao") -> str:
    league_id = _get_league_id(league_query)
    year = datetime.now().year

    # Endpoint correto para tabela com season
    url = f"{WEB_API}/soccer/{league_id}/standings?season={year}"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        entries = []
        # Navega na estrutura da resposta
        for group in data.get("children", []):
            for entry in group.get("standings", {}).get("entries", []):
                entries.append(entry)

        if not entries:
            # Tenta estrutura alternativa
            entries = data.get("standings", {}).get("entries", [])

        if not entries:
            return "Tabela temporariamente indisponível."

        lines = []
        for entry in entries[:20]:
            team = entry.get("team", {}).get("displayName", "?")
            stats = {s["name"]: s.get("displayValue", s.get("value", "?"))
                     for s in entry.get("stats", [])}
            pos  = stats.get("rank", stats.get("playoffSeed", "?"))
            pts  = stats.get("points", "?")
            pg   = stats.get("gamesPlayed", "?")
            v    = stats.get("wins", "?")
            e    = stats.get("ties", "?")
            d    = stats.get("losses", "?")
            sg   = stats.get("pointDifferential", stats.get("goalDifference", "?"))
            lines.append(f"{pos}. {team} | {pts}pts | {pg}J {v}V {e}E {d}D | SG:{sg}")

        return "\n".join(lines) if lines else "Tabela indisponível no momento."

    except Exception as e:
        return f"Erro ao buscar tabela: {e}"


def get_scoreboard(league_query: str = "brasileirao") -> str:
    league_id = _get_league_id(league_query)
    url = f"{SITE_API}/soccer/{league_id}/scoreboard"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        events = data.get("events", [])
        if not events:
            return "Nenhuma partida encontrada no momento."

        lines = []
        for event in events[:10]:
            status = event.get("status", {}).get("type", {}).get("description", "")
            competitions = event.get("competitions", [{}])
            competitors = competitions[0].get("competitors", [])

            if len(competitors) == 2:
                home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
                away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
                hn = home.get("team", {}).get("shortDisplayName", "?")
                an = away.get("team", {}).get("shortDisplayName", "?")
                hs = home.get("score", "-")
                as_ = away.get("score", "-")
                lines.append(f"{hn} {hs} x {as_} {an}  [{status}]")

        return "\n".join(lines) if lines else "Sem jogos encontrados."

    except Exception as e:
        return f"Erro ao buscar resultados: {e}"


def get_top_scorers(league_query: str = "brasileirao") -> str:
    league_id = _get_league_id(league_query)
    url = f"{SITE_API}/soccer/{league_id}/leaders"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        categories = data.get("categories", [])
        if not categories:
            return "Artilharia indisponível no momento."

        lines = ["Artilharia:"]
        for cat in categories[:1]:  # só gols
            for i, leader in enumerate(cat.get("leaders", [])[:10], 1):
                athlete = leader.get("athlete", {})
                name  = athlete.get("displayName", "?")
                team  = leader.get("team", {}).get("displayName", "?")
                value = leader.get("value", "?")
                lines.append(f"{i}. {name} ({team}) — {int(value)} gols")

        return "\n".join(lines)

    except Exception as e:
        return f"Erro ao buscar artilharia: {e}"


def get_news(league_query: str = "brasileirao") -> str:
    league_id = _get_league_id(league_query)
    url = f"{SITE_API}/soccer/{league_id}/news"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        articles = data.get("articles", [])
        if not articles:
            return "Sem notícias no momento."

        lines = []
        for article in articles[:5]:
            headline = article.get("headline", "")
            published = article.get("published", "")[:10]
            if headline:
                lines.append(f"• {headline}  [{published}]")

        return "\n".join(lines) if lines else "Sem notícias disponíveis."

    except Exception as e:
        return f"Erro ao buscar notícias: {e}"


def get_team_schedule(team_name: str, league_query: str = "brasileirao") -> str:
    """Busca próximos jogos de um time específico."""
    league_id = _get_league_id(league_query)

    # Primeiro busca o ID do time
    teams_url = f"{SITE_API}/soccer/{league_id}/teams"
    try:
        r = requests.get(teams_url, timeout=10)
        r.raise_for_status()
        teams_data = r.json()

        team_id = None
        team_found = ""
        for team in teams_data.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", []):
            t = team.get("team", {})
            if team_name.lower() in t.get("displayName", "").lower() or \
               team_name.lower() in t.get("shortDisplayName", "").lower():
                team_id = t.get("id")
                team_found = t.get("displayName", team_name)
                break

        if not team_id:
            return f"Time '{team_name}' não encontrado."

        # Busca agenda do time
        sched_url = f"{SITE_API}/soccer/{league_id}/teams/{team_id}/schedule"
        r2 = requests.get(sched_url, timeout=10)
        r2.raise_for_status()
        sched = r2.json()

        events = sched.get("events", [])
        if not events:
            return f"Sem jogos encontrados para {team_found}."

        lines = [f"Próximos jogos do {team_found}:"]
        count = 0
        for event in events:
            status = event.get("status", {}).get("type", {}).get("state", "")
            if status == "pre" and count < 5:
                name = event.get("name", "")
                date = event.get("date", "")[:10]
                lines.append(f"• {name}  [{date}]")
                count += 1

        return "\n".join(lines) if len(lines) > 1 else f"Sem próximos jogos para {team_found}."

    except Exception as e:
        return f"Erro ao buscar agenda do time: {e}"
