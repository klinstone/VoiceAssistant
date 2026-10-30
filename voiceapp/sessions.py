# -*- coding: utf-8 -*-
"""Хранение диалогов: один файл .jsonl на диалог (каждая строка — одна реплика)."""
import json
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import settings

_lock = threading.Lock()


def _dir():
    return Path(settings.get("SESSIONS_DIR"))


class Session:
    def __init__(self, path):
        self.path = Path(path)

    def append(self, role, content, src):
        rec = {"t": datetime.now().isoformat(timespec="seconds"),
               "role": role, "content": content, "src": src}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _lock, open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def new_session():
    """Новый диалог. Файл появится при первой записанной реплике."""
    name = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = _dir() / f"{name}.jsonl"
    n = 1
    while path.exists():
        path = _dir() / f"{name}_{n}.jsonl"
        n += 1
    return Session(path)


def load_messages(path):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("role") in ("user", "assistant") and rec.get("content"):
                    out.append(rec)
    except OSError:
        pass
    return out


@dataclass
class Info:
    path: Path
    when: datetime
    title: str
    count: int


_summary_cache = {}      # путь -> ((время изменения, размер), результат): файл диалога только дописывается, размер выдаст изменение


def _summary(path):
    """Заголовок и число реплик с кэшем: окно обновляет список после каждого ответа, а читать заново нужно только изменившиеся файлы."""
    try:
        st = Path(path).stat()
    except OSError:
        return None
    key = (st.st_mtime_ns, st.st_size)
    hit = _summary_cache.get(str(path))
    if hit and hit[0] == key:
        return hit[1]
    result = _read_summary(path)
    _summary_cache[str(path)] = (key, result)
    return result


def _read_summary(path):
    """Заголовок и число реплик. JSON разбирается только до первой реплики пользователя,
    остальное лишь считается построчно: список диалогов открывается быстро даже при сотнях файлов."""
    title, count = None, 0
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                count += 1
                if title is None:
                    try:
                        rec = json.loads(line)
                    except Exception:
                        count -= 1
                        continue
                    if rec.get("role") == "user" and rec.get("content"):
                        title = " ".join(rec["content"].split())[:45]
    except OSError:
        return None
    if not count:
        return None
    return title or "(без заголовка)", count


def list_sessions():
    """Список диалогов, новые сверху."""
    d = _dir()
    if not d.exists():
        return []
    infos = []
    for p in sorted(d.glob("*.jsonl"), reverse=True):
        s = _summary(p)
        if s is None:
            continue
        try:
            when = datetime.strptime(p.stem[:19], "%Y-%m-%d_%H-%M-%S")
        except ValueError:
            when = datetime.fromtimestamp(p.stat().st_mtime)
        infos.append(Info(p, when, s[0], s[1]))
    return infos


def delete(path):
    _summary_cache.pop(str(path), None)
    try:
        Path(path).unlink()
    except OSError:
        pass
