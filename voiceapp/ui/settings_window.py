# -*- coding: utf-8 -*-
"""Окно «Настройки». Страницы и строки строятся из voiceapp/schema.py.
Изменения применяются кнопкой «Сохранить» и сразу, без перезапуска, если у настройки нет пометки «нужен перезапуск»."""
import threading

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
                               QMessageBox, QPushButton, QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from .. import settings
from ..log import log
from ..schema import BY_KEY, FIELDS, GROUPS
from ..text_utils import norm_text
from .data_page import DataPage
from .editors import WIDE, ModelFetcher, make_editor


def _same(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) \
            and not isinstance(b, bool):
        return abs(float(a) - float(b)) < 1e-9
    if isinstance(a, tuple):
        a = list(a)
    if isinstance(b, tuple):
        b = list(b)
    return a == b


def _repolish(w):
    w.style().unpolish(w)
    w.style().polish(w)


class SettingRow(QFrame):
    changed = Signal()
    message = Signal(str)

    def __init__(self, f, ui, value, default):
        super().__init__()
        self.f, self.ui = f, ui
        self.setObjectName("row")
        self.ed = make_editor(f)
        self.ed.set(default)
        self.default = self.ed.get()                # значения «прогоняем» через редактор, чтобы сравнение было честным
        self.ed.set(value)
        self.saved = self.ed.get()
        wide = f.kind in WIDE

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 15, 0, 15)
        root.setSpacing(9)
        top = QHBoxLayout()
        top.setSpacing(22)
        left = QVBoxLayout()
        left.setSpacing(3)
        tl = QHBoxLayout()
        tl.setSpacing(8)
        title = QLabel(f.title)
        title.setObjectName("h2")
        tl.addWidget(title)
        if f.restart:
            badge = QLabel("нужен перезапуск")
            badge.setObjectName("badge")
            tl.addWidget(badge)
        tl.addStretch(1)
        left.addLayout(tl)
        if f.help:
            h = QLabel(f.help)
            h.setObjectName("muted")
            h.setWordWrap(True)
            left.addWidget(h)
        top.addLayout(left, 5)

        right = QHBoxLayout()
        right.setSpacing(8)
        if not wide:
            if f.kind in ("bool", "int", "float"):
                right.addStretch(1)
            right.addWidget(self.ed.widget, 1 if f.kind not in ("bool", "int", "float") else 0)
        if f.models:
            self.fetch_btn = QPushButton("Загрузить список")
            self.fetch_btn.setToolTip("Получить актуальные модели с OpenRouter"
                                      + (" (только с поддержкой изображений)" if f.models == "vision" else ""))
            self.fetch_btn.clicked.connect(self._fetch_models)
            right.addWidget(self.fetch_btn)
            self.fetcher = ModelFetcher()
            self.fetcher.done.connect(self._models_loaded)
            self.fetcher.failed.connect(self._models_failed)
        if f.test == "voice":
            self.test_btn = QPushButton("Проверить")
            self.test_btn.setToolTip("Произнести фразу выбранным голосом")
            self.test_btn.setEnabled(bool(ui.services.preview_voice))
            self.test_btn.clicked.connect(self._test_voice)
            self._enable_test.connect(self._reenable_test)
            right.addWidget(self.test_btn)
        self.reset_btn = QPushButton("↺")
        self.reset_btn.setObjectName("icon")
        self.reset_btn.setToolTip("Вернуть значение по умолчанию")
        self.reset_btn.setFixedWidth(34)
        self.reset_btn.clicked.connect(lambda: self.ed.set(self.default))
        right.addWidget(self.reset_btn)
        top.addLayout(right, 4)
        root.addLayout(top)
        if wide:
            root.addWidget(self.ed.widget)
        self.ed.connect(self._edited)
        self._refresh()

    # --- состояние ---
    def value(self):
        return self.ed.get()

    def is_dirty(self):
        return not _same(self.ed.get(), self.saved)

    def commit(self):
        self.saved = self.ed.get()
        self._refresh()

    def revert(self):
        self.ed.set(self.saved)

    def reload(self, value):
        self.ed.set(value)
        self.saved = self.ed.get()
        self._refresh()

    def _refresh(self):
        self.setProperty("dirty", self.is_dirty())
        _repolish(self)
        self.reset_btn.setEnabled(not _same(self.ed.get(), self.default))

    def _edited(self):
        self._refresh()
        self.changed.emit()

    def matches(self, q):
        q = q.lower()
        return q in (self.f.title + " " + self.f.help + " " + self.f.key).lower()

    # --- кнопки рядом с полем ---
    def _fetch_models(self):
        self.fetch_btn.setEnabled(False)
        self.fetch_btn.setText("Загружаю…")
        self.fetcher.run(self.f.models == "vision")

    @Slot(str)
    def _models_failed(self, err):
        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("Загрузить список")
        self.message.emit("Список не загрузился: " + err)

    @Slot(list)
    def _models_loaded(self, ids):
        cur = self.ed.get()
        w = self.ed.widget
        w.blockSignals(True)
        w.clear()
        w.addItems(ids)
        w.setCurrentText(cur)
        w.blockSignals(False)
        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("Загрузить список")
        self.message.emit(f"Загружено моделей: {len(ids)}. Начните вводить название, чтобы найти нужную.")

    def _test_voice(self):
        speaker = self.ed.get()
        self.test_btn.setEnabled(False)
        self.message.emit("Проверяю голос…")

        def work():
            try:
                self.ui.services.preview_voice("Привет! Так звучит этот голос.", speaker)
                self.message.emit("")
            except Exception as e:
                self.message.emit(f"Не удалось проверить голос: {e}")
            finally:
                self._enable_test.emit()
        threading.Thread(target=work, daemon=True).start()

    _enable_test = Signal()

    @Slot()
    def _reenable_test(self):
        self.test_btn.setEnabled(bool(self.ui.services.preview_voice))


class SettingsWindow(QMainWindow):
    def __init__(self, ui):
        super().__init__()
        self.ui = ui
        self.rows = {}
        self.data_page = None
        self.pages = {}                              # id группы -> индекс страницы
        self.setWindowTitle("Настройки")
        self.setWindowIcon(ui.icon("ready"))
        self.resize(1020, 740)
        self.setMinimumSize(780, 520)
        self._build()
        self._update_footer()

    # ------------------------------ построение ------------------------------
    def _build(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        nav = QFrame()
        nav.setObjectName("nav")
        nav.setFixedWidth(236)
        nl = QVBoxLayout(nav)
        nl.setContentsMargins(0, 14, 0, 10)
        nl.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Найти настройку…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        sb = QHBoxLayout()
        sb.setContentsMargins(12, 0, 12, 0)
        sb.addWidget(self.search)
        nl.addLayout(sb)
        self.nav = QListWidget()
        self.nav.setObjectName("navlist")
        self.nav.currentRowChanged.connect(self._page_changed)
        nl.addWidget(self.nav, 1)
        reset_all = QPushButton("Сбросить все настройки…")
        reset_all.setObjectName("flat")
        reset_all.setCursor(Qt.PointingHandCursor)
        reset_all.clicked.connect(self._reset_all)
        rb = QHBoxLayout()
        rb.setContentsMargins(10, 0, 10, 0)
        rb.addWidget(reset_all)
        nl.addLayout(rb)
        outer.addWidget(nav)

        right = QVBoxLayout()
        right.setSpacing(0)
        self.banner = QFrame()
        self.banner.setObjectName("banner")
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(14, 8, 10, 8)
        bl.addWidget(QLabel("Часть настроек вступит в силу после перезапуска программы."), 1)
        rb2 = QPushButton("Перезапустить сейчас")
        rb2.setObjectName("primary")
        rb2.clicked.connect(self.ui.restart)
        bl.addWidget(rb2)
        bw = QHBoxLayout()
        bw.setContentsMargins(20, 12, 20, 0)
        bw.addWidget(self.banner)
        right.addLayout(bw)
        self.banner.setVisible(self.ui.pending_restart)

        self.stack = QStackedWidget()
        right.addWidget(self.stack, 1)

        self.footer = footer = QFrame()
        footer.setObjectName("footer")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(24, 10, 20, 10)
        fl.setSpacing(10)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        fl.addWidget(self.status, 1)
        self.revert_btn = QPushButton("Отменить изменения")
        self.revert_btn.clicked.connect(self.revert)
        self.save_btn = QPushButton("Сохранить")
        self.save_btn.setObjectName("primary")
        self.save_btn.clicked.connect(lambda: self.save())
        self.save_restart_btn = QPushButton("Сохранить и перезапустить")
        self.save_restart_btn.clicked.connect(lambda: self.save(restart=True))
        for b in (self.revert_btn, self.save_restart_btn, self.save_btn):
            fl.addWidget(b)
        right.addWidget(footer)
        outer.addLayout(right, 1)

        by_group = {}
        for f in FIELDS:
            by_group.setdefault(f.group, []).append(f)
        for gid, gtitle in GROUPS:
            if gid == "data":
                page = self.data_page = DataPage(self.ui)
            else:
                page = self._settings_page(gtitle, by_group.get(gid, []))
            self.pages[gid] = self.stack.addWidget(page)
            it = QListWidgetItem(gtitle)
            it.setData(Qt.UserRole, gid)
            self.nav.addItem(it)
        self.nav.setCurrentRow(0)

    def _value_of(self, f):
        return settings.env_get(f.key) if f.env else settings.get(f.key)

    def _settings_page(self, title, fields):
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("page")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.setSpacing(0)
        h = QLabel(title)
        h.setObjectName("title")
        lay.addWidget(h)
        lay.addSpacing(6)
        for f in fields:
            row = SettingRow(f, self.ui, self._value_of(f), settings.default(f.key))
            row.changed.connect(self._update_footer)
            row.message.connect(self.flash)
            self.rows[f.key] = row
            lay.addWidget(row)
        lay.addStretch(1)
        sc.setWidget(body)
        return sc

    # ------------------------------ навигация и поиск ------------------------------
    def select_page(self, gid):
        for i in range(self.nav.count()):
            if self.nav.item(i).data(Qt.UserRole) == gid:
                self.nav.setCurrentRow(i)

    def _page_changed(self, row):
        if row >= 0:
            gid = self.nav.item(row).data(Qt.UserRole)
            self.stack.setCurrentIndex(self.pages[gid])
            self.footer.setVisible(gid != "data")        # на странице данных у вкладок свои кнопки

    def _filter(self, text):
        q = text.strip()
        first_visible = None
        for i in range(self.nav.count()):
            gid = self.nav.item(i).data(Qt.UserRole)
            if gid == "data":
                visible = not q
            else:
                n = 0
                for f in FIELDS:
                    if f.group == gid:
                        ok = not q or self.rows[f.key].matches(q)
                        self.rows[f.key].setVisible(ok)
                        n += ok
                visible = n > 0
            self.nav.item(i).setHidden(not visible)
            if visible and first_visible is None:
                first_visible = i
        cur = self.nav.currentRow()
        if first_visible is not None and (cur < 0 or self.nav.item(cur).isHidden()):
            self.nav.setCurrentRow(first_visible)

    # ------------------------------ сохранение ------------------------------
    def dirty_rows(self):
        return [r for r in self.rows.values() if r.is_dirty()]

    def _update_footer(self):
        d = self.dirty_rows()
        self.revert_btn.setEnabled(bool(d))
        self.save_btn.setEnabled(bool(d))
        self.save_restart_btn.setVisible(any(r.f.restart for r in d))
        if d:
            self.status.setText(f"Изменено настроек: {len(d)}")
        elif not getattr(self, "_flashing", False):
            self.status.setText("Все изменения сохранены")

    @Slot(str)
    def flash(self, text):
        self._flashing = bool(text)
        self.status.setText(text)
        if not text:
            self._update_footer()

    def revert(self):
        for r in self.dirty_rows():
            r.revert()
        self._update_footer()

    def save(self, restart=False):
        changes, env = {}, {}
        for r in self.dirty_rows():
            v = r.value()
            key = r.f.key
            if key == "WAKE_PHRASE":                  # Vosk выдаёт строчные слова без знаков и без «ё»: сравнивать надо так же
                v = norm_text(str(v)) or settings.default(key)
            if key in ("SILERO_MODELS", "ASR_MODELS", "WAKE_PHRASE", "LLM_MODEL", "SEARCH_REGION", "DEFAULT_CITY") and not v:
                v = settings.default(key)
            if key == "NEW_SESSION_PHRASES":          # пустой список допустим: голосовой сброс просто выключен
                v = [p for p in (norm_text(str(x)) for x in v) if p]
            (env if r.f.env else changes)[key] = v
        try:
            if changes:
                settings.save(changes)
            for k, v in env.items():
                settings.env_set(k, v)
        except OSError as e:
            QMessageBox.warning(self, "Настройки", f"Не удалось сохранить: {e}")
            return False
        if env:
            self.ui.services.brain.reset_client()
        need_restart = any(BY_KEY[k].restart for k in (*changes, *env))
        for r in self.rows.values():
            key = r.f.key
            if key in changes or key in env:
                stored = changes[key] if key in changes else env[key]
                if _same(r.value(), stored):
                    r.commit()
                else:
                    r.reload(stored)                  # в поле показываем то, что реально сохранено (после нормализации)
        self.ui.settings_saved({*changes, *env})
        log("Настройки сохранены: " + ", ".join([*changes, *env]))
        if need_restart:
            self.ui.pending_restart = True
            self.banner.setVisible(True)
        self._update_footer()
        if restart:
            self.ui.restart()
        else:
            self.flash("Сохранено" + (": перезапустите программу, чтобы применить всё" if need_restart else " и применено"))
        return True

    def _reset_all(self):
        if not settings.user_values():
            self.flash("Все настройки и так по умолчанию.")
            return
        if QMessageBox.question(self, "Сбросить настройки",
                                "Вернуть все настройки к значениям по умолчанию?\nКлюч OpenRouter в .env не меняется.") \
                != QMessageBox.Yes:
            return
        keys = list(settings.user_values())
        settings.reset(keys)
        for k in keys:
            if k in self.rows:
                self.rows[k].reload(settings.default(k))
        if any(k in BY_KEY and BY_KEY[k].restart for k in keys):
            self.ui.pending_restart = True
            self.banner.setVisible(True)
        self.ui.settings_saved(set(keys))
        self._update_footer()
        self.flash("Настройки сброшены.")

    def confirm_close(self):
        """Если есть несохранённые правки (настройки или заметки/память на странице «Данные и файлы»),
        спрашивает, что с ними делать. False: пользователь передумал, закрывать нельзя."""
        rows = self.dirty_rows()
        data_dirty = self.data_page is not None and self.data_page.is_dirty()
        if not rows and not data_dirty:
            return True
        what = []
        if rows:
            what.append(f"настройки ({len(rows)})")
        if data_dirty:
            what.append("заметки или память")
        box = QMessageBox(self)
        box.setWindowTitle("Настройки")
        box.setText("Есть несохранённые изменения: " + ", ".join(what) + ".")
        save = box.addButton("Сохранить", QMessageBox.AcceptRole)
        drop = box.addButton("Не сохранять", QMessageBox.DestructiveRole)
        box.addButton("Отмена", QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save:
            if rows and not self.save():
                return False
            if data_dirty:
                self.data_page.save_all()
            return True
        if clicked is drop:
            self.revert()
            if data_dirty:
                self.data_page.load(force=True)
            return True
        return False

    def closeEvent(self, e):
        if not self.confirm_close():
            e.ignore()
            return
        self.ui.remember_geometry(self, "settings")
        e.accept()
