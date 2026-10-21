# -*- coding: utf-8 -*-
"""Общение с моделью через OpenRouter: потоковый ответ, инструменты, история и сохранение диалогов.

Brain один на всю программу. И голос, и окно чата работают с одним и тем же активным диалогом
(brain.session). Что происходит с запросом, Brain сообщает через voiceapp.bus, а не вызывает интерфейс сам.
Источник реплики (src) решает только две вещи: какой системный промпт взять («для озвучки» или «для чтения»)
и озвучивать ли ответ (если передан speaker)."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from . import bus
from . import config as cfg
from . import sessions, settings
from .chat_prompt import build_chat_prompt
from .client import make_client
from .log import log
from .prompt import build_system_prompt
from .text_utils import Chunker
from .tools import FAST_TOOLS, STATUS, active_tools, run_tool


class _StreamPrinter:
    """Печатает ответ в консоль по мере поступления токенов (только для голосового режима)."""

    def __init__(self):
        self.on = False

    def feed(self, s):
        if not self.on:
            print(time.strftime("%H:%M:%S"), "Ассистент: ", end="", flush=True)
            self.on = True
        print(s, end="", flush=True)

    def end(self):
        if self.on:
            print(flush=True)
            self.on = False


class Brain:
    def __init__(self):
        self._client = None                 # создаётся при первом запросе: без ключа программа всё равно запускается
        self._lock = threading.RLock()      # запросы идут строго по одному (голос и окно не мешают друг другу)
        self._cancel = threading.Event()
        self._turn = 0
        self.history = []
        self.no_reasoning = False
        self.last_activity = time.time()
        self.busy = False                   # сейчас обрабатывается запрос
        self.inflight = None                # {"turn", "src", "user", "answer"} пока идёт запрос (окно могли открыть посреди ответа)
        self.session = sessions.new_session()   # активный диалог; пока в нём нет реплик, это «черновик» без файла

    # ------------------------- клиент -------------------------
    @property
    def client(self):
        if self._client is None:
            self._client = make_client(timeout=40)
        return self._client

    def reset_client(self):
        """Ключ изменился: клиент создастся заново со следующим запросом."""
        self._client = None

    # ------------------------- история и диалоги -------------------------
    @property
    def turn(self):
        """Номер последнего начатого запроса (окно по нему отличает уже показанное от нового)."""
        return self._turn

    @property
    def is_draft(self):
        """Активный диалог ещё пуст (файл появится вместе с первой репликой)."""
        return not self.session.path.exists()

    @staticmethod
    def _limit(src):
        return cfg.HISTORY_MESSAGES if src == "voice" else settings.get("CHAT_HISTORY_MESSAGES")

    def _context(self, src):
        """Последние реплики, которые уйдут модели (для голоса и текста лимиты свои)."""
        msgs = self.history[-max(2, self._limit(src)):]
        while msgs and msgs[0]["role"] != "user":
            msgs = msgs[1:]
        return msgs

    def _trim(self):
        keep = max(cfg.HISTORY_MESSAGES, settings.get("CHAT_HISTORY_MESSAGES"), 2)
        self.history = self.history[-keep:]
        while self.history and self.history[0]["role"] != "user":
            self.history.pop(0)

    def new_session(self, wait=True):
        """Новый пустой диалог становится активным. wait=False: если модель сейчас отвечает, не ждать (вернёт False)."""
        if not self._lock.acquire(blocking=wait):
            return False
        try:
            if self.history or not self.is_draft:
                self.history = []
                self.session = sessions.new_session()
            self.last_activity = time.time()
            path = str(self.session.path)
        finally:
            self._lock.release()
        bus.emit(bus.SESSION_CHANGED, path=path)
        return True

    reset = new_session                     # старое имя

    def open_session(self, path, wait=False):
        """Сделать активным сохранённый диалог (голос и текст продолжат его)."""
        if not self._lock.acquire(blocking=wait):
            return False
        try:
            msgs = sessions.load_messages(path)
            self.history = [{"role": m["role"], "content": m["content"]} for m in msgs]
            self._trim()
            self.session = sessions.Session(path)
            self.last_activity = time.time()
        finally:
            self._lock.release()
        bus.emit(bus.SESSION_CHANGED, path=str(path))
        return True

    def delete_session(self, path, wait=False):
        if not self._lock.acquire(blocking=wait):
            return False
        was_active = False
        try:
            was_active = str(path) == str(self.session.path)
            if was_active:
                self.history = []
                self.session = sessions.new_session()
            sessions.delete(path)
        finally:
            self._lock.release()
        if was_active:
            bus.emit(bus.SESSION_CHANGED, path=str(self.session.path))
        bus.emit(bus.SESSIONS_UPDATED)
        return True

    def cancel(self):
        """Прервать ответ, который сейчас генерируется (то, что успело прийти, сохранится)."""
        if self.busy:
            self._cancel.set()

    def _expire_if_idle(self):
        """Голос: если долго молчали, следующая фраза открывает новый диалог. На ввод текстом не влияет."""
        mins = settings.get("CONTEXT_TIMEOUT_MIN")
        if mins and self.history and time.time() - self.last_activity > mins * 60:
            log(f"Прошло больше {mins} мин. без разговора, начинаю новый диалог.")
            self.new_session()

    # ------------------------------ запрос ------------------------------
    def _extra(self):
        if self.no_reasoning:
            return {"reasoning": {"enabled": False}}
        if cfg.REASONING_EFFORT:
            return {"reasoning": {"effort": cfg.REASONING_EFFORT}}
        return {}

    def ask(self, user_text, speaker=None, on_token=None, on_status=None, src="text"):
        """src: "voice" | "text". speaker: озвучивать ответ. on_token/on_status — необязательные колбэки
        (интерфейс получает то же самое через voiceapp.bus). Возвращает текст ответа."""
        with self._lock:
            self._cancel.clear()
            self.busy = True
            turn = self._turn + 1
            try:
                from openai import BadRequestError
                if src == "voice":
                    self._expire_if_idle()
                self._turn = turn
                self.inflight = {"turn": turn, "src": src, "user": user_text, "answer": ""}
                bus.emit(bus.USER_MESSAGE, turn=turn, text=user_text, src=src)
                bus.emit(bus.ASSISTANT_START, turn=turn, src=src)
                answer = ""
                for attempt in (1, 2):
                    try:
                        answer = self._run(user_text, speaker, on_token, on_status, src, turn)
                        break
                    except BadRequestError as e:
                        log(f"LLM: ошибка запроса: {e}")
                        if attempt == 1 and cfg.REASONING_EFFORT and not self.no_reasoning:
                            log("Повторяю без режима размышлений.")
                            self.no_reasoning = True
                            continue
                        raise
                if answer:
                    self.history += [{"role": "user", "content": user_text},
                                     {"role": "assistant", "content": answer}]
                    self._trim()
                    self.session.append("user", user_text, src)
                    self.session.append("assistant", answer, src)
                    bus.emit(bus.SESSIONS_UPDATED)
                self.last_activity = time.time()
                bus.emit(bus.ASSISTANT_DONE, turn=turn, text=answer or "")
                return answer
            except Exception as e:
                bus.emit(bus.ASSISTANT_ERROR, turn=turn, message=str(e) or type(e).__name__)
                raise
            finally:
                self.inflight = None
                self.busy = False

    def _run(self, user_text, speaker, on_token, on_status, src, turn):
        system = build_system_prompt() if src == "voice" else build_chat_prompt()
        messages = [{"role": "system", "content": system}, *self._context(src),
                    {"role": "user", "content": user_text}]
        spoken, budget = "", cfg.MAX_TOOL_CALLS
        printer = _StreamPrinter()
        tools = active_tools()
        for _ in range(cfg.MAX_TOOL_CALLS + 2):
            kwargs = dict(model=cfg.LLM_MODEL, messages=messages, stream=True,
                          temperature=settings.get("LLM_TEMPERATURE"),
                          max_tokens=int(settings.get("LLM_MAX_TOKENS")), extra_body=self._extra())
            if budget > 0 and tools:
                kwargs["tools"] = tools            # когда лимит исчерпан, инструменты не предлагаем
            stream = self.client.chat.completions.create(**kwargs)
            content, reasoning, calls = "", "", {}
            chunker = Chunker()
            try:
                for chunk in stream:
                    if self._cancel.is_set():
                        break
                    if not chunk.choices:
                        continue
                    d = chunk.choices[0].delta
                    if d.content:
                        content += d.content
                        if speaker:
                            printer.feed(d.content)
                            for s in chunker.feed(d.content):
                                speaker.say(s)
                        if on_token:
                            on_token(d.content)
                        full = spoken + content
                        if self.inflight is not None:
                            self.inflight["answer"] = full
                        bus.emit(bus.TOKEN, turn=turn, delta=d.content, full=full)
                    r = getattr(d, "reasoning", None)
                    if isinstance(r, str):
                        reasoning += r
                    if d.tool_calls:
                        for tc in d.tool_calls:
                            slot = calls.setdefault(tc.index, {"id": "", "name": "", "args": ""})
                            if tc.id:
                                slot["id"] = tc.id
                            if tc.function:
                                if tc.function.name and tc.function.name != slot["name"]:
                                    slot["name"] += tc.function.name   # имя приходит кусками (часть провайдеров повторяет его целиком)
                                if tc.function.arguments:
                                    slot["args"] += tc.function.arguments
            finally:
                printer.end()
            if self._cancel.is_set():
                try:
                    stream.close()
                except Exception:
                    pass
                if speaker:
                    speaker.stop()
                return (spoken + content).strip()
            if speaker:
                for s in chunker.flush():
                    speaker.say(s)
            if not calls:
                return (spoken + content).strip()
            spoken += content + ("\n" if content.strip() else "")

            ordered = [c for _, c in sorted(calls.items())]
            am = {"role": "assistant", "content": content or None, "tool_calls": [
                {"id": c["id"], "type": "function",
                 "function": {"name": c["name"], "arguments": c["args"] or "{}"}} for c in ordered]}
            if reasoning and not self.no_reasoning:
                am["reasoning"] = reasoning
            messages.append(am)

            jobs = []
            for c in ordered:
                try:
                    args = json.loads(c["args"] or "{}")
                except Exception:
                    args = {}
                jobs.append((c, args))
            allowed = jobs[:max(budget, 0)]
            budget -= len(allowed)
            # «Секунду.» говорим только перед медленными инструментами (поиск, сеть), перед быстрыми это лишнее
            if speaker and not content.strip() and any(c["name"] not in FAST_TOOLS for c, _ in allowed):
                speaker.say("Секунду.")
            if allowed:
                status = " ".join(STATUS.get(c["name"], c["name"]) for c, _ in allowed)
                if on_status:
                    on_status(status)
                bus.emit(bus.STATUS, turn=turn, text=status)
            with ThreadPoolExecutor(max_workers=max(1, len(allowed))) as ex:   # параллельно
                results = list(ex.map(lambda j: run_tool(j[0]["name"], j[1]), allowed))
            for (c, _), res in zip(allowed, results):
                messages.append({"role": "tool", "tool_call_id": c["id"], "content": res})
            for c, _ in jobs[len(allowed):]:
                messages.append({"role": "tool", "tool_call_id": c["id"],
                                 "content": "Лимит обращений к инструментам исчерпан. "
                                            "Ответь по уже имеющимся данным."})
        return (spoken).strip()
