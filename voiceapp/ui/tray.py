# -*- coding: utf-8 -*-
"""Иконка в системном трее: состояние голосовой части цветом, меню, уведомления."""
from PySide6.QtCore import QObject, Slot
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


class TrayIcon(QObject):
    def __init__(self, ui):
        super().__init__()
        self.ui = ui
        self.available = QSystemTrayIcon.isSystemTrayAvailable()
        self.icon = QSystemTrayIcon(ui.icon("idle"))
        self.icon.setToolTip("Ассистент: загрузка")
        sv = ui.services
        self.menu = QMenu()
        self.menu.addAction(self._action("Открыть чат", ui.open_chat, bold=True))
        self.menu.addAction(self._action("Новая сессия", lambda: sv.brain.new_session(wait=False)))
        if sv.silence:
            self.menu.addAction(self._action("Остановить звук", sv.silence))
        self.menu.addSeparator()
        self.menu.addAction(self._action("Настройки", lambda: ui.open_settings()))
        self.menu.addSeparator()
        self.menu.addAction(self._action("Выход", ui.quit))
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._activated)
        ui.bridge.state.connect(self.on_state)
        ui.bridge.notify.connect(self.on_notify)

    def _action(self, text, fn, bold=False):
        a = QAction(text, self.menu)
        a.triggered.connect(lambda _checked=False: fn())
        if bold:
            f = a.font()
            f.setBold(True)
            a.setFont(f)
        return a

    def _activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.ui.open_chat()

    def show(self):
        if self.available:
            self.icon.show()

    def hide(self):
        self.icon.hide()

    @Slot(str, str)
    def on_state(self, state, text):
        self.icon.setIcon(self.ui.icon(state))
        self.icon.setToolTip(f"Ассистент: {text}"[:120])

    @Slot(str, str)
    def on_notify(self, title, text):
        if self.available:
            self.icon.showMessage(title, text[:250], QSystemTrayIcon.Information, 6000)
