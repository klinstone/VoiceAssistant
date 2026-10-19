# -*- coding: utf-8 -*-
"""Инструменты, которые может вызывать модель: поиск, погода, курсы валют."""
import time

from . import config as cfg
from .log import log

WMO = {0: "ясно", 1: "в основном ясно", 2: "переменная облачность", 3: "пасмурно", 45: "туман",
       48: "изморозь", 51: "слабая морось", 53: "морось", 55: "сильная морось", 61: "слабый дождь",
       63: "дождь", 65: "сильный дождь", 66: "ледяной дождь", 67: "ледяной дождь", 71: "слабый снег",
       73: "снег", 75: "сильный снег", 77: "снежная крупа", 80: "ливень", 81: "сильный ливень",
       82: "очень сильный ливень", 85: "снегопад", 86: "сильный снегопад", 95: "гроза",
       96: "гроза с градом", 99: "сильная гроза с градом"}

TOOLS = [
    {"type": "function", "function": {
        "name": "web_search",
        "description": "Поиск в интернете: новости, факты, результаты событий, всё, что могло измениться. "
                       "Не использовать для погоды и курсов валют.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Точный поисковый запрос"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "get_weather",
        "description": "Текущая погода и прогноз на 3 дня для города.",
        "parameters": {"type": "object", "properties": {
            "city": {"type": "string", "description": "Название города"}}, "required": ["city"]}}},
    {"type": "function", "function": {
        "name": "get_exchange_rate",
        "description": "Актуальный курс валюты, быстрый вызов. Например доллар к рублю: base=USD, target=RUB.",
        "parameters": {"type": "object", "properties": {
            "base": {"type": "string", "description": "Код валюты, которую меняем, например USD"},
            "target": {"type": "string", "description": "Код валюты, в которой выражаем курс, например RUB"}},
            "required": ["base", "target"]}}},
]


def web_search(query):
    try:
        from ddgs import DDGS
        res = DDGS(timeout=6).text(query, max_results=4, region="wt-wt")
    except Exception as e:
        return f"Ошибка поиска: {e}"
    if not res:
        return "Ничего не найдено."
    return "\n".join(f"{r.get('title', '')}: {r.get('body', '')}" for r in res)[:2000]


def get_weather(city):
    try:
        import requests
        g = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                         params={"name": city, "count": 1, "language": "ru"}, timeout=8).json()
        if not g.get("results"):
            return f"Город «{city}» не найден."
        r = g["results"][0]
        f = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": r["latitude"], "longitude": r["longitude"],
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,precipitation",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
            "timezone": "auto", "forecast_days": 3, "wind_speed_unit": "ms"}, timeout=8).json()
        c, d = f["current"], f["daily"]
        out = [f"{r.get('name', city)}. Сейчас: {c['temperature_2m']}°C, ощущается как "
               f"{c['apparent_temperature']}°C, {WMO.get(c['weather_code'], 'без описания')}, "
               f"ветер {c['wind_speed_10m']} м/с."]
        for i, day in enumerate(d["time"]):
            out.append(f"{day}: от {d['temperature_2m_min'][i]} до {d['temperature_2m_max'][i]}°C, "
                       f"{WMO.get(d['weather_code'][i], '')}, вероятность осадков "
                       f"{d['precipitation_probability_max'][i]}%.")
        return "\n".join(out)
    except Exception as e:
        return f"Ошибка получения погоды: {e}"


def get_exchange_rate(base, target):
    base, target = (base or "USD").upper(), (target or "RUB").upper()
    try:
        import requests
        r = requests.get(f"https://open.er-api.com/v6/latest/{base}", timeout=6).json()
        if r.get("result") != "success":
            return f"Не удалось получить курс: {r.get('error-type', 'ошибка')}. Можно попробовать web_search."
        rate = r["rates"].get(target)
        if rate is None:
            return f"Нет курса для {target}."
        return f"1 {base} = {rate} {target} (обновлено {r.get('time_last_update_utc', '')})"
    except Exception as e:
        return f"Ошибка получения курса: {e}. Можно попробовать web_search."


def run_tool(name, args):
    t0 = time.time()
    try:
        if name == "web_search":
            res = web_search(args.get("query", ""))
        elif name == "get_weather":
            res = get_weather(args.get("city") or cfg.DEFAULT_CITY)
        elif name == "get_exchange_rate":
            res = get_exchange_rate(args.get("base"), args.get("target"))
        else:
            res = "Неизвестный инструмент."
    except Exception as e:
        res = f"Ошибка инструмента: {e}"
    log(f"Инструмент {name} {args} -> {time.time() - t0:.1f} с")
    return res
