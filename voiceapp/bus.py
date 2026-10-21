# -*- coding: utf-8 -*-
"""Шина событий между ядром (голос, модель) и интерфейсом.
Ядро только вызывает emit(...) и ничего не знает о том, кто слушает; интерфейс подписывается через subscribe(...).
Обработчики вызываются в потоке, который сделал emit, поэтому в интерфейсе их нужно перекладывать в свой поток.

События (имя: поля):
  USER_MESSAGE     turn, text, src          — началась обработка реплики пользователя (src: "voice" | "text")
  ASSISTANT_START  turn, src                — модель начала отвечать
  TOKEN            turn, delta, full        — очередной кусок ответа; full — весь текст ответа на данный момент
  STATUS           turn, text               — модель вызывает инструмент («Ищу в интернете…»)
  ASSISTANT_DONE   turn, text               — ответ готов и сохранён
  ASSISTANT_ERROR  turn, message            — запрос не удался
  SESSION_CHANGED  path                     — сменился активный диалог (новый, выбранный, удалённый)
  SESSIONS_UPDATED                          — изменился список диалогов (новая реплика, удаление)
  VOICE_PARTIAL    text                     — то, что вы говорите, пока идёт запись ("" = запись закончена)
  STATE            state, text              — состояние голосовой части: idle/ready/listening/thinking/speaking/error
  NOTIFY           title, text              — показать уведомление (сработал таймер)
"""
import threading
import traceback

USER_MESSAGE = "user_message"
ASSISTANT_START = "assistant_start"
TOKEN = "token"
STATUS = "status"
ASSISTANT_DONE = "assistant_done"
ASSISTANT_ERROR = "assistant_error"
SESSION_CHANGED = "session_changed"
SESSIONS_UPDATED = "sessions_updated"
VOICE_PARTIAL = "voice_partial"
STATE = "state"
NOTIFY = "notify"

_REMEMBER = {STATE}          # для этих событий хранится последнее значение (окно, открытое позже, узнает состояние)
_subs = {}
_last = {}
_lock = threading.Lock()


def subscribe(event, fn):
    """fn(**поля_события). Возвращает fn (удобно для декоратора)."""
    with _lock:
        _subs.setdefault(event, []).append(fn)
    return fn


def unsubscribe(event, fn):
    with _lock:
        if fn in _subs.get(event, []):
            _subs[event].remove(fn)


def emit(event, **data):
    if event in _REMEMBER:
        _last[event] = data
    with _lock:
        handlers = list(_subs.get(event, []))
    for fn in handlers:
        try:
            fn(**data)
        except Exception:
            traceback.print_exc()


def last(event):
    """Поля последнего события из числа запоминаемых (сейчас только STATE) или None."""
    return _last.get(event)
