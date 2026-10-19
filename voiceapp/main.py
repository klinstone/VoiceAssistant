# -*- coding: utf-8 -*-
"""Точка входа: разбор аргументов, трей, запуск."""
import argparse
import threading
import warnings

from .log import log  # noqa: E402  (импортируется первым: настраивает вывод)
from . import config as cfg

warnings.filterwarnings("ignore", category=SyntaxWarning)  # шум из внутренностей модели Silero


def _single_instance():
    import socket
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", 47653))
    except OSError:
        return None
    return s


def _open_chat():
    from .chat_gui import open_chat
    open_chat()


def main():
    from .core import Assistant
    ap = argparse.ArgumentParser()
    ap.add_argument("--devices", action="store_true", help="список аудиоустройств")
    ap.add_argument("--say", metavar="ТЕКСТ", help="проверка голоса")
    ap.add_argument("--listen", action="store_true", help="проверка микрофона и распознавания")
    ap.add_argument("--chat", action="store_true", help="только текстовый чат (без голоса)")
    ap.add_argument("--no-tray", action="store_true", help="без иконки в трее")
    args = ap.parse_args()

    if args.devices:
        import sounddevice as sd
        print(sd.query_devices())
        return
    if args.chat:
        from .chat_gui import run_standalone
        run_standalone()
        return

    stop = threading.Event()
    tray = None
    a = Assistant(stop)

    if args.say:
        a.load(llm=False)
        a.speaker.say(args.say)
        a.speaker.wait()
        return
    if args.listen:
        a.load(llm=False)
        a.listen_once()
        return

    lock = _single_instance()                       # защита от двойного запуска
    if lock is None:
        log("Ассистент уже запущен.")
        return

    def on_quit():
        stop.set()
        if tray:
            tray.stop()

    if cfg.USE_TRAY and not args.no_tray:
        try:
            from .tray import Tray
            tray = Tray(on_quit, a.reset_session, _open_chat)
            a.tray = tray
        except Exception as e:
            log(f"Трей недоступен ({e}), работаю в консоли.")
            tray = None

    if tray:
        threading.Thread(target=a.run_safe, daemon=True).start()
        tray.run()
    else:
        try:
            a.run_safe()
        except KeyboardInterrupt:
            pass
