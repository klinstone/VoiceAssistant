# -*- coding: utf-8 -*-
"""Редакторы значений для окна настроек. У каждого одинаковый интерфейс: get(), set(v), connect(callback)."""
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QCompleter, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from .widgets import Combo, FloatSpin, IntSpin, Switch

TOOL_TITLES = {
    "web_search": "Поиск в интернете", "read_webpage": "Чтение страниц и субтитров Ютуба", "get_weather": "Погода",
    "get_exchange_rate": "Курсы валют и криптовалют", "world_time": "Время в других городах",
    "calculate": "Калькулятор", "timer": "Таймеры и напоминания", "notes": "Заметки и списки",
    "remember": "Долговременная память о вас", "clipboard": "Буфер обмена", "look_at_screen": "Взгляд на экран",
    "pc_control": "Управление ПК (громкость, медиа, блокировка)", "open_target": "Запуск программ и сайтов",
    "system_status": "Состояние компьютера"}

WIDE = {"strlist", "tools", "dict", "text"}


class Ed:
    """Обёртка: виджет + как прочитать значение + как его записать + сигнал изменения."""

    def __init__(self, widget, get, set_, signal):
        self.widget, self.get, self.set, self._signal = widget, get, set_, signal

    def connect(self, cb):
        self._signal.connect(lambda *_: cb())


def _btn(text, tip="", name=""):
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    if tip:
        b.setToolTip(tip)
    if name:
        b.setObjectName(name)
    return b


# ------------------------------ составные редакторы ------------------------------
class SecretEdit(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.line = QLineEdit()
        self.line.setEchoMode(QLineEdit.Password)
        self.line.setPlaceholderText("sk-or-v1-…")
        self.line.textChanged.connect(lambda _: self.changed.emit())
        self.eye = _btn("Показать")
        self.eye.setCheckable(True)
        self.eye.toggled.connect(lambda on: (self.line.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password),
                                             self.eye.setText("Скрыть" if on else "Показать")))
        lay.addWidget(self.line, 1)
        lay.addWidget(self.eye)


class StrList(QWidget):
    """Список строк: правка двойным щелчком, добавление, удаление, порядок."""
    changed = Signal()

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        self.list = QListWidget()
        self.list.setObjectName("inner")
        self.list.setFixedHeight(126)
        self.list.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.list.itemChanged.connect(lambda _: self.changed.emit())
        v.addWidget(self.list)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Новая строка…")
        self.input.returnPressed.connect(self._add)
        add, up, down, rm = _btn("Добавить"), _btn("↑", "Выше"), _btn("↓", "Ниже"), _btn("Удалить")
        add.clicked.connect(self._add)
        up.clicked.connect(lambda: self._move(-1))
        down.clicked.connect(lambda: self._move(1))
        rm.clicked.connect(self._remove)
        row.addWidget(self.input, 1)
        for b in (add, up, down, rm):
            row.addWidget(b)
        v.addLayout(row)

    def _item(self, text):
        it = QListWidgetItem(text)
        it.setFlags(it.flags() | Qt.ItemIsEditable)
        return it

    def _add(self):
        t = self.input.text().strip()
        if t:
            self.list.addItem(self._item(t))
            self.input.clear()
            self.changed.emit()

    def _remove(self):
        r = self.list.currentRow()
        if r >= 0:
            self.list.takeItem(r)
            self.changed.emit()

    def _move(self, d):
        r = self.list.currentRow()
        if r < 0 or not 0 <= r + d < self.list.count():
            return
        it = self.list.takeItem(r)
        self.list.insertItem(r + d, it)
        self.list.setCurrentRow(r + d)
        self.changed.emit()

    def get(self):
        out = [self.list.item(i).text().strip() for i in range(self.list.count())]
        return [t for t in out if t]

    def set(self, values):
        self.list.blockSignals(True)
        self.list.clear()
        for t in values or []:
            self.list.addItem(self._item(str(t)))
        self.list.blockSignals(False)


class ToolsBox(QWidget):
    """Галочки по инструментам: включён = модель его видит. Значение настройки — список ОТКЛЮЧЁННЫХ."""
    changed = Signal()

    def __init__(self):
        super().__init__()
        from ..tools import tool_catalog
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(7)
        self.boxes = {}
        for name, desc in tool_catalog():
            row = QHBoxLayout()
            cb = QCheckBox(TOOL_TITLES.get(name, name))
            cb.setChecked(True)
            cb.toggled.connect(lambda _: self.changed.emit())
            code = QLabel(name)
            code.setObjectName("meta")
            row.addWidget(cb)
            row.addWidget(code)
            row.addStretch(1)
            v.addLayout(row)
            self.boxes[name] = cb

    def get(self):
        return [n for n, cb in self.boxes.items() if not cb.isChecked()]

    def set(self, disabled):
        for n, cb in self.boxes.items():
            cb.blockSignals(True)
            cb.setChecked(n not in (disabled or []))
            cb.blockSignals(False)


class DictTable(QWidget):
    """Таблица «название — значение» (свои программы и сайты)."""
    changed = Signal()

    def __init__(self, key_title, value_title, browse):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([key_title, value_title])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 220)
        self.table.verticalHeader().setVisible(False)
        self.table.setFixedHeight(170)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.itemChanged.connect(lambda _: self.changed.emit())
        v.addWidget(self.table)
        row = QHBoxLayout()
        row.setSpacing(6)
        add, rm = _btn("Добавить строку"), _btn("Удалить строку")
        add.clicked.connect(lambda: self._add_row("", ""))
        rm.clicked.connect(self._remove)
        row.addWidget(add)
        row.addWidget(rm)
        if browse:
            br = _btn("Выбрать файл…")
            br.clicked.connect(self._browse)
            row.addWidget(br)
        row.addStretch(1)
        v.addLayout(row)

    def _add_row(self, k, val):
        self.table.blockSignals(True)
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(k))
        self.table.setItem(r, 1, QTableWidgetItem(val))
        self.table.blockSignals(False)
        self.table.setCurrentCell(r, 0)
        self.changed.emit()

    def _remove(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)
            self.changed.emit()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выберите программу", "", "Программы (*.exe *.lnk *.bat *.cmd);;Все файлы (*)")
        if not path:
            return
        r = self.table.currentRow()
        if r < 0:
            self._add_row("", path)
        else:
            self.table.item(r, 1).setText(path)

    def get(self):
        out = {}
        for r in range(self.table.rowCount()):
            k = (self.table.item(r, 0).text() if self.table.item(r, 0) else "").strip()
            val = (self.table.item(r, 1).text() if self.table.item(r, 1) else "").strip()
            if k and val:
                out[k] = val
        return out

    def set(self, d):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for k, val in (d or {}).items():
            if isinstance(val, (list, tuple)):          # (главная, шаблон поиска): показываем шаблон
                val = val[1] if len(val) > 1 and val[1] else val[0]
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(str(k)))
            self.table.setItem(r, 1, QTableWidgetItem(str(val)))
        self.table.blockSignals(False)


def list_mics():
    try:
        import sounddevice as sd
        names = []
        for d in sd.query_devices():
            if d["max_input_channels"] > 0 and d["name"] not in names:
                names.append(d["name"])
        return names
    except Exception:
        return []


class ModelFetcher(QObject):
    """Список моделей OpenRouter (для «Основной модели» и «Модели для экрана»)."""
    done = Signal(list)
    failed = Signal(str)

    def run(self, vision):
        def work():
            try:
                import requests
                data = requests.get("https://openrouter.ai/api/v1/models", timeout=15).json().get("data", [])
                ids = []
                for m in data:
                    mods = (m.get("architecture") or {}).get("input_modalities") or []
                    if vision and "image" not in mods:
                        continue
                    ids.append(m["id"])
                self.done.emit(sorted(ids))
            except Exception as e:
                self.failed.emit(f"{type(e).__name__}: {str(e)[:100]}")
        threading.Thread(target=work, daemon=True).start()


# ------------------------------ фабрика ------------------------------
def make_editor(f):
    k = f.kind
    if k == "bool":
        w = Switch()
        return Ed(w, w.isChecked, w.setChecked, w.toggled)
    if k == "int":
        w = IntSpin()
        w.setRange(int(f.min), int(f.max))
        w.setSingleStep(int(f.step))
        w.setSuffix(f.suffix)
        return Ed(w, w.value, lambda v: w.setValue(int(round(float(v or 0)))), w.valueChanged)
    if k == "float":
        w = FloatSpin()
        w.setRange(f.min, f.max)
        w.setDecimals(f.decimals)
        w.setSingleStep(f.step)
        w.setSuffix(f.suffix)
        return Ed(w, lambda: round(w.value(), f.decimals), lambda v: w.setValue(float(v or 0)), w.valueChanged)
    if k == "str":
        w = QLineEdit()
        return Ed(w, lambda: w.text().strip(), lambda v: w.setText(str(v or "")), w.textChanged)
    if k == "secret":
        w = SecretEdit()
        return Ed(w, lambda: w.line.text().strip(), lambda v: w.line.setText(str(v or "")), w.changed)
    if k == "text":
        w = QPlainTextEdit()
        w.setFixedHeight(110)
        return Ed(w, lambda: w.toPlainText().strip(), lambda v: w.setPlainText(str(v or "")), w.textChanged)
    if k == "choice":
        w = Combo()
        for val, label in f.options:
            w.addItem(label, val)

        def set_choice(v):
            i = w.findData(v)
            if i < 0:
                w.addItem(str(v), v)
                i = w.count() - 1
            w.setCurrentIndex(i)
        return Ed(w, w.currentData, set_choice, w.currentIndexChanged)
    if k == "combo":
        w = Combo()
        w.setEditable(True)
        w.setMinimumWidth(300)
        labels = {label: val for val, label in f.options}
        for val, label in f.options:
            w.addItem(label)
        comp = QCompleter(w.model(), w)
        comp.setFilterMode(Qt.MatchContains)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        w.setCompleter(comp)

        def get_combo():
            t = w.currentText().strip()
            return labels.get(t, t)

        def set_combo(v):
            v = "" if v is None else str(v)
            w.setCurrentText(next((label for val, label in f.options if val == v), v))
        return Ed(w, get_combo, set_combo, w.currentTextChanged)
    if k == "mic":
        w = Combo()
        w.addItem("по умолчанию", None)
        for n in list_mics():
            w.addItem(n, n)

        def set_mic(v):
            i = w.findData(v)
            if i < 0:
                w.addItem(f"Устройство №{v}" if isinstance(v, int) else str(v), v)
                i = w.count() - 1
            w.setCurrentIndex(i)
        return Ed(w, w.currentData, set_mic, w.currentIndexChanged)
    if k == "strlist":
        w = StrList()
        return Ed(w, w.get, w.set, w.changed)
    if k == "tools":
        w = ToolsBox()
        return Ed(w, w.get, w.set, w.changed)
    if k == "dict":
        w = DictTable(f.key_title, f.value_title, f.browse)
        return Ed(w, w.get, w.set, w.changed)
    raise ValueError(f"неизвестный тип настройки: {k}")
