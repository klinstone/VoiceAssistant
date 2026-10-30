# -*- coding: utf-8 -*-
"""Подготовка текста для озвучки, нарезка потока на предложения, нечёткое сравнение."""
import difflib
import re

try:
    from num2words import num2words as _n2w
except Exception:
    _n2w = None

HAS_NUM2WORDS = _n2w is not None

_LAT = {"a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф", "g": "г", "h": "х", "i": "и",
        "j": "дж", "k": "к", "l": "л", "m": "м", "n": "н", "o": "о", "p": "п", "q": "к", "r": "р",
        "s": "с", "t": "т", "u": "у", "v": "в", "w": "в", "x": "кс", "y": "й", "z": "з"}
_DIGRAPHS = [("sh", "ш"), ("ch", "ч"), ("th", "т"), ("ph", "ф"), ("ck", "к"), ("ee", "и"),
             ("oo", "у"), ("zh", "ж"), ("ya", "я"), ("yu", "ю")]


def translit(t):
    """Запасной вариант: если осталась латиница, пишем её русскими буквами."""
    def conv(m):
        w = m.group(0).lower()
        for a, b in _DIGRAPHS:
            w = w.replace(a, b)
        return "".join(_LAT.get(ch, ch) for ch in w)
    return re.sub(r"[A-Za-z]+", conv, t)


def numbers_to_words(t):
    if not _n2w:
        return t

    def repl(m):
        s = m.group(0).replace(",", ".")
        try:
            return _n2w(float(s) if "." in s else int(s), lang="ru")
        except Exception:
            return m.group(0)

    return re.sub(r"\d+(?:[.,]\d+)?", repl, t)


_THOUSANDS = re.compile(r"(?<![\w.,])\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?!\w)")


def clean_for_tts(t, strict=False):
    t = re.sub(r"https?://\S+", "", t)
    t = _THOUSANDS.sub(lambda m: re.sub(r"\D", "", m.group()), t)      # «1 000» читалось как «один ноль»
    t = re.sub(r"[*_`#>~|]+", "", t)
    t = t.replace("°C", " градусов").replace("°", " градусов").replace("%", " процентов")
    t = re.sub(r"(?<![\w])-(?=\d)", "минус ", t)
    t = numbers_to_words(t)
    t = translit(t)
    allowed = r"[^А-Яа-яЁё\s.,!?:;…\-—]" if strict else r"[^А-Яа-яЁё0-9\s.,!?:;…\-—]"
    t = re.sub(allowed, " ", t)       # убирает эмодзи, кавычки и прочее, на чём ломается Silero
    return re.sub(r"\s+", " ", t).strip()


_SENT_END = re.compile(r"(?<=[.!?…])\s+|\n+")


class Chunker:
    """Режет потоковый текст LLM на предложения, чтобы озвучивать их сразу."""

    def __init__(self):
        self.buf = ""

    def feed(self, s):
        self.buf += s
        out = []
        while True:
            m = _SENT_END.search(self.buf)
            if m:
                sent = self.buf[:m.start()].strip()
                self.buf = self.buf[m.end():]
                if sent:
                    out.append(sent)
                continue
            if len(self.buf) > 220:
                cut = self.buf.rfind(", ", 0, 220)
                if cut < 60:
                    cut = self.buf.rfind(" ", 0, 220)
                if cut <= 0:
                    cut = 219                       # длинная строка без пробелов (ссылка, base64): режем жёстко
                out.append(self.buf[:cut + 1].strip())
                self.buf = self.buf[cut + 1:]
                continue
            break
        return out

    def flush(self):
        rest = self.buf.strip()
        self.buf = ""
        return [rest] if rest else []


def norm_text(t):
    t = t.lower().replace("ё", "е")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t)).strip()


def fuzzy_contains(text, phrases, threshold=0.8):
    """Есть ли в тексте одна из фраз (с допуском на неточное распознавание)."""
    t = norm_text(text)
    words = t.split()
    padded = f" {t} "
    for ph in phrases:
        p = norm_text(ph)
        if not p:
            continue
        if f" {p} " in padded:                       # по границам слов: «эй роботный» не считается за «эй робот»
            return True
        n = len(p.split())
        for i in range(max(1, len(words) - n + 1)):
            w = " ".join(words[i:i + n])
            if difflib.SequenceMatcher(None, p, w).ratio() >= threshold:
                return True
    return False


def split_after_phrase(text, phrase, threshold=0.8):
    """Часть текста после кодовой фразы (с допуском на неточное распознавание).
    Возвращает None, если фразу найти не удалось."""
    words = [(m.group().lower().replace("ё", "е"), m.end()) for m in re.finditer(r"\w+", text)]
    p = norm_text(phrase)
    n = len(p.split())
    for i in range(len(words) - n + 1):
        w = " ".join(x for x, _ in words[i:i + n])
        if difflib.SequenceMatcher(None, p, w).ratio() >= threshold:
            return text[words[i + n - 1][1]:].lstrip(" ,.!?:;-—…")
    return None
