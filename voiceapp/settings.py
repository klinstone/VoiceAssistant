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
}


def get(name):
    return getattr(_cfg, name, _DEFAULTS[name])
