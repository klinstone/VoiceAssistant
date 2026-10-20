# -*- coding: utf-8 -*-
"""Новые настройки со значениями по умолчанию.
Чтобы изменить, допишите строку с тем же именем в config.py (например: CONTEXT_TIMEOUT_MIN = 15)."""
from . import config as _cfg

_DEFAULTS = {
    "CONTEXT_TIMEOUT_MIN": 10,                     # через сколько минут тишины начинать новый диалог (0 = никогда)
    "SESSIONS_DIR": _cfg.BASE / "sessions",        # куда сохраняются диалоги
    "CHAT_HISTORY_MESSAGES": 40,                   # сколько последних реплик помнит текстовый чат
    "WAKE_SPLIT_WORDS": True,                      # добавлять в грамматику Vosk отдельные слова фразы
    "WAKE_CARRY_ON": True,                         # вопрос можно говорить сразу после кодовой фразы, без паузы
    "WAKE_MIN_CONF": 0.0,                          # мин. уверенность Vosk для кодового слова (0 = выключено)

    # ---- инструменты ----
    "DATA_DIR": _cfg.BASE / "data",                # заметки, память и таймеры (переживают перезапуск)
    "DISABLED_TOOLS": [],                          # имена инструментов, которые не показывать модели
    "SEARCH_REGION": "wt-wt",                      # регион веб-поиска
    "SEARCH_RESULTS": 5,                           # сколько результатов поиска отдавать модели
    "PAGE_MAX_CHARS": 8000,                        # сколько символов страницы отдавать модели
    "VISION_MODEL": "google/gemini-2.5-flash",     # модель для «посмотри на экран» (None = LLM_MODEL)
    "SCREEN_MAX_SIDE": 1600,                       # скриншот сжимается до такой длинной стороны, px
    "SCREEN_ALL_MONITORS": False,                  # снимать все мониторы сразу (иначе только основной)
    "ALARM_REPEATS": 3,                            # сколько раз повторять сигнал таймера
    "ALARM_GAP": 12,                               # пауза между повторами, сек
    "APPS": {},                                    # свои программы: {"телеграм": r"C:\...\Telegram.exe"}
    "SITES": {},                                   # свои сайты: {"почта": "https://...", "пикабу": "https://.../search?q={q}"}
}


def get(name):
    return getattr(_cfg, name, _DEFAULTS[name])
