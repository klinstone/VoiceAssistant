# -*- coding: utf-8 -*-
"""Мелкие значки для QSS (стрелки списков, галочка): рисуются при запуске во временную папку,
потому что QSS умеет подключать только файлы."""
import tempfile
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap


def _poly(p, pts):
    p.drawPolyline([QPointF(x, y) for x, y in pts])


def _draw(path, size, painter_fn):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    painter_fn(p, size)
    p.end()
    pm.save(str(path), "PNG")


def ensure_icons(arrow_color="#aab1c3"):
    """Возвращает {имя: путь с прямыми слэшами} для подстановки в QSS."""
    d = Path(tempfile.gettempdir()) / "voiceapp_ui"
    d.mkdir(parents=True, exist_ok=True)

    def pen(color, w):
        p = QPen(QColor(color), w)
        p.setCapStyle(Qt.RoundCap)
        p.setJoinStyle(Qt.RoundJoin)
        return p

    def down(p, s):
        p.setPen(pen(arrow_color, 1.8))
        _poly(p, [(s * .25, s * .38), (s * .5, s * .64), (s * .75, s * .38)])

    def up(p, s):
        p.setPen(pen(arrow_color, 1.8))
        _poly(p, [(s * .25, s * .62), (s * .5, s * .36), (s * .75, s * .62)])

    def check(p, s):
        p.setPen(pen("#ffffff", 2.0))
        _poly(p, [(s * .24, s * .52), (s * .43, s * .70), (s * .77, s * .30)])

    files = {"down": ("arrow_down.png", down), "up": ("arrow_up.png", up), "check": ("check.png", check)}
    out = {}
    for key, (name, fn) in files.items():
        path = d / name
        _draw(path, 16, fn)
        out[key] = path.as_posix()
    return out
