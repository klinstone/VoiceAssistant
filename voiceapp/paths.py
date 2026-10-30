# -*- coding: utf-8 -*-
"""Где лежат данные программы: рядом с исходниками или (в exe) рядом с .exe."""
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
BASE = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent.parent
