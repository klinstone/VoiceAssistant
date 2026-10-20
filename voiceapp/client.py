# -*- coding: utf-8 -*-
"""Клиент OpenRouter (общий для основной модели и модели «зрения»)."""
import os

from . import config as cfg


def make_client(timeout=40):
    from dotenv import load_dotenv
    from openai import OpenAI
    load_dotenv(cfg.BASE / ".env")
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key or "ваш_ключ" in key:
        raise RuntimeError("В файле .env не найден настоящий OPENROUTER_API_KEY.")
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key, timeout=timeout)
