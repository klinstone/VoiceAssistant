# -*- coding: utf-8 -*-
"""Главная логика: ожидание кодового слова, запись фразы, диалог."""
import collections
import json
import queue
import re
import threading
import time
import traceback

from . import config as cfg
from . import settings
from .audio import Mic, Speaker, chime_alarm, chime_reset, chime_start, chime_stop, load_tts
from .log import log
from .reminders import SCHEDULER
from .stt import load_asr, transcribe
from .text_utils import HAS_NUM2WORDS, fuzzy_contains, norm_text, split_after_phrase


def is_new_session(text):
    return len(text.split()) <= 6 and fuzzy_contains(text, cfg.NEW_SESSION_PHRASES, cfg.WAKE_MATCH)


class Assistant:
    def __init__(self, stop, tray=None):
        self.stop = stop
        self.tray = tray
        self.brain = None
        self.asr = None
        self.speaker = None
        self.ignore_until = 0.0
        self.alarm_stop = threading.Event()     # «хватит повторять сигнал таймера»
        self.chiming = threading.Event()        # идёт сигнал таймера (его не надо записывать как речь)
        self.wake_re = re.compile(
            r"^\W*" + r"\W+".join(map(re.escape, cfg.WAKE_PHRASE.split())) + r"\W*", re.I)

    def state(self, st, text):
        if self.tray:
            self.tray.set(st, text)

    def reset_session(self):
        if self.brain:
            self.brain.reset()
        log("Контекст диалога сброшен.")

    def silence(self):
        """Остановить озвучку и повторы сигнала таймера (пункт «Остановить звук» в трее, кодовое слово)."""
        self.alarm_stop.set()
        if self.speaker is not None:
            self.speaker.stop()

    # ---------------------------- таймеры ----------------------------
    def on_alarm(self, item, late=False):
        """Сработал таймер или напоминание (вызывается из потока планировщика, модель не участвует)."""
        label = (item.get("label") or "").strip()
        head = "Пропущенное напоминание." if late else ("Таймер сработал." if item.get("kind") == "timer" else "Напоминание.")
        text = head + (f" {label}." if label else "")
        log("Сработало:", text)
        if self.tray:
            self.tray.notify(label or head)
        self.alarm_stop.clear()
        repeats = max(1, int(settings.get("ALARM_REPEATS")))
        for i in range(repeats):
            if self.alarm_stop.is_set():
                break
            try:
                self.chiming.set()
                try:
                    chime_alarm()
                finally:
                    self.chiming.clear()
                if self.speaker is not None:
                    self.speaker.say(text)
                    self.speaker.wait()
            except Exception:
                traceback.print_exc()
            if i < repeats - 1 and self.alarm_stop.wait(settings.get("ALARM_GAP")):
                break

    # ---------------------------- загрузка ----------------------------
    def load(self, llm=True):
        self.state("idle", "загрузка")
        if not HAS_NUM2WORDS:
            log("Совет: выполните `pip install num2words`, чтобы цифры озвучивались словами.")
        from vosk import Model, SetLogLevel
        SetLogLevel(-1)
        if not cfg.VOSK_DIR.exists():
            raise RuntimeError(f"Не найдена папка {cfg.VOSK_DIR}")
        log("Загружаю Vosk...")
        self.vosk = Model(str(cfg.VOSK_DIR))
        log("Загружаю распознавание речи (первый запуск скачивает модель)...")
        self.asr = load_asr()
        log("Загружаю голос (первый запуск скачивает модель)...")
        self.speaker = Speaker(load_tts())
        try:
            self.speaker.synth("Привет.")     # «прогрев» без воспроизведения
        except Exception:
            pass
        if llm:
            from .llm import Brain
            self.brain = Brain()

    # ---------------------------- запись фразы ----------------------------
    def _others_sounding(self):
        """Сейчас звучит не пользователь (озвучка, сигнал таймера): такое не записываем."""
        return self.chiming.is_set() or (self.speaker is not None and self.speaker.busy())

    def record(self, mic, first_timeout, preroll=None):
        """Пишет фразу. Заканчивает, когда cfg.END_SILENCE секунд нет новых слов.
        preroll: уже записанные блоки звука (то, что вы успели сказать вместе с кодовым словом).
        Возвращает (pcm, текст_от_vosk) или (None, "") если вы не заговорили."""
        from vosk import KaldiRecognizer
        rec = KaldiRecognizer(self.vosk, cfg.SAMPLE_RATE)
        frames, segments = list(preroll or []), []
        partial, started = "", bool(frames)
        max_len = cfg.MAX_RECORD - 0.1 * len(frames)     # блок = 0.1 с
        t0 = last_act = time.time()
        last_idx = len(frames)
        while not self.stop.is_set():
            try:
                data = mic.get(1.0)
            except queue.Empty:
                data = None            # микрофон молчит: таймауты всё равно проверяем (раньше тут был вечный цикл)
            now = time.time()
            if data is not None:
                if self._others_sounding():
                    # например, сработал таймер: чужой голос в запись не берём, начинаем запись заново
                    rec.Reset()
                    frames, segments, partial, started = [], [], "", False
                    t0 = last_act = now
                    last_idx, max_len = 0, cfg.MAX_RECORD
                    continue
                frames.append(data)
                if rec.AcceptWaveform(data):
                    t = json.loads(rec.Result()).get("text", "")
                    if t:
                        segments.append(t)
                        started, last_act, last_idx = True, now, len(frames)
                    partial = ""
                else:
                    p = json.loads(rec.PartialResult()).get("partial", "")
                    if p != partial:
                        partial = p
                        if p:
                            started, last_act, last_idx = True, now, len(frames)
            if not started:
                if now - t0 > first_timeout:
                    return None, ""
            elif now - last_act > cfg.END_SILENCE or now - t0 > max_len:
                break
        if not started:
            return None, ""
        final = json.loads(rec.FinalResult()).get("text", "")
        if final:
            segments.append(final)
        pcm = b"".join(frames[:last_idx + 8])      # обрезаем хвост тишины (оставляем ~0.8 с)
        return pcm, " ".join(segments).strip()

    def listen_once(self):
        mic = Mic()
        mic.start()
        log("Говорите (после сигнала)...")
        chime_start()
        mic.drain()
        pcm, vt = self.record(mic, cfg.NO_SPEECH_TIMEOUT)
        chime_stop()
        if pcm is None:
            log("Речь не обнаружена. Проверьте микрофон и усиление.")
            return
        log("Vosk услышал:", vt)
        log("GigaAM услышал:", transcribe(self.asr, pcm, vt))

    # ---------------------------- диалог ----------------------------
    def conversation(self, mic, preroll=None):
        """Первая реплика после кодового слова, следующие без него, пока вы отвечаете в окне.
        preroll: звук, записанный вместе с кодовым словом (вы начали говорить, не дожидаясь сигнала)."""
        first = True
        while not self.stop.is_set():
            self.state("listening", "слушаю")
            used_preroll = preroll is not None
            if not used_preroll:
                chime_start()                       # пиликанье: можно говорить
                mic.drain()
            pcm, vt = self.record(mic, cfg.NO_SPEECH_TIMEOUT if first else cfg.FOLLOWUP_WINDOW,
                                  preroll=preroll)
            preroll = None
            if pcm is None:
                chime_stop(block=True)              # «диалог окончен, не слушаю»
                log("Диалог завершён." if not first else "Речь не обнаружена.")
                return
            chime_stop(block=False)                 # «записал, думаю»
            self.state("thinking", "думаю")
            full = transcribe(self.asr, pcm, vt)
            if used_preroll:                        # в записи есть и кодовая фраза: берём то, что после неё
                after = split_after_phrase(full, cfg.WAKE_PHRASE, cfg.WAKE_MATCH)
                text = (after if after is not None else self.wake_re.sub("", full)).strip()
            else:
                text = self.wake_re.sub("", full).strip()
            log("Вы:", text)
            if not text:
                if used_preroll:                    # вопроса не нашли: работаем как обычно, с сигналом
                    continue
                return
            if is_new_session(text):
                self.reset_session()
                time.sleep(0.3)
                chime_reset()
                return
            try:
                answer = self.brain.ask(text, self.speaker)  # ответ печатается и озвучивается потоком
            except Exception as e:
                log(f"Ошибка LLM: {e}")
                self.speaker.say("Не получилось связаться с моделью.")
                self.speaker.wait()
                return
            if not answer:                          # раньше в этом случае ассистент молча замолкал
                self.speaker.say("Не получилось сформулировать ответ.")
            self.state("speaking", "говорю")
            self.speaker.wait()
            time.sleep(0.4)                         # даём затихнуть эху комнаты
            first = False

    # ---------------------------- кодовое слово ----------------------------
    def verify(self, mic, ring, phrases, wake):
        """Точная модель перепроверяет, что кодовое слово прозвучало на самом деле.
        Возвращает (принято, начало_вопроса): если вы продолжили говорить сразу после кодовой фразы,
        начало вопроса уже есть в записи."""
        if not cfg.WAKE_VERIFY or self.asr is None:
            return True, ""
        end = time.time() + cfg.VERIFY_TAIL         # дослушиваем, чтобы фраза закончилась
        while time.time() < end:
            try:
                data = mic.get(0.2)
            except queue.Empty:
                continue
            ring.append(data)
            wake.AcceptWaveform(data)
        conf_text, min_conf = "", None
        try:                                        # уверенность Vosk по словам (для настройки порога)
            words = [w for w in json.loads(wake.FinalResult()).get("result", [])
                     if w.get("word") != "[unk]"]
            if words:
                conf_text = " ".join(f"{w['word']}({w['conf']:.2f})" for w in words)
                min_conf = min(w["conf"] for w in words)
        except Exception:
            pass
        heard = transcribe(self.asr, b"".join(ring), "")
        ok = fuzzy_contains(heard, phrases, cfg.WAKE_MATCH)
        min_needed = settings.get("WAKE_MIN_CONF")
        if ok and min_needed and min_conf is not None and min_conf < min_needed:
            ok = False
        rest = ""
        if ok and phrases == [cfg.WAKE_PHRASE] and settings.get("WAKE_CARRY_ON"):
            after = split_after_phrase(heard, cfg.WAKE_PHRASE, cfg.WAKE_MATCH) or ""
            if len(norm_text(after).replace(" ", "")) >= 3:     # не шум, а настоящие слова
                rest = after
        log(f"Проверка кодового слова: «{heard}»; Vosk: {conf_text or '-'} -> "
            f"{'принято' if ok else 'отклонено'}" + (f"; после фразы уже есть речь: «{rest}»" if rest else ""))
        return ok, rest

    def wake_grammar(self):
        items = [cfg.WAKE_PHRASE, *cfg.NEW_SESSION_PHRASES]
        if settings.get("WAKE_SPLIT_WORDS"):        # отдельные слова: одиночное «эй» не станет «эй робот»
            for ph in list(items):
                for w in ph.split():
                    if len(ph.split()) > 1 and w not in items:
                        items.append(w)
        return json.dumps([*items, "[unk]"], ensure_ascii=False)

    def _reopen_mic(self, old):
        """Микрофон перестал присылать звук (Bluetooth-гарнитура уснула, устройство переподключили)."""
        log("Микрофон перестал передавать звук, переоткрываю...")
        old.close()
        try:
            m = Mic()
            m.start()
            return m
        except Exception as e:
            log(f"Не удалось открыть микрофон: {e}")
            time.sleep(3)
            return old

    def run(self):
        from vosk import KaldiRecognizer
        self.load()
        SCHEDULER.set_handler(self.on_alarm)        # таймеры и напоминания будут озвучиваться отсюда
        SCHEDULER.start()
        mic = Mic()
        mic.start()
        wake = KaldiRecognizer(self.vosk, cfg.SAMPLE_RATE, self.wake_grammar())
        try:
            wake.SetWords(True)                     # нужно, чтобы видеть уверенность по словам
        except Exception:
            pass
        ring = collections.deque(maxlen=30)         # последние ~3 с звука для проверки
        chime_start()
        mic.drain()
        self.state("ready", f"жду «{cfg.WAKE_PHRASE}»")
        log(f"Готово. Скажите: «{cfg.WAKE_PHRASE}» (или «{cfg.NEW_SESSION_PHRASES[0]}» для сброса контекста)")
        last_data = time.time()
        while not self.stop.is_set():
            try:
                data = mic.get(0.5)
            except queue.Empty:
                if time.time() - last_data > 5:
                    mic = self._reopen_mic(mic)
                    last_data = time.time()
                continue
            last_data = time.time()
            ring.append(data)
            if wake.AcceptWaveform(data):
                heard = json.loads(wake.Result()).get("text", "")
            else:
                heard = json.loads(wake.PartialResult()).get("partial", "")
            if time.time() < self.ignore_until:
                continue
            if cfg.WAKE_PHRASE in heard:
                kind, phrases = "wake", [cfg.WAKE_PHRASE]
            elif any(p in heard for p in cfg.NEW_SESSION_PHRASES):
                kind, phrases = "reset", cfg.NEW_SESSION_PHRASES
            else:
                continue
            ok, rest = self.verify(mic, ring, phrases, wake)
            preroll = list(ring) if (ok and rest) else None     # звук вместе с началом вопроса
            wake.Reset()
            ring.clear()
            if not ok:
                continue
            if kind == "reset":
                self.reset_session()
                chime_reset()
                mic.drain()
                continue
            log("Кодовое слово!")
            self.silence()                          # если звенел таймер, сигнал прекращаем
            try:
                self.conversation(mic, preroll=preroll)
            except Exception:
                traceback.print_exc()
            mic.drain()
            wake.Reset()
            ring.clear()
            last_data = time.time()
            self.ignore_until = time.time() + cfg.IGNORE_AFTER_DIALOG
            self.state("ready", f"жду «{cfg.WAKE_PHRASE}»")

    def run_safe(self):
        try:
            self.run()
        except Exception:
            traceback.print_exc()
            self.state("error", "ошибка, см. assistant.log")
