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


def list_sessions():
    """Список диалогов, новые сверху."""
    d = _dir()
    if not d.exists():
        return []
    infos = []
    for p in sorted(d.glob("*.jsonl"), reverse=True):
        msgs = load_messages(p)
        if not msgs:
            continue
        first = next((m["content"] for m in msgs if m["role"] == "user"), msgs[0]["content"])
        title = " ".join(first.split())[:45]
        try:
            when = datetime.strptime(p.stem[:19], "%Y-%m-%d_%H-%M-%S")
        except ValueError:
            when = datetime.fromtimestamp(p.stat().st_mtime)
        infos.append(Info(p, when, title, len(msgs)))
    return infos


def delete(path):
    try:
        Path(path).unlink()
    except OSError:
        pass
