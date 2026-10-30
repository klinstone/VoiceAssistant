# -*- coding: utf-8 -*-
"""Мост: события из voiceapp.bus (приходят из любых потоков) превращаются в сигналы Qt,
которые безопасно доходят до окон в главном потоке."""
from PySide6.QtCore import QObject, Signal

from .. import bus


class Bridge(QObject):
    user_message = Signal(int, str, str)        # turn, text, src
    assistant_start = Signal(int, str)          # turn, src
    token = Signal(int, str)                    # turn, весь текст ответа на данный момент
    status = Signal(int, str)                   # turn, текст статуса
    done = Signal(int, str)                     # turn, итоговый текст
    error = Signal(int, str)                    # turn, сообщение
    session_changed = Signal(str)               # путь к активному диалогу
    sessions_updated = Signal()
    voice_partial = Signal(str)
    state = Signal(str, str)                    # состояние, подпись
    notify = Signal(str, str)                   # заголовок, текст
    open_settings = Signal(str, str)            # страница, ключ настройки (куда поставить курсор)

    def __init__(self):
        super().__init__()
        s = bus.subscribe
        s(bus.USER_MESSAGE, lambda turn, text, src: self.user_message.emit(turn, text, src))
        s(bus.ASSISTANT_START, lambda turn, src: self.assistant_start.emit(turn, src))
        s(bus.TOKEN, lambda turn, delta, full: self.token.emit(turn, full))
        s(bus.STATUS, lambda turn, text: self.status.emit(turn, text))
        s(bus.ASSISTANT_DONE, lambda turn, text: self.done.emit(turn, text))
        s(bus.ASSISTANT_ERROR, lambda turn, message: self.error.emit(turn, message))
        s(bus.SESSION_CHANGED, lambda path: self.session_changed.emit(path))
        s(bus.SESSIONS_UPDATED, lambda: self.sessions_updated.emit())
        s(bus.VOICE_PARTIAL, lambda text: self.voice_partial.emit(text))
        s(bus.STATE, lambda state, text: self.state.emit(state, text))
        s(bus.NOTIFY, lambda title, text: self.notify.emit(title, text))
        s(bus.OPEN_SETTINGS, lambda page, focus: self.open_settings.emit(page, focus))
