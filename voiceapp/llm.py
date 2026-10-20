# -*- coding: utf-8 -*-
"""Общение с моделью через OpenRouter: потоковый ответ, инструменты, история и сохранение диалогов."""
import json
import time
from concurrent.futures import ThreadPoolExecutor

from . import config as cfg
from . import sessions, settings
from .chat_prompt import build_chat_prompt
from .client import make_client
from .log import log
from .prompt import build_system_prompt
from .text_utils import Chunker
from .tools import FAST_TOOLS, STATUS, TOOLS, run_tool


class _StreamPrinter:
    """Печатает ответ в консоль по мере поступления токенов."""

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
    """mode="voice": голосовой диалог (озвучка, автосброс по времени);
    mode="chat": текстовый чат (потоковый вывод в окно)."""

    def __init__(self, mode="voice"):
        self.client = make_client(timeout=40)
        self.mode = mode
        self.history = []
        self.session = None
        self.no_reasoning = False
        self.last_activity = time.time()

    # ------------------------- история и сессии -------------------------
    def _limit(self):
        return cfg.HISTORY_MESSAGES if self.mode == "voice" else settings.get("CHAT_HISTORY_MESSAGES")

    def _trim(self):
        self.history = self.history[-self._limit():]
        while self.history and self.history[0]["role"] != "user":
            self.history.pop(0)

    def reset(self):
        """Новый диалог: забываем контекст, следующая реплика откроет новый файл."""
        self.history = []
        self.session = None

    def load_session(self, path):
        """Продолжить сохранённый диалог."""
        msgs = sessions.load_messages(path)
        self.history = [{"role": m["role"], "content": m["content"]} for m in msgs]
        self._trim()
        self.session = sessions.Session(path)

    def _expire_if_idle(self):
        mins = settings.get("CONTEXT_TIMEOUT_MIN")
        if self.mode == "voice" and mins and self.history and time.time() - self.last_activity > mins * 60:
            log(f"Прошло больше {mins} мин. без разговора, начинаю новый диалог.")
            self.reset()

    # ------------------------------ запрос ------------------------------
    def _extra(self):
        if self.no_reasoning:
            return {"reasoning": {"enabled": False}}
        if cfg.REASONING_EFFORT:
            return {"reasoning": {"effort": cfg.REASONING_EFFORT}}
        return {}

    def ask(self, user_text, speaker=None, on_token=None, on_status=None, src=None):
        """speaker: озвучивать ответ; on_token(str): получать текст по частям; on_status(str): статус инструментов."""
        from openai import BadRequestError
        src = src or ("voice" if self.mode == "voice" else "text")
        self._expire_if_idle()
        for attempt in (1, 2):
            try:
                answer = self._run(user_text, speaker, on_token, on_status)
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
            if self.session is None:
                self.session = sessions.new_session()
            self.session.append("user", user_text, src)
            self.session.append("assistant", answer, src)
        self.last_activity = time.time()
        return answer

    def _run(self, user_text, speaker, on_token, on_status):
        system = build_system_prompt() if self.mode == "voice" else build_chat_prompt()
        messages = [{"role": "system", "content": system}, *self.history,
                    {"role": "user", "content": user_text}]
        spoken, budget = "", cfg.MAX_TOOL_CALLS
        printer = _StreamPrinter()
        for _ in range(cfg.MAX_TOOL_CALLS + 2):
            kwargs = dict(model=cfg.LLM_MODEL, messages=messages, stream=True, temperature=0.7,
                          max_tokens=1500, extra_body=self._extra())
            if budget > 0 and TOOLS:
                kwargs["tools"] = TOOLS            # когда лимит исчерпан, инструменты не предлагаем
            stream = self.client.chat.completions.create(**kwargs)
            content, reasoning, calls = "", "", {}
            chunker = Chunker()
            try:
                for chunk in stream:
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
            if speaker:
                for s in chunker.flush():
                    speaker.say(s)
            spoken += content
            if not calls:
                return spoken.strip()

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
            if on_status and allowed:
                on_status(" ".join(STATUS.get(c["name"], c["name"]) for c, _ in allowed))
            with ThreadPoolExecutor(max_workers=max(1, len(allowed))) as ex:   # параллельно
                results = list(ex.map(lambda j: run_tool(j[0]["name"], j[1]), allowed))
            for (c, _), res in zip(allowed, results):
                messages.append({"role": "tool", "tool_call_id": c["id"], "content": res})
            for c, _ in jobs[len(allowed):]:
                messages.append({"role": "tool", "tool_call_id": c["id"],
                                 "content": "Лимит обращений к инструментам исчерпан. "
                                            "Ответь по уже имеющимся данным."})
        return spoken.strip()
