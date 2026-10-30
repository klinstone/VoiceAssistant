# -*- coding: utf-8 -*-
"""Клиент OpenRouter (общий для основной модели и модели «зрения»)."""
import os

from . import config as cfg


# заготовки из .env.example и подобные: настоящий ключ OpenRouter выглядит как sk-or-v1-<шестнадцатеричная строка>
_PLACEHOLDERS = ("ваш_ключ", "api-key", "your_key", "your-key", "xxxx")


def read_key():
    """Ключ OpenRouter из .env или пустая строка, если его нет или там заготовка из .env.example."""
    from dotenv import load_dotenv
    load_dotenv(cfg.BASE / ".env", override=True)
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    return "" if not key or any(p in key.lower() for p in _PLACEHOLDERS) else key


def has_key():
    return bool(read_key())


def make_client(timeout=40):
    from openai import OpenAI
    key = read_key()
    if not key:
        raise RuntimeError("В файле .env не найден настоящий OPENROUTER_API_KEY.")
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key, timeout=timeout)
