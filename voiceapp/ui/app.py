# -*- coding: utf-8 -*-
"""Qt-приложение: окна, трей, тема. Всё, что нужно от остальной программы, приходит через Services."""
import base64
import json
import sys
from dataclasses import dataclass
from typing import Callable, Optional

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import QApplication

from .. import bus, settings
from . import theme
from .bridge import Bridge
from .icons import ensure_icons
from .tray import TrayIcon


@dataclass
class Services:
    """Что интерфейсу нужно от ядра. Больше интерфейс ни о чём в программе не знает."""
    brain: object                                   # voiceapp.llm.Brain
    quit: Callable                                  # остановить голосовую часть
    restart: Optional[Callable] = None              # запустить новую копию программы (перед выходом)
    silence: Optional[Callable] = None              # остановить озвучку и ответ
    reset_session: Optional[Callable] = None
    preview_voice: Optional[Callable] = None        # (текст, диктор): проверка голоса в настройках
    voice: bool = True                              # есть ли голосовая часть (False для --chat)


class UiApp:
    def __init__(self, services, standalone=False):
        self.services, self.standalone = services, standalone
        self.app = QApplication.instance() or QApplication(sys.argv[:1])
        self.app.setApplicationName("Ассистент")
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setStyle("Fusion")
        try:                                        # тёмная рамка окна в Windows (Qt 6.8+)
            self.app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
        except Exception:
            pass
        self.bridge = Bridge()
        self.chat = self.settings_win = None
        self.pending_restart = False
        self._restart = False
        self._icons = {}
        self.apply_theme()
        self.tray = TrayIcon(self)

    # ------------------------------ тема ------------------------------
    def apply_theme(self):
        accent = theme.accent_of(settings.get("UI_ACCENT"))
        size = int(settings.get("UI_FONT_SIZE") or 10)
        self.app.setFont(QFont("Segoe UI", size))
        pal = QPalette()
        c = lambda k: QColor(theme.C[k])
        pal.setColor(QPalette.Window, c("bg"))
        pal.setColor(QPalette.WindowText, c("text"))
        pal.setColor(QPalette.Base, c("panel"))
        pal.setColor(QPalette.AlternateBase, c("side"))
        pal.setColor(QPalette.Text, c("text"))
        pal.setColor(QPalette.Button, c("panel"))
        pal.setColor(QPalette.ButtonText, c("text"))
        pal.setColor(QPalette.ToolTipBase, c("panel"))
        pal.setColor(QPalette.ToolTipText, c("text"))
        pal.setColor(QPalette.PlaceholderText, c("muted"))
        pal.setColor(QPalette.Link, c("link"))
        pal.setColor(QPalette.Highlight, QColor(accent))
        pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        self.app.setPalette(pal)
        self.app.setStyleSheet(theme.build_qss(settings.get("UI_ACCENT"), size, ensure_icons()))
        for w in (self.chat, self.settings_win):
            if w is not None:
                w.update()

    def settings_saved(self, keys):
        if any(k.startswith("UI_") for k in keys):
            self.apply_theme()
            if self.chat is not None:
                self.chat.view.fit_all()

    # ------------------------------ иконки ------------------------------
    def icon(self, state):
        if state not in self._icons:
            pm = QPixmap(64, 64)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.STATE_COLORS.get(state, theme.STATE_COLORS["idle"])))
            p.drawEllipse(4, 4, 56, 56)
            p.setBrush(QColor(255, 255, 255, 235))
            for x, h in ((20, 14), (28, 26), (36, 20)):         # три «столбика» голоса
                p.drawRoundedRect(x, 32 - h // 2, 6, h, 3, 3)
            p.end()
            self._icons[state] = QIcon(pm)
        return self._icons[state]

    def last_state(self):
        d = bus.last(bus.STATE)
        return (d["state"], d["text"]) if d else None

    # ------------------------------ состояние окон ------------------------------
    def _state_file(self):
        return settings.get("DATA_DIR") / "ui_state.json"

    def restore_geometry(self, win, name):
        try:
            data = json.loads(self._state_file().read_text(encoding="utf-8"))
            win.restoreGeometry(QByteArray(base64.b64decode(data[name])))
        except Exception:
            pass

    def remember_geometry(self, win, name):
        try:
            f = self._state_file()
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                data = {}
            data[name] = base64.b64encode(bytes(win.saveGeometry())).decode()
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass

    # ------------------------------ окна ------------------------------
    def _front(self, win):
        win.showNormal()
        win.raise_()
        win.activateWindow()

    def open_chat(self):
        if self.chat is None:
            from .chat_window import ChatWindow
            self.chat = ChatWindow(self)
            self.restore_geometry(self.chat, "chat")
        self._front(self.chat)

    def open_settings(self, page=None):
        if self.settings_win is None:
            from .settings_window import SettingsWindow
            self.settings_win = SettingsWindow(self)
            self.restore_geometry(self.settings_win, "settings")
        if page:
            self.settings_win.select_page(page)
        self._front(self.settings_win)

    # ------------------------------ жизненный цикл ------------------------------
    def quit(self):
        for w, n in ((self.chat, "chat"), (self.settings_win, "settings")):
            if w is not None:
                self.remember_geometry(w, n)
        self.services.quit()
        self.tray.hide()
        self.app.quit()

    def restart(self):
        self._restart = True
        if self.services.restart:
            self.services.restart()
        self.quit()

    def run(self, show_chat=False):
        """Блокирует до выхода. Возвращает True, если нужно перезапустить программу."""
        self.tray.show()
        if show_chat or settings.get("UI_OPEN_ON_START") or not self.tray.available:
            QTimer.singleShot(0, self.open_chat)
        self.app.exec()
        return self._restart
