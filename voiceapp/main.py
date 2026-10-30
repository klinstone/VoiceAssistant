# -*- coding: utf-8 -*-
"""Точка входа: разбор аргументов, интерфейс (окно + трей), запуск голосовой части."""
import argparse
import json
import os
import sys
import threading
import time
import warnings

from .log import log  # noqa: E402  (импортируется первым: настраивает вывод)
from . import config as cfg

warnings.filterwarnings("ignore", category=SyntaxWarning)  # шум из внутренностей модели Silero


def _single_instance(wait=0.0):
    """Занимает порт-замок. wait: сколько секунд ждать, пока старый экземпляр (при перезапуске) отпустит порт."""
    import socket
    deadline = time.time() + wait
    while True:
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", 47653))
            return s
        except OSError:
            s.close()
            if time.time() >= deadline:
                return None
            time.sleep(0.3)


def _restart_process():
    """Запустить копию программы. Новый экземпляр сам дождётся, пока старый выйдет (VOICEAPP_RESTARTED)."""
    import subprocess
    env = dict(os.environ, VOICEAPP_RESTARTED="1")
    flags = 0x08000000 if sys.platform == "win32" else 0          # CREATE_NO_WINDOW
    subprocess.Popen([sys.executable, os.path.abspath(sys.argv[0]), *sys.argv[1:]],
                     env=env, cwd=str(cfg.BASE), creationflags=flags, close_fds=True)


def _run_tool_cli(parts):
    """python assistant.py --tool get_weather city=Рига   |   --tool timer '{"seconds": 5, "label": "тест"}'
    python assistant.py --tool list  — показать все инструменты."""
    from .tools import TOOLS, run_tool
    name = parts[0]
    if name == "list":
        for t in TOOLS:
            print(f"{t['function']['name']}: {t['function']['description'][:90]}")
        return
    rest = " ".join(parts[1:]).strip()
    if rest.startswith("{"):
        args = json.loads(rest)
    else:
        args = {}
        for p in parts[1:]:
            k, _, v = p.partition("=")
            args[k] = float(v) if v.replace(".", "", 1).isdigit() else v
    print(run_tool(name, args))
    if name == "timer" and args.get("action", "set") == "set":
        from .reminders import SCHEDULER
        print("Жду срабатывания (до 60 с)...")
        for _ in range(120):
            if not SCHEDULER.items():
                break
            time.sleep(0.5)
        time.sleep(4)


def main():
    from .core import Assistant
    ap = argparse.ArgumentParser()
    ap.add_argument("--devices", action="store_true", help="список аудиоустройств")
    ap.add_argument("--say", metavar="ТЕКСТ", help="проверка голоса")
    ap.add_argument("--listen", action="store_true", help="проверка микрофона и распознавания")
    ap.add_argument("--chat", action="store_true", help="только окно чата (без голоса)")
    ap.add_argument("--no-tray", action="store_true", help="без окна и иконки в трее (только консоль)")
    ap.add_argument("--tool", nargs="+", metavar="ИМЯ [арг=знач ...]",
                    help="вызвать инструмент без голоса и модели (для проверки); --tool list — список")
    args = ap.parse_args()

    if args.devices:
        import sounddevice as sd
        print(sd.query_devices())
        return
    if args.tool:
        _run_tool_cli(args.tool)
        return

    stop = threading.Event()
    if args.say:
        a = Assistant(stop)
        a.load(llm=False, stt=False)            # для озвучки нужен только голос
        a.speaker.say(args.say)
        a.speaker.wait()
        return
    if args.listen:
        a = Assistant(stop)
        a.load(llm=False, tts=False)            # для проверки микрофона голос не нужен
        a.listen_once()
        return

    lock = None
    if not args.chat:                                   # защита от двойного запуска
        lock = _single_instance(wait=20 if os.environ.get("VOICEAPP_RESTARTED") else 0)
        if lock is None:
            log("Ассистент уже запущен.")
            return

    from .llm import Brain
    brain = Brain()                                     # один мозг на голос и окно чата
    assistant = None if args.chat else Assistant(stop, brain=brain)

    use_ui = args.chat or (cfg.USE_TRAY and not args.no_tray)
    ui = None
    if use_ui:
        try:
            from .ui import Services, UiApp
            ui = UiApp(Services(
                brain=brain,
                quit=stop.set,
                restart=_restart_process,
                silence=(lambda: assistant.silence(cancel=True)) if assistant else None,
                reset_session=brain.new_session,
                preview_voice=assistant.preview_voice if assistant else None,
                voice=assistant is not None,
            ), standalone=args.chat)
        except Exception as e:
            log(f"Интерфейс недоступен ({type(e).__name__}: {e}). Установите: pip install PySide6-Essentials")
            if args.chat:
                return

    if ui:
        if assistant:
            threading.Thread(target=assistant.run_safe, daemon=True, name="voice").start()
        restart = ui.run(show_chat=args.chat)           # блокирует до выхода из программы
        stop.set()
        if restart:
            os._exit(0)                                 # гарантированно освободить порт для нового экземпляра
    else:
        try:
            assistant.run_safe()
        except KeyboardInterrupt:
            pass
