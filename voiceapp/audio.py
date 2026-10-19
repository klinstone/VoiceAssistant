# -*- coding: utf-8 -*-
"""Микрофон, звуковые сигналы, озвучка (Silero TTS)."""
import queue
import threading
import traceback

from . import config as cfg
from .log import log
from .text_utils import clean_for_tts


# ------------------------------ микрофон ------------------------------
def pick_device():
    if cfg.MIC_DEVICE is None:
        return None
    if isinstance(cfg.MIC_DEVICE, int):
        return cfg.MIC_DEVICE
    import sounddevice as sd
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and cfg.MIC_DEVICE.lower() in d["name"].lower():
            return i
    raise RuntimeError(f"Микрофон «{cfg.MIC_DEVICE}» не найден. Запустите: python assistant.py --devices")


class Mic:
    def __init__(self):
        import sounddevice as sd
        self.q = queue.Queue()
        self.stream = sd.RawInputStream(samplerate=cfg.SAMPLE_RATE, channels=1, dtype="int16",
                                        blocksize=1600, device=pick_device(), callback=self._cb)

    def _cb(self, indata, frames, t, status):
        self.q.put(bytes(indata))

    def start(self):
        self.stream.start()

    def get(self, timeout=0.5):
        return self.q.get(timeout=timeout)

    def drain(self):
        while True:
            try:
                self.q.get_nowait()
            except queue.Empty:
                break


# ------------------------------ сигналы ------------------------------
def _play_notes(notes, vol=0.22, block=True):
    """Короткий мягкий сигнал из нот [(частота Гц, длительность мс), ...]; частота 0 = пауза."""
    import numpy as np
    import sounddevice as sd
    sr = 48000
    parts = [np.zeros(int(sr * 0.03))]            # тишина в начале, чтобы звук не обрезался
    for f, ms in notes:
        t = np.arange(int(sr * ms / 1000)) / sr
        env = np.minimum(1.0, t / 0.008) * np.exp(-t * 16)
        parts.append((np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t)) * env)
    wave = np.concatenate(parts)
    wave = (wave / max(1e-6, np.abs(wave).max()) * vol).astype("float32")
    sd.play(wave, sr)
    if block:
        sd.wait()


def chime_start():
    """Говорите: две ноты вверх."""
    _play_notes([(659, 90), (988, 170)])


def chime_stop(block=True):
    """Запись окончена, вас больше не слушают: короткий мягкий сигнал вниз."""
    _play_notes([(784, 70), (494, 140)], vol=0.18, block=block)


def chime_reset():
    """Контекст сброшен: два одинаковых коротких сигнала."""
    _play_notes([(740, 70), (0, 50), (740, 90)])


# ------------------------------ озвучка ------------------------------
def load_tts():
    import torch
    torch.hub.set_dir(str(cfg.CACHE / "torch"))
    torch.set_num_threads(4)
    from silero import silero_tts
    for name in cfg.SILERO_MODELS:
        try:
            out = silero_tts(language="ru", speaker=name)
            model = out[0] if isinstance(out, tuple) else out
            model.to(torch.device("cpu"))
            log(f"Голос: Silero {name}, диктор {cfg.SPEAKER}")
            return model
        except Exception as e:
            log(f"Silero {name} не загрузился: {str(e)[:150]}")
    raise RuntimeError("Не удалось загрузить модель Silero TTS.")


class Speaker:
    """Два потока: синтез предложений и их воспроизведение (чтобы не было пауз между фразами)."""

    def __init__(self, tts_model):
        self.model = tts_model
        self.text_q = queue.Queue()
        self.audio_q = queue.Queue(maxsize=4)
        threading.Thread(target=self._synth_loop, daemon=True).start()
        threading.Thread(target=self._play_loop, daemon=True).start()

    def say(self, text):
        text = clean_for_tts(text)
        if text:
            self.text_q.put(text)

    def wait(self):
        self.text_q.join()
        self.audio_q.join()

    def synth(self, text):
        import torch
        with torch.inference_mode():
            audio = self.model.apply_tts(text=text, speaker=cfg.SPEAKER, sample_rate=cfg.TTS_SAMPLE_RATE)
        return audio.numpy().astype("float32")

    def _synth_safe(self, text):
        try:
            return self.synth(text)
        except ValueError:
            simple = clean_for_tts(text, strict=True)   # второй шанс: только русские буквы и знаки
            if simple and simple != text:
                return self.synth(simple)
            raise

    def _synth_loop(self):
        while True:
            text = self.text_q.get()
            try:
                self.audio_q.put(self._synth_safe(text))
            except Exception as e:
                log(f"Не удалось озвучить «{text[:60]}»: {type(e).__name__}")
            finally:
                self.text_q.task_done()

    def _play_loop(self):
        import sounddevice as sd
        while True:
            audio = self.audio_q.get()
            try:
                sd.play(audio, cfg.TTS_SAMPLE_RATE)
                sd.wait()
            except Exception:
                traceback.print_exc()
            finally:
                self.audio_q.task_done()
