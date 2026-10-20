# -*- coding: utf-8 -*-
"""Инструменты, которые может вызывать модель.
Чтобы добавить новый: напишите функцию, оформите её декоратором @tool(...) ниже и упомяните в prompt.py.
Ненужные инструменты отключаются в config.py: DISABLED_TOOLS = ["look_at_screen", ...]
(каждая схема отправляется модели в каждом запросе, лишние инструменты слегка замедляют ответ)."""
import time

from . import settings
from .log import log

_REG = {}
MAX_RESULT = 6000


def _schema(name, description, props=None, required=None):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": props or {}, "required": required or []}}}


def tool(name, description, props=None, required=None, status="", fast=False):
    """fast=True: инструмент мгновенный, перед ним не нужно говорить «Секунду»."""
    def deco(fn):
        _REG[name] = {"schema": _schema(name, description, props, required), "fn": fn,
                      "status": status or name, "fast": fast}
        return fn
    return deco


def _s(desc, **kw):
    return {"type": "string", "description": desc, **kw}


# ------------------------------ интернет ------------------------------
@tool("web_search",
      "Поиск в интернете: новости, факты, события, всё, что могло измениться. Не для погоды и курсов валют. "
      "Возвращает заголовки, отрывки и ссылки; чтобы разобраться подробнее, откройте ссылку через read_webpage.",
      {"query": _s("Точный поисковый запрос"),
       "kind": _s("text — обычный поиск (по умолчанию), news — свежие новости, video — видео", enum=["text", "news", "video"]),
       "period": _s("Ограничение по давности: d — сутки, w — неделя, m — месяц, y — год", enum=["d", "w", "m", "y"])},
      ["query"], status="Ищу в интернете…")
def _web_search(a):
    from . import web
    return web.web_search(a.get("query"), a.get("kind", "text"), a.get("period"))


@tool("read_webpage",
      "Прочитать страницу целиком по ссылке (статью из результатов поиска) или получить текст субтитров видео на YouTube, "
      "чтобы пересказать или ответить по содержанию.",
      {"url": _s("Ссылка, начинающаяся с http:// или https://")}, ["url"], status="Читаю страницу…")
def _read_webpage(a):
    from . import web
    return web.read_webpage(a.get("url"))


@tool("get_weather", "Текущая погода и прогноз на 3 дня для города.",
      {"city": _s("Название города")}, ["city"], status="Смотрю погоду…")
def _get_weather(a):
    from . import config as cfg, web
    return web.get_weather(a.get("city") or cfg.DEFAULT_CITY)


@tool("get_exchange_rate",
      "Актуальный курс валюты или криптовалюты (BTC, ETH, TON, USDT...). Например доллар к рублю: base=USD, target=RUB.",
      {"base": _s("Код валюты, которую меняем, например USD или BTC"),
       "target": _s("Код валюты, в которой выражаем курс, например RUB или USD")},
      ["base", "target"], status="Проверяю курс…")
def _get_exchange_rate(a):
    from . import web
    return web.get_exchange_rate(a.get("base"), a.get("target"))


@tool("world_time", "Который сейчас час в другом городе или стране.",
      {"city": _s("Название города")}, ["city"], status="Узнаю время…")
def _world_time(a):
    from . import web
    return web.world_time(a.get("city"))


@tool("calculate", "Точно вычислить выражение: + - * / ** % //, скобки, sqrt, sin, cos, log, round, min, max, pi. "
                   "Проценты записывай как 0.15*2000. Десятичная точка, не запятая.",
      {"expression": _s("Математическое выражение")}, ["expression"], fast=True)
def _calculate(a):
    from . import calc
    return calc.calculate(a.get("expression"))


# ------------------------------ таймеры, заметки, память ------------------------------
@tool("timer",
      "Таймеры и напоминания (сработают звуком и голосом даже без участия модели). "
      "set: либо seconds (через сколько секунд), либо at (во сколько, формат ЧЧ:ММ или ГГГГ-ММ-ДД ЧЧ:ММ). "
      "list — показать активные, cancel — отменить (по названию, label=все — отменить все).",
      {"action": _s("set, list или cancel", enum=["set", "list", "cancel"]),
       "seconds": {"type": "number", "description": "Через сколько секунд сработать (для таймера)"},
       "at": _s("Точное время срабатывания (для напоминания)"),
       "label": _s("Короткое название, что напомнить, например «пельмени»")},
      ["action"], fast=True)
def _timer(a):
    from . import reminders
    return reminders.timer(a.get("action"), a.get("seconds"), a.get("at"), a.get("label"))


@tool("notes",
      "Заметки и списки (например, покупки), сохраняются в файл. add — записать, read — прочитать, "
      "delete — вычеркнуть запись (по её тексту), clear — очистить весь список.",
      {"action": _s("add, read, delete или clear", enum=["add", "read", "delete", "clear"]),
       "text": _s("Текст записи (для add и delete)"),
       "list_name": _s("Название списка: «покупки», «задачи»... По умолчанию «заметки». Для read без названия читаются все")},
      ["action"], fast=True)
def _notes(a):
    from . import notes
    return notes.notes_tool(a.get("action"), a.get("text"), a.get("list_name"))


@tool("remember",
      "Надолго запомнить факт о пользователе (предпочтения, имена близких, привычки). "
      "Использовать только когда пользователь сам просит запомнить. add — запомнить, forget — забыть, list — что помнишь.",
      {"action": _s("add, forget или list", enum=["add", "forget", "list"]),
       "text": _s("Факт в законченной форме, например «любимый жанр кино — фантастика»")},
      ["action"], fast=True)
def _remember(a):
    from . import notes
    return notes.remember_tool(a.get("action"), a.get("text"))


# ------------------------------ компьютер ------------------------------
@tool("clipboard", "Буфер обмена: read — прочитать скопированный текст (чтобы объяснить, перевести, пересказать), "
                   "write — скопировать текст в буфер.",
      {"action": _s("read или write", enum=["read", "write"]), "text": _s("Что скопировать (для write)")},
      ["action"], fast=True)
def _clipboard(a):
    from . import pc
    return pc.clipboard(a.get("action"), a.get("text"))


@tool("look_at_screen", "Сделать снимок экрана и ответить на вопрос о том, что на нём (ошибка, окно, текст). "
                        "Только когда пользователь просит посмотреть на экран.",
      {"question": _s("Что именно нужно выяснить по экрану")}, ["question"], status="Смотрю на экран…")
def _look(a):
    from . import pc
    return pc.look_at_screen(a.get("question"))


@tool("pc_control", "Управление компьютером: пауза/продолжить (play_pause), next, previous, stop, "
                    "громкость (volume_up, volume_down, mute, set_volume), lock, sleep, show_desktop.",
      {"action": _s("Действие", enum=["play_pause", "next", "previous", "stop", "volume_up", "volume_down",
                                      "mute", "set_volume", "lock", "sleep", "show_desktop"]),
       "value": {"type": "number", "description": "Для set_volume — уровень 0-100; для volume_up/down — на сколько процентов (по умолчанию 10)"}},
      ["action"], fast=True)
def _pc_control(a):
    from . import pc
    return pc.pc_control(a.get("action"), a.get("value"))


@tool("open_target", "Открыть программу (калькулятор, блокнот, хром...), папку (загрузки, документы), сайт (ютуб, гугл...) "
                     "или ссылку. С query сразу ищет на сайте: target=ютуб, query=ролики про пайтон.",
      {"target": _s("Название программы, папки, сайта или ссылка"),
       "query": _s("Поисковый запрос, если нужно искать на сайте")}, ["target"], fast=True)
def _open(a):
    from . import pc
    return pc.open_target(a.get("target"), a.get("query"))


@tool("system_status", "Состояние компьютера: загрузка процессора, память, диски, видеокарта, батарея, аптайм.",
      fast=True)
def _status(a):
    from . import pc
    return pc.system_status()


# ------------------------------ публичный интерфейс ------------------------------
_DISABLED = set(settings.get("DISABLED_TOOLS") or [])
TOOLS = [v["schema"] for k, v in _REG.items() if k not in _DISABLED]
STATUS = {k: v["status"] for k, v in _REG.items()}
FAST_TOOLS = {k for k, v in _REG.items() if v["fast"]}


def run_tool(name, args):
    t0 = time.time()
    ent = _REG.get(name)
    if ent is None or name in _DISABLED:
        res = "Неизвестный инструмент."
    else:
        try:
            res = str(ent["fn"](args if isinstance(args, dict) else {}))
        except Exception as e:
            res = f"Ошибка инструмента: {e}"
    log(f"Инструмент {name} {str(args)[:150]} -> {time.time() - t0:.1f} с")
    return res[:MAX_RESULT]
