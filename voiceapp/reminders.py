# -*- coding: utf-8 -*-
"""Таймеры и напоминания.
Один фоновый поток проверяет список раз в полсекунды; список хранится в data/reminders.json,
так что таймеры переживают перезапуск. Когда время вышло, вызывается обработчик
(в голосовом режиме это Assistant.on_alarm: сигнал + озвучка) — языковая модель для этого не нужна."""
import datetime
import json
import os
import re
import threading
import time
from pathlib import Path

from . import settings
from .log import log
from .text_utils import norm_text


# ------------------------------ форматирование ------------------------------
def plural(n, forms):
    """plural(5, ("минута", "минуты", "минут")) -> "минут"."""
    n = abs(int(n))
    if 11 <= n % 100 <= 14:
        return forms[2]
    if n % 10 == 1:
        return forms[0]
    return forms[1] if 2 <= n % 10 <= 4 else forms[2]


def fmt_duration(sec):
    sec = max(0, int(round(sec)))
    d, rest = divmod(sec, 86400)
    h, rest = divmod(rest, 3600)
    m, s = divmod(rest, 60)
    parts = []
    if d:
        parts.append(f"{d} {plural(d, ('день', 'дня', 'дней'))}")
    if h:
        parts.append(f"{h} {plural(h, ('час', 'часа', 'часов'))}")
    if m and not d:
        parts.append(f"{m} {plural(m, ('минута', 'минуты', 'минут'))}")
    if s and not d and not h:
        parts.append(f"{s} {plural(s, ('секунда', 'секунды', 'секунд'))}")
    return " ".join(parts) or "0 секунд"


def fmt_when(ts):
    d = datetime.datetime.fromtimestamp(ts)
    today = datetime.date.today()
    if d.date() == today:
        day = "сегодня"
    elif d.date() == today + datetime.timedelta(days=1):
        day = "завтра"
    else:
        day = f"{d:%d.%m}"
    return f"{day} в {d:%H:%M}"


def parse_at(text, now=None):
    """'18:40' -> ближайшее такое время; 'ГГГГ-ММ-ДД ЧЧ:ММ' и 'ДД.ММ.ГГГГ ЧЧ:ММ' -> точный момент. Возвращает timestamp."""
    now = time.time() if now is None else now
    s = (text or "").strip()
    m = re.fullmatch(r"(\d{1,2})[:.](\d{2})(?::\d{2})?", s)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if h > 23 or mi > 59:
            raise ValueError("bad time")
        base = datetime.datetime.fromtimestamp(now).replace(hour=h, minute=mi, second=0, microsecond=0)
        if base.timestamp() <= now:
            base += datetime.timedelta(days=1)
        return base.timestamp()
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "")).timestamp()
    except ValueError:
        pass
    for f in ("%d.%m.%Y %H:%M", "%d.%m.%y %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.datetime.strptime(s, f).timestamp()
        except ValueError:
            continue
    raise ValueError("bad time")


# ------------------------------ планировщик ------------------------------
def _default_handler(item, late):
    log(f"Сработало: {item.get('label') or item.get('kind')} (голосовая часть не запущена)")
    try:
        from .audio import chime_alarm
        chime_alarm()
    except Exception:
        pass


class Scheduler:
    def __init__(self):
        self._lock = threading.Lock()
        self._items = []
        self._next_id = 1
        self._loaded = False
        self._handler = None
        self._thread = None

    # --- хранение ---
    def _path(self):
        return Path(settings.get("DATA_DIR")) / "reminders.json"

    def _ensure_loaded(self):
        if self._loaded:
            return
        self._loaded = True
        try:
            with open(self._path(), encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):          # файл правили руками или он повреждён
                raise ValueError("ожидался объект")
            items = [i for i in data.get("items", []) if isinstance(i, dict) and isinstance(i.get("when"), (int, float))]
            next_id = int(data.get("next_id", 1))
        except (OSError, ValueError, TypeError):
            return
        self._next_id = max(next_id, max((i["id"] for i in items if isinstance(i.get("id"), int)), default=0) + 1)
        for i in items:
            if not isinstance(i.get("id"), int):
                i["id"] = self._next_id
                self._next_id += 1
        self._items = items

    def _save(self):
        p = self._path()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"next_id": self._next_id, "items": self._items}, f, ensure_ascii=False, indent=1)
            os.replace(tmp, p)
        except OSError as e:
            log(f"Не удалось сохранить таймеры: {e}")

    # --- управление ---
    def set_handler(self, fn):
        self._handler = fn

    def start(self):
        with self._lock:
            self._ensure_loaded()
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._loop, daemon=True, name="scheduler")
                self._thread.start()

    def add(self, when, label, kind):
        with self._lock:
            self._ensure_loaded()
            item = {"id": self._next_id, "when": when, "label": label, "kind": kind}
            self._next_id += 1
            self._items.append(item)
            self._save()
        self.start()
        return item

    def items(self):
        with self._lock:
            self._ensure_loaded()
            return sorted((dict(i) for i in self._items), key=lambda i: i["when"])

    def find(self, query):
        q = norm_text(query or "")
        if not q:
            return []
        return [i for i in self.items() if q in norm_text(i.get("label", ""))]

    def remove(self, ids):
        ids = set(ids)
        with self._lock:
            self._ensure_loaded()
            removed = [i for i in self._items if i["id"] in ids]
            self._items = [i for i in self._items if i["id"] not in ids]
            if removed:
                self._save()
        return removed

    # --- фоновый поток ---
    def _loop(self):
        while True:
            now = time.time()
            with self._lock:
                due = [i for i in self._items if i["when"] <= now]
                if due:
                    self._items = [i for i in self._items if i["when"] > now]
                    self._save()
            for it in due:
                late = now - it["when"]
                if it.get("kind") == "timer" and late > 600:
                    log(f"Таймер «{it.get('label')}» пропущен (программа была выключена).")
                    continue
                threading.Thread(target=self._fire, args=(it, late > 90), daemon=True).start()
            time.sleep(0.5)

    def _fire(self, item, late):
        try:
            (self._handler or _default_handler)(item, late)
        except Exception as e:
            log(f"Ошибка обработчика таймера: {e}")


SCHEDULER = Scheduler()


# ------------------------------ инструмент для модели ------------------------------
def _describe(item, now):
    name = item.get("label") or "без названия"
    return f"«{name}» — через {fmt_duration(item['when'] - now)} ({fmt_when(item['when'])})"


def timer(action=None, seconds=None, at=None, label=""):
    label = " ".join(str(label or "").split())[:80]
    action = (action or "").strip().lower() or ("set" if (seconds or at) else "list")
    now = time.time()
    items = SCHEDULER.items()

    if action == "list":
        if not items:
            return "Активных таймеров и напоминаний нет."
        return "Активные:\n" + "\n".join(f"- {_describe(i, now)}" for i in items)

    if action == "cancel":
        if not items:
            return "Активных таймеров и напоминаний нет."
        if norm_text(label) in ("все", "всё", "all", "*"):
            ids = [i["id"] for i in items]
        elif label:
            ids = [i["id"] for i in SCHEDULER.find(label)]
            if not ids:
                return f"Не нашёл таймер «{label}». Активные:\n" + "\n".join(f"- {_describe(i, now)}" for i in items)
        elif len(items) == 1:
            ids = [items[0]["id"]]
        else:
            return "Активных несколько, уточните какой отменить:\n" + "\n".join(f"- {_describe(i, now)}" for i in items)
        removed = SCHEDULER.remove(ids)
        return "Отменено: " + ", ".join(f"«{i.get('label') or 'без названия'}»" for i in removed) + "."

    if action != "set":
        return "Неизвестное действие. Допустимо: set, list, cancel."
    if len(items) >= 50:
        return "Слишком много активных таймеров (50)."
    if at:
        try:
            when = parse_at(str(at), now)
        except ValueError:
            return f"Не понял время «{at}». Нужен формат ЧЧ:ММ или ГГГГ-ММ-ДД ЧЧ:ММ."
        kind = "reminder"
    else:
        try:
            sec = float(seconds)
        except (TypeError, ValueError):
            return "Не указано, на сколько ставить таймер (seconds) или на какое время (at)."
        if sec < 1 or sec > 30 * 86400:
            return "Таймер можно поставить от одной секунды до тридцати суток."
        when, kind = now + sec, "timer"
    if when <= now:
        return "Это время уже прошло."
    if when - now > 366 * 86400:
        return "Слишком далёкая дата (максимум год)."
    SCHEDULER.add(when, label, kind)
    what = "Таймер поставлен" if kind == "timer" else "Напоминание поставлено"
    name = f" «{label}»" if label else ""
    return f"{what}{name}: сработает через {fmt_duration(when - now)} ({fmt_when(when)})."
