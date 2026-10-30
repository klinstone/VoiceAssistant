# -*- coding: utf-8 -*-
"""Страница «Данные и файлы»: заметки, память и напоминания можно править прямо здесь,
а любой файл программы — открыть или показать в папке."""
from pathlib import Path

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (QAbstractItemView, QDateTimeEdit, QDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from .. import config as cfg
from .. import notes, settings
from ..reminders import SCHEDULER, fmt_when
from .widgets import open_path, reveal


def _btn(text, primary=False):
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    if primary:
        b.setObjectName("primary")
    return b


class NotesTab(QWidget):
    """Заметки и списки (например, «покупки»): их читает и пополняет модель."""

    def __init__(self, on_status):
        super().__init__()
        self.say = on_status
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 14, 14, 14)
        info = QLabel("Записи из заметок и списков. Здесь их можно поправить, добавить или удалить. "
                      "Изменения вступают в силу после «Сохранить».")
        info.setObjectName("muted")
        info.setWordWrap(True)
        v.addWidget(info)
        self.dirty = False                      # есть несохранённые правки (страницу не перезагружаем поверх них)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Список", "Запись"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 160)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.itemChanged.connect(lambda _: setattr(self, "dirty", True))
        v.addWidget(self.table, 1)
        row = QHBoxLayout()
        add, rm, ref, save = _btn("Добавить"), _btn("Удалить"), _btn("Обновить"), _btn("Сохранить", True)
        add.clicked.connect(lambda: self._add("заметки", ""))
        rm.clicked.connect(self._remove)
        ref.clicked.connect(self.load)
        save.clicked.connect(self.save)
        for b in (add, rm, ref):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(save)
        v.addLayout(row)

    def _add(self, ln, text):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(ln))
        self.table.setItem(r, 1, QTableWidgetItem(text))
        self.table.setCurrentCell(r, 1)

    def _remove(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)
            self.dirty = True

    def load(self):
        self.table.blockSignals(True)           # заполнение из файла не считается правкой
        self.table.setRowCount(0)
        for ln, text in notes.snapshot()["notes"]:
            self._add(ln, text)
        self.table.clearSelection()
        self.table.blockSignals(False)
        self.dirty = False

    def save(self):
        rows = [((self.table.item(r, 0) or QTableWidgetItem()).text(), (self.table.item(r, 1) or QTableWidgetItem()).text())
                for r in range(self.table.rowCount())]
        notes.replace_all(rows, notes.snapshot()["facts"])
        self.say("Заметки сохранены.")
        self.load()


class FactsTab(QWidget):
    """Долговременная память: факты о вас, которые модель получает в каждом запросе."""

    def __init__(self, on_status):
        super().__init__()
        self.say = on_status
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 14, 14, 14)
        info = QLabel("Факты о вас, которые ассистент запомнил по вашей просьбе. Они добавляются в каждый запрос к модели "
                      "(последние 30), поэтому держите список коротким.")
        info.setObjectName("muted")
        info.setWordWrap(True)
        v.addWidget(info)
        self.dirty = False
        self.list = QListWidget()
        self.list.setObjectName("inner")
        self.list.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.list.itemChanged.connect(lambda _: setattr(self, "dirty", True))
        v.addWidget(self.list, 1)
        row = QHBoxLayout()
        add, rm, ref, save = _btn("Добавить"), _btn("Удалить"), _btn("Обновить"), _btn("Сохранить", True)
        add.clicked.connect(self._add)
        rm.clicked.connect(self._remove)
        ref.clicked.connect(self.load)
        save.clicked.connect(self.save)
        for b in (add, rm, ref):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(save)
        v.addLayout(row)

    def _item(self, text):
        it = QListWidgetItem(text)
        it.setFlags(it.flags() | Qt.ItemIsEditable)
        return it

    def _add(self):
        it = self._item("")
        self.list.addItem(it)
        self.list.setCurrentItem(it)
        self.list.editItem(it)
        self.dirty = True

    def _remove(self):
        r = self.list.currentRow()
        if r >= 0:
            self.list.takeItem(r)
            self.dirty = True

    def load(self):
        self.list.blockSignals(True)
        self.list.clear()
        for t in notes.snapshot()["facts"]:
            self.list.addItem(self._item(t))
        self.list.blockSignals(False)
        self.dirty = False

    def save(self):
        facts = [self.list.item(i).text() for i in range(self.list.count())]
        notes.replace_all(notes.snapshot()["notes"], facts)
        self.say("Память сохранена.")
        self.load()


class ReminderDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Новое напоминание")
        form = QFormLayout(self)
        form.setContentsMargins(18, 18, 18, 14)
        form.setSpacing(10)
        self.label = QLineEdit()
        self.label.setPlaceholderText("Например: позвонить маме")
        self.when = QDateTimeEdit(QDateTime.currentDateTime().addSecs(600))
        self.when.setCalendarPopup(True)
        self.when.setDisplayFormat("dd.MM.yyyy  HH:mm")
        form.addRow("Что напомнить", self.label)
        form.addRow("Когда", self.when)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel, ok = _btn("Отмена"), _btn("Добавить", True)
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        form.addRow(row)
        self.setMinimumWidth(380)


class RemindersTab(QWidget):
    """Активные таймеры и напоминания (их же ставит и показывает голос)."""

    def __init__(self, on_status):
        super().__init__()
        self.say = on_status
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 14, 14, 14)
        info = QLabel("Таймеры и напоминания, которые ещё не сработали. Сработавшие исчезают из списка сами.")
        info.setObjectName("muted")
        info.setWordWrap(True)
        v.addWidget(info)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Когда", "Тип", "Что"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 190)
        self.table.setColumnWidth(1, 120)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        v.addWidget(self.table, 1)
        row = QHBoxLayout()
        add, rm, ref = _btn("Добавить…", True), _btn("Удалить выбранное"), _btn("Обновить")
        add.clicked.connect(self._add)
        rm.clicked.connect(self._remove)
        ref.clicked.connect(self.load)
        row.addWidget(add)
        row.addWidget(rm)
        row.addWidget(ref)
        row.addStretch(1)
        v.addLayout(row)

    def load(self):
        self.table.setRowCount(0)
        for it in SCHEDULER.items():
            r = self.table.rowCount()
            self.table.insertRow(r)
            a = QTableWidgetItem(fmt_when(it["when"]))
            a.setData(Qt.UserRole, it["id"])
            self.table.setItem(r, 0, a)
            self.table.setItem(r, 1, QTableWidgetItem("таймер" if it.get("kind") == "timer" else "напоминание"))
            self.table.setItem(r, 2, QTableWidgetItem(it.get("label") or "без названия"))

    def _add(self):
        d = ReminderDialog(self)
        if d.exec() == QDialog.Accepted:
            when = d.when.dateTime().toSecsSinceEpoch()
            import time
            if when <= time.time():
                QMessageBox.information(self, "Напоминание", "Это время уже прошло.")
                return
            SCHEDULER.add(when, d.label.text().strip()[:80], "reminder")
            self.say("Напоминание добавлено.")
            self.load()

    def _remove(self):
        r = self.table.currentRow()
        if r >= 0:
            SCHEDULER.remove([self.table.item(r, 0).data(Qt.UserRole)])
            self.load()

    def showEvent(self, e):
        super().showEvent(e)
        self.load()


class FilesTab(QWidget):
    """Все файлы и папки программы: открыть или показать в проводнике."""

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 10, 14, 14)
        v.setSpacing(0)
        data = Path(settings.get("DATA_DIR"))
        items = [
            ("Заметки и память", data / "notes.json", "Правятся на вкладках выше"),
            ("Таймеры и напоминания", data / "reminders.json", "Пока программа запущена, лучше править на вкладке «Напоминания»"),
            ("Диалоги", Path(settings.get("SESSIONS_DIR")), "По одному файлу .jsonl на диалог"),
            ("Настройки", cfg.USER_SETTINGS_FILE, "Только то, что отличается от умолчаний"),
            ("Ключ OpenRouter", settings.ENV_FILE, "Секрет, не публикуйте этот файл"),
            ("Журнал работы", cfg.BASE / "assistant.log", "Что слышал и делал ассистент"),
            ("Кэш моделей", cfg.CACHE, "Скачанные модели голоса и распознавания"),
            ("Папка программы", cfg.BASE, ""),
        ]
        for title, path, note in items:
            fr = QFrame()
            fr.setObjectName("row")
            h = QHBoxLayout(fr)
            h.setContentsMargins(0, 10, 0, 10)
            col = QVBoxLayout()
            col.setSpacing(2)
            t = QLabel(title)
            t.setObjectName("h2")
            p = QLabel(str(path) + ("" if path.exists() else "   (ещё не создан)"))
            p.setObjectName("meta")
            p.setTextInteractionFlags(Qt.TextSelectableByMouse)
            col.addWidget(t)
            col.addWidget(p)
            if note:
                n = QLabel(note)
                n.setObjectName("muted")
                col.addWidget(n)
            h.addLayout(col, 1)
            if path.is_file() or (path.suffix and not path.is_dir()):
                o = _btn("Открыть")
                o.setEnabled(path.exists())
                o.clicked.connect(lambda _=False, pp=path: open_path(pp))
                h.addWidget(o)
            f = _btn("В папке" if path.is_file() or path.suffix else "Открыть папку")
            f.clicked.connect(lambda _=False, pp=path: reveal(pp) if pp.exists() else open_path(pp.parent))
            h.addWidget(f)
            v.addWidget(fr)
        v.addStretch(1)


class DataPage(QWidget):
    def __init__(self, ui):
        super().__init__()
        self.setObjectName("page")
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 22, 28, 22)
        v.setSpacing(10)
        title = QLabel("Данные и файлы")
        title.setObjectName("title")
        v.addWidget(title)
        self.msg = QLabel("")
        self.msg.setObjectName("muted")
        tabs = QTabWidget()
        self.notes, self.facts, self.rem = NotesTab(self.say), FactsTab(self.say), RemindersTab(self.say)
        tabs.addTab(self.notes, "Заметки")
        tabs.addTab(self.facts, "Память")
        tabs.addTab(self.rem, "Напоминания")
        tabs.addTab(FilesTab(), "Файлы")
        v.addWidget(tabs, 1)
        v.addWidget(self.msg)
        self.load()

    def say(self, text):
        self.msg.setText(text)

    def is_dirty(self):
        return self.notes.dirty or self.facts.dirty

    def save_all(self):
        if self.notes.dirty:
            self.notes.save()
        if self.facts.dirty:
            self.facts.save()

    def load(self, force=False):
        """Перечитать файл. Вкладки с несохранёнными правками не трогаем (иначе правки пропадали бы
        при переходе на другую страницу настроек и возврате), force=True перечитывает всё."""
        if force or not self.notes.dirty:
            self.notes.load()
        if force or not self.facts.dirty:
            self.facts.load()

    def showEvent(self, e):
        super().showEvent(e)
        self.load()
