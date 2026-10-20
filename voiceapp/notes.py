# -*- coding: utf-8 -*-
"""Заметки/списки и долговременная память о пользователе (файл data/notes.json).
Заметки (notes) читаются по запросу; факты (remember) подмешиваются в системный промпт каждый раз."""
import json
import os
import threading
import time
from pathlib import Path

from . import settings
from .log import log
from .text_utils import norm_text

DEFAULT_LIST = "заметки"
MAX_FACTS_IN_PROMPT = 30
_lock = threading.Lock()


def _path():
    return Path(settings.get("DATA_DIR")) / "notes.json"


def _load():
    try:
        with open(_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    data.setdefault("notes", [])
    data.setdefault("facts", [])
    data.setdefault("next_id", 1)
    return data


def _save(data):
    p = _path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    except OSError as e:
        log(f"Не удалось сохранить заметки: {e}")


def _list_name(name):
    return norm_text(name or "") or DEFAULT_LIST


def _match(query, text):
    """Нестрогое сравнение: подстрока или совпадение по основам слов («молоко» ~ «молока»)."""
    q, t = norm_text(query), norm_text(text)
    if not q:
        return False
    if q in t or t in q:
        return True
    twords = t.split()
    qwords = [w for w in q.split() if len(w) >= 3]
    if not qwords:
        return False
    return all(any(tw.startswith(w[:max(3, len(w) - 2)]) for tw in twords) for w in qwords)


def _new_id(data):
    i = data["next_id"]
    data["next_id"] += 1
    return i


# ------------------------------ заметки ------------------------------
def add_note(text, list_name=None):
    text = " ".join(str(text or "").split())
    if not text:
        return "Нечего записывать: пустой текст."
    ln = _list_name(list_name)
    with _lock:
        data = _load()
        if any(n["list"] == ln and norm_text(n["text"]) == norm_text(text) for n in data["notes"]):
            return f"«{text}» уже есть в списке «{ln}»."
        data["notes"].append({"id": _new_id(data), "t": time.strftime("%Y-%m-%dT%H:%M"), "list": ln, "text": text})
        _save(data)
        count = sum(1 for n in data["notes"] if n["list"] == ln)
    return f"Записано в «{ln}»: {text}. Всего в этом списке: {count}."


def read_notes(list_name=None):
    ln = _list_name(list_name) if list_name else None
    with _lock:
        notes = [n for n in _load()["notes"] if ln is None or n["list"] == ln]
    if not notes:
        return f"Список «{ln}» пуст." if ln else "Заметок пока нет."
    groups = {}
    for n in notes:
        groups.setdefault(n["list"], []).append(n["text"])
    out = []
    for name, items in groups.items():
        out.append(f"Список «{name}»:\n" + "\n".join(f"{i}. {t}" for i, t in enumerate(items, 1)))
    return "\n".join(out)[:3000]


def delete_note(text, list_name=None):
    ln = _list_name(list_name) if list_name else None
    with _lock:
        data = _load()
        found = [n for n in data["notes"] if (ln is None or n["list"] == ln) and _match(text, n["text"])]
        if not found:
            return "Не нашёл такую запись."
        if len(found) > 1:
            return "Подходит несколько записей, уточните:\n" + "\n".join(f"- {n['text']} (список «{n['list']}»)" for n in found)
        data["notes"] = [n for n in data["notes"] if n["id"] != found[0]["id"]]
        _save(data)
    return f"Удалено: {found[0]['text']}."


def clear_notes(list_name):
    if not list_name:
        return "Скажите, какой список очистить."
    ln = _list_name(list_name)
    with _lock:
        data = _load()
        before = len(data["notes"])
        data["notes"] = [n for n in data["notes"] if n["list"] != ln]
        removed = before - len(data["notes"])
        if removed:
            _save(data)
    return f"Список «{ln}» очищен ({removed} записей)." if removed else f"Список «{ln}» и так пуст."


def notes_tool(action=None, text="", list_name=None):
    action = (action or "").strip().lower() or ("add" if text else "read")
    if action == "add":
        return add_note(text, list_name)
    if action == "read":
        return read_notes(list_name)
    if action == "delete":
        return delete_note(text, list_name)
    if action == "clear":
        return clear_notes(list_name)
    return "Неизвестное действие. Допустимо: add, read, delete, clear."


# ------------------------------ память о пользователе ------------------------------
def remember_tool(action=None, text=""):
    action = (action or "").strip().lower() or ("add" if text else "list")
    text = " ".join(str(text or "").split())
    with _lock:
        data = _load()
        facts = data["facts"]
        if action == "add":
            if not text:
                return "Нечего запоминать: пустой текст."
            if any(norm_text(f["text"]) == norm_text(text) for f in facts):
                return "Это я уже помню."
            facts.append({"id": _new_id(data), "t": time.strftime("%Y-%m-%d"), "text": text})
            _save(data)
            return f"Запомнил: {text}."
        if action == "list":
            return ("Что я помню:\n" + "\n".join(f"- {f['text']}" for f in facts)) if facts else "Пока ничего не запомнено."
        if action == "forget":
            found = [f for f in facts if _match(text, f["text"])]
            if not found:
                return "Не нашёл такого факта."
            if len(found) > 1:
                return "Подходит несколько фактов, уточните:\n" + "\n".join(f"- {f['text']}" for f in found)
            data["facts"] = [f for f in facts if f["id"] != found[0]["id"]]
            _save(data)
            return f"Забыл: {found[0]['text']}."
    return "Неизвестное действие. Допустимо: add, forget, list."


def facts_prompt():
    """Блок для системного промпта: что ассистент помнит о пользователе."""
    with _lock:
        facts = _load()["facts"][-MAX_FACTS_IN_PROMPT:]
    if not facts:
        return ""
    return "Что ты помнишь о пользователе (по его просьбам):\n" + "\n".join(f"- {f['text']}" for f in facts)
