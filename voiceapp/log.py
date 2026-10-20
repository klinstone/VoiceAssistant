# -*- coding: utf-8 -*-
"""Вывод в консоль. Под pythonw (без консоли) вывод уходит в assistant.log."""
import os
import sys
import time
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
_LOG_MAX = 5 * 1024 * 1024        # больше 5 МБ: старый лог переименовывается в assistant.log.old

if sys.stdout is None or sys.stderr is None:
    _path = _BASE / "assistant.log"
    try:
        if _path.exists() and _path.stat().st_size > _LOG_MAX:
            os.replace(_path, _BASE / "assistant.log.old")
    except OSError:
        pass
    _f = open(_path, "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = _f
    if sys.stderr is None:
        sys.stderr = _f
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)
