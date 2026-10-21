# -*- coding: utf-8 -*-
"""Лента сообщений: «пузыри» с markdown, автопрокрутка, подгонка размера под текст."""
import math

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPalette, QTextCharFormat, QTextCursor, QTextFormat
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QScrollArea, QTextBrowser, QVBoxLayout, QWidget)

from . import theme


class AutoText(QTextBrowser):
    """Текст без рамки и прокрутки, высота и ширина подгоняются под содержимое."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setOpenExternalLinks(True)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        self.document().setDocumentMargin(0)
        pal = self.palette()
        pal.setColor(QPalette.Link, QColor(theme.C["link"]))
        self.setPalette(pal)

    def fit(self, max_w):
        doc = self.document()
        doc.setTextWidth(max(40, max_w))
        w = min(max_w, math.ceil(doc.idealWidth()) + 2)
        doc.setTextWidth(w)
        self.setFixedSize(int(w), int(math.ceil(doc.size().height())) + 2)


def style_markdown(doc):
    """Qt рисует блоки кода без оформления: добавляем фон, моноширинный шрифт и перенос длинных строк."""
    block = doc.begin()
    prev_code = False
    while block.isValid():
        fmt = block.blockFormat()
        is_code = fmt.hasProperty(QTextFormat.Property.BlockCodeFence) or fmt.nonBreakableLines()
        if is_code:
            nxt = block.next()
            last = not (nxt.isValid() and (nxt.blockFormat().hasProperty(QTextFormat.Property.BlockCodeFence)
                                           or nxt.blockFormat().nonBreakableLines()))
            fmt.setNonBreakableLines(False)
            fmt.setBackground(QColor(theme.C["code"]))
            fmt.setLeftMargin(10)
            fmt.setRightMargin(10)
            fmt.setTopMargin(0 if prev_code else 6)
            fmt.setBottomMargin(8 if last else 0)
            cur = QTextCursor(block)
            cur.setBlockFormat(fmt)
            cur.movePosition(QTextCursor.StartOfBlock)
            cur.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
            cf = QTextCharFormat()
            cf.setFontFamilies([f.strip('" ') for f in theme.MONO_FAMILY.split(",")])
            cur.mergeCharFormat(cf)
        prev_code = is_code
        block = block.next()


class MessageBubble(QWidget):
    """Одно сообщение: подпись (кто, когда) и пузырь с текстом."""

    def __init__(self, role, meta="", markdown=False, parent=None):
        super().__init__(parent)
        self.role, self.markdown, self.max_w = role, markdown, 600
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(3)
        self.meta = QLabel(meta)
        self.meta.setObjectName("meta")
        self.frame = QFrame()
        self.frame.setObjectName("bubble")
        self.frame.setProperty("role", role)
        fl = QVBoxLayout(self.frame)
        fl.setContentsMargins(14, 10, 14, 10)
        fl.setSpacing(5)
        self.text = AutoText()
        self.status = QLabel()
        self.status.setObjectName("status")
        self.status.hide()
        fl.addWidget(self.text)
        fl.addWidget(self.status)
        col.addWidget(self.meta)
        col.addWidget(self.frame)
        side = Qt.AlignRight if role == "user" else Qt.AlignLeft
        col.setAlignment(self.meta, side)
        col.setAlignment(self.frame, side)
        if role == "user":
            outer.addStretch(1)
            outer.addLayout(col)
        else:
            outer.addLayout(col)
            outer.addStretch(1)
        self.meta.setVisible(bool(meta))
        if role == "user":
            pal = self.text.palette()
            pal.setColor(QPalette.Text, QColor("#ffffff"))
            pal.setColor(QPalette.Link, QColor("#ffffff"))
            self.text.setPalette(pal)

    def set_text(self, text):
        doc = self.text.document()
        if self.markdown and text:
            doc.setMarkdown(text)
            style_markdown(doc)
        else:
            doc.setPlainText(text)
        self.text.setVisible(bool(text) or not self.status.isVisible())
        self.fit(self.max_w)

    def text_value(self):
        return self.text.document().toPlainText()

    def set_status(self, text):
        self.status.setText(text)
        self.status.setVisible(bool(text))
        self.text.setVisible(bool(self.text.document().toPlainText()) or not text)

    def fit(self, max_w):
        self.max_w = max_w
        self.text.fit(max_w - 28)


class ChatView(QScrollArea):
    """Прокручиваемая лента. Если вы у нижнего края, новые сообщения прокручивают её сами;
    если пролистали вверх, чтобы перечитать, лента остаётся на месте."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.body.setObjectName("page")
        self.lay = QVBoxLayout(self.body)
        self.lay.setContentsMargins(28, 20, 28, 20)
        self.lay.setSpacing(14)
        self.lay.addStretch(1)
        self.setWidget(self.body)
        self.bubbles = []
        self._stick = True
        sb = self.verticalScrollBar()
        sb.valueChanged.connect(lambda v: setattr(self, "_stick", v >= sb.maximum() - 8))
        sb.rangeChanged.connect(lambda _lo, hi: self._stick and sb.setValue(hi))
        self._refit = QTimer(self)
        self._refit.setSingleShot(True)
        self._refit.timeout.connect(self.fit_all)
        self.hint = QLabel("", self.viewport())
        self.hint.setObjectName("muted")
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.setWordWrap(True)

    def set_hint(self, text):
        self.hint.setText(text)
        self._place_hint()

    def _place_hint(self):
        self.hint.setVisible(not self.bubbles and bool(self.hint.text()))
        w = min(480, self.viewport().width() - 40)
        self.hint.setGeometry((self.viewport().width() - w) // 2, self.viewport().height() // 2 - 40, w, 80)

    def max_w(self):
        return max(240, min(820, int((self.viewport().width() - 56) * 0.9)))

    def add_message(self, role, text, meta="", markdown=False):
        b = MessageBubble(role, meta, markdown)
        b.fit(self.max_w())
        b.set_text(text)
        self.lay.insertWidget(self.lay.count() - 1, b)
        self.bubbles.append(b)
        self._place_hint()
        return b

    def clear(self):
        for b in self.bubbles:
            b.setParent(None)
            b.deleteLater()
        self.bubbles = []
        self._stick = True
        self._place_hint()

    def scroll_to_end(self):
        self._stick = True
        QTimer.singleShot(0, lambda: self.verticalScrollBar().setValue(self.verticalScrollBar().maximum()))

    def fit_all(self):
        w = self.max_w()
        for b in self.bubbles:
            b.fit(w)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._refit.start(25)
        self._place_hint()
