# -*- coding: utf-8 -*-
"""Настройки, которых нет в config.py (значения по умолчанию) и хранилище пользовательских значений.
Порядок такой: значения из config.py / _DEFAULTS ниже -> поверх них то, что сохранено в data/settings.json.
Окно «Настройки» пишет сюда через save(): изменения применяются сразу, а при следующем запуске
config.py сам подхватит data/settings.json. Ключ OpenRouter лежит отдельно, в .env (env_get / env_set)."""
import copy
import json
import os

from . import config as _cfg

_DEFAULTS = {
    "CONTEXT_TIMEOUT_MIN": 10,                     # через сколько минут тишины голос начинает новый диалог (0 = никогда)
    "SESSIONS_DIR": _cfg.BASE / "sessions",        # куда сохраняются диалоги
    "WAKE_SPLIT_WORDS": True,                      # добавлять в грамматику Vosk отдельные слова фразы
    "WAKE_CARRY_ON": True,                         # вопрос можно говорить сразу после кодовой фразы, без паузы
    "WAKE_MIN_CONF": 0.0,                          # мин. уверенность Vosk для кодового слова (0 = выключено)

    # ---- модель ----
    "LLM_TEMPERATURE": 0.7,                        # «креативность» ответов
    "LLM_MAX_TOKENS": 1500,                        # максимальная длина одного ответа
    "EXTRA_PROMPT": "",                            # ваши дополнительные инструкции модели (добавляются к системному промпту)

    # ---- инструменты ----
    "DATA_DIR": _cfg.BASE / "data",                # заметки, память и таймеры (переживают перезапуск)
    "DISABLED_TOOLS": [],                          # имена инструментов, которые не показывать модели
    "SEARCH_REGION": "wt-wt",                      # регион веб-поиска
    "SEARCH_RESULTS": 5,                           # сколько результатов поиска отдавать модели
    "PAGE_MAX_CHARS": 8000,                        # сколько символов страницы отдавать модели
    "VISION_MODEL": "google/gemini-2.5-flash",     # модель для «посмотри на экран» (None = LLM_MODEL)
    "SCREEN_MAX_SIDE": 1600,                       # скриншот сжимается до такой длинной стороны, px
    "SCREEN_ALL_MONITORS": False,                  # снимать все мониторы сразу (иначе только основной)
    "ALARM_REPEATS": 1,                            # сколько раз повторять сигнал таймера
    "ALARM_GAP": 12,                               # пауза между повторами, сек
    "APPS": {},                                    # свои программы: {"телеграм": r"C:\...\Telegram.exe"}
    "SITES": {},                                   # свои сайты: {"почта": "https://...", "пикабу": "https://.../search?q={q}"}

    # ---- интерфейс ----
    "UI_ACCENT": "Синий",                          # акцентный цвет окна
    "UI_FONT_SIZE": 10,                            # размер шрифта, pt
    "UI_OPEN_ON_START": False,                     # открывать окно чата при запуске
}

ENV_FILE = _cfg.BASE / ".env"


def get(name):
    return getattr(_cfg, name, _DEFAULTS.get(name))


def default(name):
    """Значение по умолчанию (без учёта data/settings.json). Всегда копия: списки и словари нельзя испортить на месте."""
    if name in _cfg.DEFAULTS:
        return copy.deepcopy(_cfg.DEFAULTS[name])
    return copy.deepcopy(_DEFAULTS.get(name))


def _sanitize():
    """config.py проверяет по типу только свои ключи. Здесь то же для ключей из _DEFAULTS: значение из settings.json,
    которое не подходит по типу (файл правили руками), заменяется умолчанием, а не роняет программу позже."""
    for name, dflt in _DEFAULTS.items():
        if name in vars(_cfg) and name not in _cfg.DEFAULTS and not _cfg._same_kind(name, getattr(_cfg, name), dflt):
            setattr(_cfg, name, copy.deepcopy(dflt))


_sanitize()


# ------------------------------ data/settings.json ------------------------------
def user_values():
    """Что сейчас сохранено пользователем (только отличия от умолчаний)."""
    try:
        with open(_cfg.USER_SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(data):
    p = _cfg.USER_SETTINGS_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def save(changes):
    """Сохранить {имя: значение} в data/settings.json и сразу применить в работающей программе."""
    current = user_values()
    for name, value in changes.items():
        if value == default(name):
            current.pop(name, None)
        else:
            current[name] = value
        setattr(_cfg, name, value)
    _write(current)


def reset(names=None):
    """Вернуть значения по умолчанию (всем настройкам, если names не указан)."""
    names = list(names) if names is not None else list(user_values())
    save({n: default(n) for n in names})


# ------------------------------ .env (секреты) ------------------------------
def env_get(name):
    try:
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            key, sep, val = line.partition("=")
            if sep and key.strip() == name:
                return val.strip().strip("\"'")
    except OSError:
        pass
    return os.getenv(name, "")


def env_set(name, value):
    """Записать значение в .env (остальные строки не трогаем) и в окружение процесса."""
    value = (value or "").strip()
    try:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    out, done = [], False
    for line in lines:
        if line.partition("=")[0].strip() == name and "=" in line:
            out.append(f"{name}={value}")
            done = True
        else:
            out.append(line)
    if not done:
        out.append(f"{name}={value}")
    ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.environ[name] = value
