# -*- coding: utf-8 -*-
"""Мелкие общие виджеты и помощники."""
import os
import subprocess
import sys

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import QAbstractButton, QComboBox, QDoubleSpinBox, QSpinBox

from . import theme


class Switch(QAbstractButton):
    """Переключатель вкл/выкл."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(40, 22)

    def sizeHint(self):
        return QSize(40, 22)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.isChecked()
        track = self.palette().color(QPalette.Highlight) if on else QColor(theme.C["border"])
        if not self.isEnabled():
            track = QColor(theme.C["sel"])
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(0, 1, 40, 20, 10, 10)
        p.setBrush(QColor("#ffffff" if on else theme.C["muted"]))
        p.drawEllipse(21 if on else 3, 4, 14, 14)


class RoundButton(QAbstractButton):
    """Круглая кнопка отправки / остановки."""

    def __init__(self, kind="send", parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(40, 40)
        self.setCursor(Qt.PointingHandCursor)

    def set_kind(self, kind):
        self.kind = kind
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        base = self.palette().color(QPalette.Highlight)
        if not self.isEnabled():
            base = QColor(theme.C["sel"])
        elif self.underMouse():
            base = base.lighter(112)
        p.setPen(Qt.NoPen)
        p.setBrush(base)
        p.drawEllipse(self.rect().adjusted(1, 1, -1, -1))
        fg = QColor("#ffffff" if self.isEnabled() else theme.C["muted"])
        if self.kind == "stop":
            p.setBrush(fg)
            p.drawRoundedRect(14, 14, 12, 12, 3, 3)
        else:
            pen = QPen(fg, 2.4)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            path = QPainterPath()
            path.moveTo(20, 27)
            path.lineTo(20, 13.5)
            path.moveTo(13.5, 19.5)
            path.lineTo(20, 13)
            path.lineTo(26.5, 19.5)
            p.drawPath(path)


class _NoWheel:
    """Прокрутка колёсиком над полем не меняет значение, пока поле не в фокусе (иначе страница настроек «убегает»)."""

    def wheelEvent(self, e):
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()


class IntSpin(_NoWheel, QSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumWidth(130)


class FloatSpin(_NoWheel, QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumWidth(130)


class Combo(_NoWheel, QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumWidth(220)


# ------------------------------ файлы и папки ------------------------------
def open_path(path):
    """Открыть файл или папку программой по умолчанию."""
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def reveal(path):
    """Показать файл в папке (в проводнике файл будет выделен)."""
    path = str(path)
    if sys.platform == "win32" and os.path.exists(path):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        open_path(os.path.dirname(path) if os.path.isfile(path) else path)
