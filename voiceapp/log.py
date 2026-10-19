# -*- coding: utf-8 -*-
"""Вывод в консоль. Под pythonw (без консоли) вывод уходит в assistant.log."""
import sys
import time
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent

if sys.stdout is None or sys.stderr is None:
    _f = open(_BASE / "assistant.log", "a", encoding="utf-8", buffering=1)
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
