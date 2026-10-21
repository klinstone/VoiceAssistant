# -*- coding: utf-8 -*-
"""Интерфейс на PySide6: окно чата, окно настроек, иконка в трее.
Снаружи нужны только UiApp и Services (см. app.py)."""
from .app import Services, UiApp

__all__ = ["Services", "UiApp"]
