# -*- coding: utf-8 -*-
"""Распознавание речи: загрузка GigaAM/Parakeet через onnx-asr и расшифровка записи."""
from . import config as cfg
from .log import log


def load_asr():
    try:
        import onnx_asr
    except Exception as e:
        log(f"onnx-asr не загрузился: {e}")
        return None
    for name in cfg.ASR_MODELS:
        try:
            m = onnx_asr.load_model(name)
            log(f"Распознавание: {name}")
            try:                                   # «прогрев»
                import numpy as np
                m.recognize(np.zeros(cfg.SAMPLE_RATE, dtype=np.float32), sample_rate=cfg.SAMPLE_RATE)
            except Exception:
                pass
            return m
        except Exception as e:
            log(f"Модель {name} недоступна: {str(e)[:150]}")
    log("GigaAM/Parakeet не загрузились, использую текст от Vosk (хуже по качеству).")
    return None


def transcribe(asr, pcm, fallback_text=""):
    """pcm: байты int16 16 кГц. Возвращает текст."""
    import numpy as np
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    if audio.size:
        p = float(np.percentile(np.abs(audio), 99.5))
        if p > 0.002:                              # подтягиваем тихую запись
            audio = np.clip(audio * min(0.5 / p, 30.0), -1.0, 1.0)
    if asr is not None:
        try:
            res = asr.recognize(audio, sample_rate=cfg.SAMPLE_RATE)
            text = res if isinstance(res, str) else getattr(res, "text", str(res))
            return text.strip()
        except Exception as e:
            log(f"Ошибка распознавания: {e}")
    return fallback_text.strip()
