"""
Dados meteorológicos via Open-Meteo — 100% gratuito, sem API key.
Geocodificação via Open-Meteo Geocoding API.
"""

import requests

GEO_URL     = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

SP_BAIRROS = {
    "cachoeirinha":           (-23.4800, -46.6200),
    "vila nova cachoeirinha": (-23.4800, -46.6200),
    "limao":                  (-23.4900, -46.6400),
    "santana":                (-23.4900, -46.6300),
    "tucuruvi":               (-23.4700, -46.6000),
    "jacana":                 (-23.4500, -46.5900),
    "casa verde":             (-23.5000, -46.6400),
    "brasilandia":            (-23.4700, -46.6800),
    "pirituba":               (-23.4900, -46.7200),
    "sao paulo":              (-23.5505, -46.6333),
    "sp":                     (-23.5505, -46.6333),
}

WMO_CODES = {
    0: "Ceu limpo", 1: "Principalmente limpo", 2: "Parcialmente nublado",
    3: "Nublado", 45: "Neblina", 51: "Chuvisco leve", 53: "Chuvisco moderado",
    61: "Chuva leve", 63: "Chuva moderada", 65: "Chuva forte",
    80: "Pancadas leves", 81: "Pancadas moderadas", 82: "Pancadas fortes",
    95: "Tempestade", 99: "Tempestade com granizo",
}


def _normalize(text):
    import unicodedata
    return unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()


def _geocode(location):
    loc = _normalize(location)
    for key, coords in SP_BAIRROS.items():
        if key in loc or loc in key:
            return coords[0], coords[1], location.title()
    try:
        r = requests.get(
            GEO_URL,
            params={"name": location, "count": 1, "language": "pt", "countryCode": "BR"},
            timeout=8,
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        if results:
            res = results[0]
            name = res.get("name", location)
            admin = res.get("admin1", "")
            display = f"{name}, {admin}" if admin else name
            return res["latitude"], res["longitude"], display
    except Exception:
        pass
    return None


def get_weather(location: str) -> str:
    geo = _geocode(location)
    if not geo:
        return f"Nao consegui localizar '{location}'. Tenta colocar a cidade junto, tipo 'Cachoeirinha, SP'."

    lat, lon, display_name = geo

    try:
        r = requests.get(
            WEATHER_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": [
                    "temperature_2m", "apparent_temperature",
                    "relative_humidity_2m", "weather_code",
                    "wind_speed_10m", "precipitation",
                ],
                "daily": [
                    "temperature_2m_max", "temperature_2m_min",
                    "precipitation_sum",
                ],
                "timezone": "America/Sao_Paulo",
                "forecast_days": 3,
                "wind_speed_unit": "kmh",
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()

        cur  = data.get("current", {})
        daily = data.get("daily", {})

        temp       = cur.get("temperature_2m", "?")
        feels_like = cur.get("apparent_temperature", "?")
        humidity   = cur.get("relative_humidity_2m", "?")
        wind       = cur.get("wind_speed_10m", "?")
        rain       = cur.get("precipitation", 0) or 0
        condition  = WMO_CODES.get(cur.get("weather_code", 0), "?")

        max_temps  = daily.get("temperature_2m_max", [])
        min_temps  = daily.get("temperature_2m_min", [])
        rain_days  = daily.get("precipitation_sum", [])

        lines = [
            f"Clima em {display_name}:",
            f"Temperatura: {temp}C (sensacao {feels_like}C)",
            f"Condicao: {condition}",
            f"Umidade: {humidity}%",
            f"Vento: {wind} km/h",
        ]

        if rain > 0:
            lines.append(f"Chuva agora: {rain}mm")

        if max_temps and len(max_temps) >= 3:
            lines.append("")
            lines.append("Proximos dias:")
            dias = ["Hoje", "Amanha", "Depois de amanha"]
            for i in range(3):
                chuva = f" | {rain_days[i]:.0f}mm chuva" if rain_days[i] > 0 else ""
                lines.append(f"  {dias[i]}: {min_temps[i]:.0f}C - {max_temps[i]:.0f}C{chuva}")

        return "\n".join(lines)

    except Exception as e:
        return f"Erro ao buscar clima: {e}"
