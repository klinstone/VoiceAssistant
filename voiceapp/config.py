# -*- coding: utf-8 -*-
"""Все настройки ассистента. Меняйте значения здесь."""
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CACHE = BASE / "cache"
VOSK_DIR = BASE / "vosk_model"

# Кэш моделей держим внутри проекта (должно выставляться до импорта huggingface/torch)
os.environ.setdefault("HF_HOME", str(CACHE / "hf"))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# ---------------- кодовые слова ----------------
WAKE_PHRASE = "эй робот"                                  # строчными, по-русски
NEW_SESSION_PHRASES = ["новая сессия", "новый диалог"]    # сбрасывают контекст диалога
WAKE_VERIFY = True       # перепроверять срабатывание точной моделью (отсекает ложные тревоги)
WAKE_MATCH = 0.8         # насколько похоже должно быть распознанное на кодовое слово (0..1)
VERIFY_TAIL = 0.8        # сколько секунд дослушивать перед проверкой
IGNORE_AFTER_DIALOG = 1.0  # пауза после диалога, когда кодовое слово не ловится, сек

# ---------------- время ----------------
END_SILENCE = 1.25        # секунд тишины = конец вопроса (можно думать паузами)
NO_SPEECH_TIMEOUT = 6    # после «эй, робот» ждать начала фразы, сек
FOLLOWUP_WINDOW = 2.0   # после ответа ждать следующий вопрос без кодового слова, сек
MAX_RECORD = 25          # макс. длина одной фразы, сек (у GigaAM лимит ~20-30 с)

# ---------------- LLM ----------------
LLM_MODEL = "deepseek/deepseek-v4.1-flash-1017"
VISION_MODEL = "deepseek/deepseek-v4.1-flash-1017"
REASONING_EFFORT = "low"   # "low" | "high" | "max" | None (не передавать)
MAX_TOOL_CALLS = 3         # макс. обращений к поиску/погоде/курсам за один ответ
HISTORY_MESSAGES = 20      # сколько последних реплик помнить
DEFAULT_CITY = "Tomsk" # город для погоды, если не назван

# ---------------- голос и распознавание ----------------
SILERO_MODELS = ["v5_5_ru", "v5_ru"]   # пробуем по очереди
SPEAKER = "baya"                      # aidar, baya, kseniya, xenia, eugene
TTS_SAMPLE_RATE = 48000                # 24000 быстрее, 48000 качественнее
ASR_MODELS = [                         # пробуем по очереди; при неудаче - текст от Vosk
    "gigaam-v3-e2e-ctc",
    "gigaam-v3-ctc",
    "gigaam-v3-e2e-rnnt",
    "gigaam-v3-rnnt",
    "nemo-parakeet-tdt-0.6b-v3",
]

# ---------------- аудио ----------------
MIC_DEVICE = None        # None = по умолчанию; число или часть названия, напр. "K678"
SAMPLE_RATE = 16000
USE_TRAY = True
