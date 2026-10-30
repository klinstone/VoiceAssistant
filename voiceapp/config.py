# -*- coding: utf-8 -*-
"""Все настройки ассистента. Меняйте значения здесь.
Окно «Настройки» хранит свои изменения в data/settings.json: при запуске они накладываются поверх значений из этого файла
(см. блок «служебное» в самом конце)."""
import copy
import json
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
REASONING_EFFORT = "low"   # "low" | "high" | "max" | None (не передавать)
MAX_TOOL_CALLS = 3         # макс. обращений к поиску/погоде/курсам за один ответ
HISTORY_MESSAGES = 30      # сколько последних реплик помнить (одно число и для голоса, и для чата)
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


# ======================================================================================================
# Служебное: пользовательские настройки (data/settings.json). Ниже ничего менять не нужно.
# ======================================================================================================
# Значения по умолчанию запоминаем ДО наложения пользовательских: по ним окно «Настройки» умеет сбрасывать значения
# (settings.default). Пути (BASE, CACHE...) настройками не являются.
DEFAULTS = {k: copy.deepcopy(v) for k, v in list(globals().items()) if k.isupper() and not isinstance(v, Path)}
USER_SETTINGS_FILE = BASE / "data" / "settings.json"

_NULLABLE = {"REASONING_EFFORT", "MIC_DEVICE", "VISION_MODEL"}      # для этих настроек None — осмысленное значение
_PROTECTED = {"DEFAULTS", "USER_SETTINGS_FILE"}


def _same_kind(name, value, default):
    """Подходит ли значение из settings.json по типу к умолчанию (испорченный файл не должен ронять запуск)."""
    if value is None:
        return default is None or name in _NULLABLE
    if default is None:                                  # например MIC_DEVICE: номер или часть названия
        return isinstance(value, (int, str)) and not isinstance(value, bool)
    if isinstance(default, bool) or isinstance(value, bool):
        return isinstance(default, bool) and isinstance(value, bool)
    if isinstance(default, (int, float)):
        return isinstance(value, (int, float))
    if isinstance(default, (list, tuple)):
        return isinstance(value, list)
    if isinstance(default, dict):
        return isinstance(value, dict)
    if isinstance(default, str):
        return isinstance(value, str)
    return True


def _load_user_settings():
    """Накладывает data/settings.json на значения выше. Ключи, которых нет в этом файле (CONTEXT_TIMEOUT_MIN и другие,
    описанные в settings._DEFAULTS), тоже применяются: settings.get() ищет их здесь в первую очередь."""
    try:
        with open(USER_SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return
    if not isinstance(data, dict):
        return
    for name, value in data.items():
        if not (isinstance(name, str) and name.isidentifier() and name.isupper()) or name in _PROTECTED:
            continue
        if isinstance(globals().get(name), Path):
            continue
        if name in DEFAULTS and not _same_kind(name, value, DEFAULTS[name]):
            continue
        globals()[name] = value


_load_user_settings()
