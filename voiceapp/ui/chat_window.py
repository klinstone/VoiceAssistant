# -*- coding: utf-8 -*-
"""Окно чата: список диалогов слева, лента и поле ввода справа.
Окно ничего не решает само: оно показывает brain.session (активный диалог) и события из bus.
Клик по диалогу в списке делает его активным: и голос, и текст идут уже в него (зелёная точка)."""
import datetime
import threading

from PySide6.QtCore import QPointF, QRect, QSize, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMenu,
                               QMessageBox, QPlainTextEdit, QPushButton, QStyle, QStyledItemDelegate, QVBoxLayout,
                               QWidget)

from .. import config as cfg
from .. import sessions
from ..log import log
from ..reminders import plural
from . import theme
from .chat_view import ChatView
from .widgets import RoundButton, reveal

HINT = "Enter — отправить, Shift+Enter — новая строка"


def fmt_when(dt):
    today = datetime.date.today()
    if dt.date() == today:
        return f"сегодня, {dt:%H:%M}"
    if dt.date() == today - datetime.timedelta(days=1):
        return f"вчера, {dt:%H:%M}"
    return f"{dt:%d.%m %H:%M}"


class SessionDelegate(QStyledItemDelegate):
    """Строка списка: зелёная точка у активного диалога, заголовок и подпись."""

    def sizeHint(self, option, index):
        return QSize(0, 54)

    def paint(self, p, option, index):
        d = index.data(Qt.UserRole)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = option.rect.adjusted(8, 2, -8, -2)
        if option.state & QStyle.State_Selected:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.C["sel"]))
            p.drawRoundedRect(r, 9, 9)
        elif option.state & QStyle.State_MouseOver:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.C["hover"]))
            p.drawRoundedRect(r, 9, 9)
        if d["active"]:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.C["green"]))
            p.drawEllipse(QPointF(r.left() + 15, r.center().y()), 4.5, 4.5)
        left = r.left() + 30
        width = r.width() - 40
        f = QFont(option.font)
        f.setWeight(QFont.DemiBold if d["active"] else QFont.Normal)
        p.setFont(f)
        p.setPen(QPen(QColor(theme.C["text"])))
        title = QFontMetrics(f).elidedText(d["title"], Qt.ElideRight, width)
        p.drawText(QRect(left, r.top() + 7, width, 20), Qt.AlignVCenter | Qt.AlignLeft, title)
        f2 = QFont(option.font)
        f2.setPointSizeF(max(7.0, option.font.pointSizeF() - 1.5))
        p.setFont(f2)
        p.setPen(QPen(QColor(theme.C["muted"])))
        sub = QFontMetrics(f2).elidedText(d["sub"], Qt.ElideRight, width)
        p.drawText(QRect(left, r.top() + 27, width, 18), Qt.AlignVCenter | Qt.AlignLeft, sub)
        p.restore()


class Composer(QPlainTextEdit):
    """Поле ввода: растёт до шести строк, Enter отправляет, Shift+Enter — новая строка.
    Пока вы говорите голосом, сюда серым текстом «печатается» то, что слышит Vosk."""
    submitted = Signal()
    DEFAULT = "Напишите сообщение…"

    def __init__(self):
        super().__init__()
        self.setObjectName("composer")
        self.setPlaceholderText(self.DEFAULT)
        self.setTabChangesFocus(True)
        self.document().documentLayout().documentSizeChanged.connect(self._resize)
        self._resize()

    def _resize(self, *_):
        lines = max(1, min(6, int(self.document().size().height())))
        self.setFixedHeight(lines * self.fontMetrics().lineSpacing() + 30)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not (e.modifiers() & Qt.ShiftModifier):
            self.submitted.emit()
            return
        super().keyPressEvent(e)

    def set_voice(self, text):
        self.setPlaceholderText(("🎤  " + text) if text else self.DEFAULT)


class ChatWindow(QMainWindow):
    def __init__(self, ui):
        super().__init__()
        self.ui = ui
        self.brain = ui.services.brain
        self.busy = False
        self.stream = None              # пузырь ответа, который сейчас печатается
        self.stream_turn = None
        self.reload_turn = 0            # события этого и более старых запросов окно уже показало при перезагрузке
        self.buf = ""
        self.infos = []
        self._render = QTimer(self)
        self._render.setSingleShot(True)
        self._render.timeout.connect(self._flush_stream)
        self.setWindowTitle("Ассистент")
        self.setWindowIcon(ui.icon("ready"))
        self.resize(1100, 740)
        self.setMinimumSize(760, 480)
        self._build()
        b = ui.bridge
        b.user_message.connect(self.on_user_message)
        b.assistant_start.connect(self.on_start)
        b.token.connect(self.on_token)
        b.status.connect(self.on_status)
        b.done.connect(self.on_done)
        b.error.connect(self.on_error)
        b.session_changed.connect(self.on_session_changed)
        b.sessions_updated.connect(self.refresh_list)
        b.voice_partial.connect(self.composer.set_voice)
        b.state.connect(self.on_state)
        self.reload()
        last = ui.last_state()
        if last:
            self.on_state(*last)

    # ------------------------------ интерфейс ------------------------------
    def _build(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(284)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 14, 0, 10)
        sl.setSpacing(8)
        top = QHBoxLayout()
        top.setContentsMargins(16, 0, 14, 0)
        t = QLabel("Диалоги")
        t.setObjectName("h2")
        top.addWidget(t)
        top.addStretch(1)
        sl.addLayout(top)
        self.new_btn = QPushButton("＋  Новый диалог")
        self.new_btn.setObjectName("primary")
        self.new_btn.setCursor(Qt.PointingHandCursor)
        self.new_btn.clicked.connect(self.new_chat)
        nb = QHBoxLayout()
        nb.setContentsMargins(14, 0, 14, 0)
        nb.addWidget(self.new_btn)
        sl.addLayout(nb)
        self.list = QListWidget()
        self.list.setItemDelegate(SessionDelegate(self.list))
        self.list.setMouseTracking(True)
        self.list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._list_menu)
        self.list.itemClicked.connect(self._picked)
        self.list.itemActivated.connect(self._picked)
        sl.addWidget(self.list, 1)
        self.settings_btn = QPushButton("⚙   Настройки")
        self.settings_btn.setObjectName("flat")
        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.settings_btn.clicked.connect(lambda: self.ui.open_settings())
        fb = QHBoxLayout()
        fb.setContentsMargins(10, 0, 10, 0)
        fb.addWidget(self.settings_btn)
        sl.addLayout(fb)
        lay.addWidget(side)

        right = QVBoxLayout()
        right.setSpacing(0)
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(64)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(26, 0, 22, 0)
        col = QVBoxLayout()
        col.setSpacing(1)
        col.setContentsMargins(0, 10, 0, 10)
        self.title = QLabel("Новый диалог")
        self.title.setObjectName("title")
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("meta")
        col.addWidget(self.title)
        col.addWidget(self.subtitle)
        hl.addLayout(col, 1)
        self.chip = QLabel("")
        self.chip.setTextFormat(Qt.RichText)
        hl.addWidget(self.chip)
        right.addWidget(header)

        self.view = ChatView()
        right.addWidget(self.view, 1)

        bar = QFrame()
        bar.setObjectName("inputbar")
        bl = QVBoxLayout(bar)
        bl.setContentsMargins(26, 8, 26, 10)
        bl.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.composer = Composer()
        self.composer.submitted.connect(self.send)
        row.addWidget(self.composer, 1, Qt.AlignBottom)
        self.send_btn = RoundButton("send")
        self.send_btn.clicked.connect(self._send_or_stop)
        row.addWidget(self.send_btn, 0, Qt.AlignBottom)
        bl.addLayout(row)
        self.hint = QLabel(HINT)
        self.hint.setObjectName("meta")
        bl.addWidget(self.hint)
        right.addWidget(bar)
        lay.addLayout(right, 1)
        self.composer.setFocus()

    # ------------------------------ показ диалога ------------------------------
    def reload(self):
        """Перерисовать ленту из активного диалога (и из ответа, который прямо сейчас печатается)."""
        self.view.clear()
        self._render.stop()
        self.stream, self.stream_turn, self.buf = None, None, ""
        self.reload_turn = self.brain.turn
        msgs = sessions.load_messages(self.brain.session.path)
        for m in msgs:
            self._add_saved(m)
        infl = self.brain.inflight
        if infl:
            self._add_user(infl["user"], infl["src"], datetime.datetime.now())
            self._begin_stream(infl["turn"], infl["src"])
            if infl["answer"]:
                self.buf = infl["answer"]
                self._flush_stream()
        self._set_busy(infl is not None)
        if self.ui.services.voice:
            self.view.set_hint(f"Пустой диалог\nСкажите «{cfg.WAKE_PHRASE}» или напишите сообщение ниже")
        else:                                       # режим --chat: микрофона нет
            self.view.set_hint("Пустой диалог\nНапишите сообщение ниже")
        self.view.scroll_to_end()
        self._update_header(msgs)
        self.refresh_list(keep_scroll=False)        # диалог сменился: список должен показать активный

    def _update_header(self, msgs=None):
        if msgs is None:
            msgs = sessions.load_messages(self.brain.session.path)
        first = next((m["content"] for m in msgs if m["role"] == "user"), "")
        self.title.setText(" ".join(first.split())[:70] if first else "Новый диалог")
        n = len(msgs)
        self.subtitle.setText(f"{n} {plural(n, ('реплика', 'реплики', 'реплик'))} · активный диалог" if n
                              else "активный диалог")

    def _stamp(self, iso):
        return iso[11:16] if len(iso) >= 16 else ""

    def _add_saved(self, m):
        voice = m.get("src") == "voice"
        stamp = self._stamp(m.get("t", ""))
        if m["role"] == "user":
            self.view.add_message("user", m["content"], " · ".join(x for x in ("Вы", stamp, "голос" if voice else "") if x))
        else:
            self.view.add_message("assistant", m["content"], " · ".join(x for x in ("Ассистент", stamp) if x),
                                  markdown=not voice)

    def _add_user(self, text, src, when):
        meta = " · ".join(x for x in ("Вы", f"{when:%H:%M}", "голос" if src == "voice" else "") if x)
        self.view.add_message("user", text, meta)
        self.view.scroll_to_end()

    def _begin_stream(self, turn, src):
        meta = f"Ассистент · {datetime.datetime.now():%H:%M}"
        self.stream = self.view.add_message("assistant", "", meta, markdown=(src != "voice"))
        self.stream.set_status("Думаю…")
        self.stream_turn = turn
        self.buf = ""

    def _flush_stream(self):
        if self.stream is not None:
            self.stream.set_status("")
            self.stream.set_text(self.buf)

    # ------------------------------ список диалогов ------------------------------
    def refresh_list(self, keep_scroll=True):
        """keep_scroll: список перерисовывается после каждого ответа, и без этого он «прыгал» бы к активному диалогу,
        пока вы листаете старые."""
        sb = self.list.verticalScrollBar()
        pos = sb.value()
        cur = str(self.brain.session.path)
        infos = []
        if self.brain.is_draft:
            infos.append({"path": cur, "title": "Новый диалог", "sub": "пока пусто", "draft": True})
        for i in sessions.list_sessions():
            sub = f"{fmt_when(i.when)} · {i.count} {plural(i.count, ('реплика', 'реплики', 'реплик'))}"
            infos.append({"path": str(i.path), "title": i.title, "sub": sub, "draft": False})
        self.infos = infos
        self.list.blockSignals(True)
        self.list.clear()
        for d in infos:
            d["active"] = d["path"] == cur
            it = QListWidgetItem()
            it.setData(Qt.UserRole, d)
            self.list.addItem(it)
            if d["active"]:
                self.list.setCurrentItem(it)
        self.list.blockSignals(False)
        if keep_scroll:
            self.list.doItemsLayout()               # без этого диапазон прокрутки ещё нулевой, и позиция обрезалась бы до 0
            sb.setValue(pos)

    def _picked(self, item):
        d = item.data(Qt.UserRole)
        if d["path"] == str(self.brain.session.path):
            return
        if not self.brain.open_session(d["path"]):
            self.flash("Дождитесь окончания ответа, потом переключайте диалог.")
            self.refresh_list()

    def new_chat(self):
        if not self.brain.new_session(wait=False):
            self.flash("Дождитесь окончания ответа.")
        self.composer.setFocus()

    def _list_menu(self, pos):
        it = self.list.itemAt(pos)
        if it is None:
            return
        d = it.data(Qt.UserRole)
        m = QMenu(self)
        a_open = m.addAction("Показать файл в папке")
        a_del = m.addAction("Удалить диалог")
        a_open.setEnabled(not d["draft"])
        a_del.setEnabled(not d["draft"])
        chosen = m.exec(self.list.mapToGlobal(pos))
        if chosen is a_open:
            reveal(d["path"])
        elif chosen is a_del:
            if QMessageBox.question(self, "Удалить диалог", f"Удалить диалог «{d['title']}»? Это нельзя отменить.") \
                    == QMessageBox.Yes:
                if not self.brain.delete_session(d["path"]):
                    self.flash("Дождитесь окончания ответа.")

    # ------------------------------ отправка ------------------------------
    def flash(self, text, ms=3500):
        self.hint.setText(text)
        QTimer.singleShot(ms, lambda: self.hint.setText(HINT))

    def _set_busy(self, busy):
        self.busy = busy
        self.send_btn.set_kind("stop" if busy else "send")

    def _send_or_stop(self):
        if self.busy:
            self.ui.services.brain.cancel()
            if self.ui.services.silence:
                self.ui.services.silence()
        else:
            self.send()

    def send(self):
        text = self.composer.toPlainText().strip()
        if not text:
            return
        if self.busy:
            self.flash("Ассистент ещё отвечает. Дождитесь ответа или нажмите «стоп».")
            return
        self.composer.clear()
        self._set_busy(True)
        threading.Thread(target=self._ask, args=(text,), daemon=True, name="chat-ask").start()

    def _ask(self, text):
        try:
            self.brain.ask(text, src="text")
        except Exception as e:                  # подробности уже в событии ASSISTANT_ERROR
            log(f"Чат: запрос не удался: {e}")

    # ------------------------------ события ------------------------------
    @Slot(int, str, str)
    def on_user_message(self, turn, text, src):
        if turn <= self.reload_turn:
            return
        self._add_user(text, src, datetime.datetime.now())
        self._set_busy(True)

    @Slot(int, str)
    def on_start(self, turn, src):
        if turn <= self.reload_turn and self.stream_turn != turn:
            return
        if self.stream_turn != turn:
            self._begin_stream(turn, src)
            self.view.scroll_to_end()

    @Slot(int, str)
    def on_token(self, turn, full):
        if self.stream is None or self.stream_turn != turn:
            return
        self.buf = full
        if not self._render.isActive():
            self._render.start(45)

    @Slot(int, str)
    def on_status(self, turn, text):
        if self.stream is not None and self.stream_turn == turn:
            self._render.stop()
            self.stream.set_text(self.buf)
            self.stream.set_status(text)

    @Slot(int, str)
    def on_done(self, turn, text):
        if self.stream is not None and self.stream_turn == turn:
            self._render.stop()
            self.stream.set_status("")
            self.stream.set_text(text or "(ответа нет)")
            self.stream, self.stream_turn = None, None
        self._set_busy(False)
        self._update_header()
        self.refresh_list()

    @Slot(int, str)
    def on_error(self, turn, message):
        if self.stream is not None and self.stream_turn == turn:
            self._render.stop()
            if not self.buf.strip():
                self.view.bubbles.remove(self.stream)
                self.stream.setParent(None)
                self.stream.deleteLater()
            else:
                self.stream.set_status("")
            self.stream, self.stream_turn = None, None
        hint = ""
        if "API_KEY" in message or "ключ" in message.lower():
            hint = "\n\nВведите ключ: Настройки → Модель и ключ."
        self.view.add_message("error", "Не удалось получить ответ: " + message + hint, "Ошибка")
        self.view.scroll_to_end()
        self._set_busy(False)

    @Slot(str)
    def on_session_changed(self, _path):
        self.reload()

    @Slot(str, str)
    def on_state(self, state, text):
        color = theme.STATE_COLORS.get(state, theme.C["muted"])
        self.chip.setText(f'<span style="color:{color}">●</span>&nbsp;<span style="color:{theme.C["muted"]}">{text}</span>')

    def closeEvent(self, e):
        if self.ui.standalone:
            if self.ui.quit():
                e.accept()
            else:                                   # в окне настроек остались несохранённые правки, и пользователь отказался выходить
                e.ignore()
        else:
            self.ui.remember_geometry(self, "chat")
            e.ignore()
            self.hide()
