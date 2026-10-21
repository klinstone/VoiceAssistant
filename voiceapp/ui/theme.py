# -*- coding: utf-8 -*-
"""Тёмная тема: цвета и таблица стилей (QSS). Акцентный цвет и размер шрифта берутся из настроек."""

ACCENTS = {"Синий": "#4c8dff", "Фиолетовый": "#8b6cff", "Бирюзовый": "#1fb5c9",
           "Зелёный": "#2fb67c", "Оранжевый": "#ee8a45", "Розовый": "#e0568d"}

C = {"bg": "#10131a", "side": "#151922", "panel": "#1b202b", "bubble": "#212735", "border": "#2a3040",
     "text": "#e6e9ef", "muted": "#8b93a7", "green": "#3ddc84", "red": "#ff6b6b", "orange": "#ffb454",
     "hover": "#1c2230", "sel": "#242c3e", "code": "#0c0f15", "link": "#8ab4ff"}

STATE_COLORS = {"idle": "#7a8194", "ready": "#6c7bff", "listening": "#3ddc84",
                "thinking": "#ffb454", "speaking": "#4c9aff", "error": "#ff6b6b"}

FONT_FAMILY = '"Segoe UI", "Inter", "SF Pro Text", "Noto Sans", "DejaVu Sans", sans-serif'
MONO_FAMILY = '"Cascadia Mono", "Consolas", "DejaVu Sans Mono", monospace'


def accent_of(name):
    return ACCENTS.get(name, ACCENTS["Синий"])


def _mix(a, b, t):
    """Смешать два цвета #rrggbb: t=0 -> a, t=1 -> b."""
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(pa, pb))


_QSS = """
* { font-family: @font; outline: 0; }
QWidget { color: @text; }
QMainWindow, QDialog, QWidget#root, QWidget#page { background: @bg; }
QToolTip { background: @panel; color: @text; border: 1px solid @border; padding: 4px 6px; }

QFrame#sidebar { background: @side; border: none; border-right: 1px solid @border; }
QFrame#header { background: @bg; border: none; border-bottom: 1px solid @border; }
QFrame#inputbar { background: @bg; border: none; }
QFrame#nav { background: @side; border: none; border-right: 1px solid @border; }
QFrame#footer { background: @side; border: none; border-top: 1px solid @border; }
QFrame#row { background: transparent; border: none; border-bottom: 1px solid @border; }
QFrame#row[dirty="true"] { background: @hover; }
QFrame#banner { background: @bannerbg; border: 1px solid @accent; border-radius: 8px; }

QLabel { background: transparent; }
QLabel#muted, QLabel[muted="true"] { color: @muted; }
QLabel#title { font-size: @h1pt; font-weight: 600; }
QLabel#h2 { font-size: @h2pt; font-weight: 600; }
QLabel#meta { color: @muted; font-size: @smallpt; }
QLabel#badge { color: @orange; font-size: @smallpt; }
QLabel#status { color: @muted; font-style: italic; }

QFrame#bubble { border: none; border-radius: 14px; }
QFrame#bubble[role="user"] { background: @accent; }
QFrame#bubble[role="assistant"] { background: @bubble; }
QFrame#bubble[role="error"] { background: #3a2026; border: 1px solid #6b2f38; }
QTextBrowser { background: transparent; border: none; selection-background-color: @sel2; }
QFrame#bubble[role="user"] QTextBrowser { color: #ffffff; selection-background-color: @accent2; }

QPushButton { background: @panel; border: 1px solid @border; border-radius: 8px; padding: 7px 14px; }
QPushButton:hover { background: @sel; border-color: @border2; }
QPushButton:pressed { background: @hover; }
QPushButton:disabled { color: @muted; background: @side; }
QPushButton#primary { background: @accent; border: 1px solid @accent; color: white; font-weight: 600; }
QPushButton#primary:hover { background: @accent2; border-color: @accent2; }
QPushButton#primary:disabled { background: @sel; border-color: @sel; color: @muted; }
QPushButton#flat { background: transparent; border: none; color: @muted; padding: 6px 10px; text-align: left; }
QPushButton#flat:hover { background: @hover; color: @text; }
QPushButton#icon { background: transparent; border: none; border-radius: 6px; padding: 4px 8px; color: @muted; }
QPushButton#icon:hover { background: @sel; color: @text; }

QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTableWidget {
    background: @panel; border: 1px solid @border; border-radius: 8px; padding: 6px 9px;
    selection-background-color: @accent; selection-color: white; }
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border-color: @accent; }
QPlainTextEdit#composer { background: @panel; border: 1px solid @border; border-radius: 18px; padding: 9px 14px; }
QPlainTextEdit#composer:focus { border-color: @accent; }
QComboBox { padding: 5px 9px; }
QComboBox QAbstractItemView { background: @panel; border: 1px solid @border; selection-background-color: @sel;
    selection-color: @text; outline: 0; padding: 3px; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox::down-arrow { image: url(@img_down); width: 14px; height: 14px; }
QSpinBox, QDoubleSpinBox { padding: 5px 24px 5px 9px; }
QSpinBox::up-button, QDoubleSpinBox::up-button { subcontrol-origin: padding; subcontrol-position: top right;
    width: 22px; border: none; background: transparent; }
QSpinBox::down-button, QDoubleSpinBox::down-button { subcontrol-origin: padding; subcontrol-position: bottom right;
    width: 22px; border: none; background: transparent; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url(@img_up); width: 12px; height: 12px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url(@img_down); width: 12px; height: 12px; }

QListWidget { background: transparent; border: none; outline: 0; }
QListWidget#navlist::item { padding: 9px 12px; border-radius: 8px; margin: 1px 8px; }
QListWidget#navlist::item:hover { background: @hover; }
QListWidget#navlist::item:selected { background: @sel; color: @text; }
QListWidget#inner { background: @panel; border: 1px solid @border; border-radius: 8px; }
QListWidget#inner::item { padding: 5px 8px; }
QListWidget#inner::item:selected { background: @sel; }

QTableWidget { gridline-color: @border; }
QTableWidget::item { padding: 3px 6px; }
QTableWidget::item:selected { background: @sel; color: @text; }
QHeaderView::section { background: @side; color: @muted; border: none; border-bottom: 1px solid @border; padding: 6px 8px; }
QTableCornerButton::section { background: @side; border: none; }

QTabWidget::pane { border: 1px solid @border; border-radius: 8px; top: -1px; }
QTabBar::tab { background: transparent; color: @muted; padding: 8px 16px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: @text; border-bottom: 2px solid @accent; }
QTabBar::tab:hover { color: @text; }

QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid @border2; background: @panel; }
QCheckBox::indicator:checked { background: @accent; border-color: @accent; image: url(@img_check); }

QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 11px; margin: 2px; }
QScrollBar::handle:vertical { background: @border2; border-radius: 4px; min-height: 36px; }
QScrollBar::handle:vertical:hover { background: @muted; }
QScrollBar:horizontal { background: transparent; height: 11px; margin: 2px; }
QScrollBar::handle:horizontal { background: @border2; border-radius: 4px; min-width: 36px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QMenu { background: @panel; border: 1px solid @border; border-radius: 8px; padding: 5px; }
QMenu::item { padding: 7px 22px 7px 14px; border-radius: 5px; }
QMenu::item:selected { background: @sel; }
QMenu::separator { height: 1px; background: @border; margin: 5px 8px; }
QMessageBox { background: @bg; }
QSplitter::handle { background: @border; }
"""


def build_qss(accent_name, font_pt, icons=None):
    accent = accent_of(accent_name)
    icons = icons or {}
    tokens = dict(C)
    tokens.update(img_down=icons.get("down", ""), img_up=icons.get("up", ""), img_check=icons.get("check", ""))
    tokens.update(font=FONT_FAMILY, accent=accent, accent2=_mix(accent, "#ffffff", 0.14),
                  border2=_mix(C["border"], "#ffffff", 0.14), sel2=_mix(accent, C["bg"], 0.35),
                  bannerbg=_mix(accent, C["bg"], 0.86),
                  h1pt=f"{font_pt + 3}pt", h2pt=f"{font_pt + 1}pt", smallpt=f"{max(7, font_pt - 1)}pt")
    qss = _QSS
    for k in sorted(tokens, key=len, reverse=True):     # длинные имена первыми: @accent2 раньше @accent
        qss = qss.replace("@" + k, tokens[k])
    return qss
