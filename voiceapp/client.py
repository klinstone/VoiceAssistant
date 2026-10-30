# -*- coding: utf-8 -*-
"""Клиент OpenRouter (общий для основной модели и модели «зрения»)."""
import os

from . import config as cfg


# заготовки из .env.example и подобные: настоящий ключ OpenRouter выглядит как sk-or-v1-<шестнадцатеричная строка>
_PLACEHOLDERS = ("ваш_ключ", "api-key", "your_key", "your-key", "xxxx")


def make_client(timeout=40):
    from dotenv import load_dotenv
    from openai import OpenAI
    load_dotenv(cfg.BASE / ".env", override=True)
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key or any(p in key.lower() for p in _PLACEHOLDERS):
        raise RuntimeError("В файле .env не найден настоящий OPENROUTER_API_KEY.")
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key, timeout=timeout)
