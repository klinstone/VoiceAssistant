# -*- coding: utf-8 -*-
"""Текстовый чат с моделью и история сохранённых диалогов (окно на tkinter)."""
import queue
import threading
import traceback

from . import sessions
from .log import log

_thread = None
_app = None
_lock = threading.Lock()


class ChatApp:
    def __init__(self):
        import tkinter as tk
        from tkinter import messagebox, ttk
        self.tk, self.ttk, self.mb = tk, ttk, messagebox
        self.q = queue.Queue()
        self.busy = False
        self.infos = []
        self.ok = True
        self.root = tk.Tk()
        self.root.title("Чат с ассистентом")
        self.root.geometry("1000x660")
        self.root.minsize(700, 420)
        try:
            from .llm import Brain
            self.brain = Brain(mode="chat")
        except Exception as e:
            messagebox.showerror("Чат с ассистентом", str(e))
            self.root.destroy()
            self.ok = False
            return
        self._build()
        self.refresh_list()
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        self.root.after(50, self._poll)

    # ----------------------------- интерфейс -----------------------------
    def _build(self):
        tk, ttk, root = self.tk, self.ttk, self.root
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        left = ttk.Frame(root, padding=8)
        left.grid(row=0, column=0, sticky="ns")
        ttk.Button(left, text="＋ Новый чат", command=self.new_chat).pack(fill="x")
        lf = ttk.Frame(left)
        lf.pack(fill="both", expand=True, pady=6)
        self.listbox = tk.Listbox(lf, width=34, activestyle="none", exportselection=False)
        sb = ttk.Scrollbar(lf, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        ttk.Button(left, text="Удалить чат", command=self.delete_chat).pack(fill="x")

        right = ttk.Frame(root, padding=(0, 8, 8, 8))
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        self.view = tk.Text(right, wrap="word", state="disabled", font=("Segoe UI", 11),
                            padx=10, pady=8, relief="solid", borderwidth=1)
        vs = ttk.Scrollbar(right, command=self.view.yview)
        self.view.configure(yscrollcommand=vs.set)
        self.view.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        self.view.tag_configure("who_user", foreground="#1a5fb4", font=("Segoe UI", 10, "bold"), spacing1=12)
        self.view.tag_configure("who_bot", foreground="#26a269", font=("Segoe UI", 10, "bold"), spacing1=12)
        self.view.tag_configure("meta", foreground="#888888", font=("Segoe UI", 9, "italic"))

        inp = ttk.Frame(right)
        inp.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        inp.columnconfigure(0, weight=1)
        self.entry = tk.Text(inp, height=3, wrap="word", font=("Segoe UI", 11))
        self.entry.grid(row=0, column=0, sticky="ew")
        self.send_btn = ttk.Button(inp, text="Отправить", command=self.send)
        self.send_btn.grid(row=0, column=1, padx=(8, 0), sticky="ns")
        self.entry.bind("<Return>", self._on_enter)
        self.status = ttk.Label(right, text=self.HINT, foreground="#666666")
        self.status.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.entry.focus_set()

    HINT = "Enter — отправить, Shift+Enter — новая строка"

    def _on_enter(self, event):
        if event.state & 0x0001:       # Shift+Enter: перенос строки
            return None
        self.send()
        return "break"

    # ----------------------------- вывод -----------------------------
    def _append(self, text, *tags):
        self.view.configure(state="normal")
        self.view.insert("end", text, tags)
        self.view.configure(state="disabled")
        self.view.see("end")

    def _clear(self):
        self.view.configure(state="normal")
        self.view.delete("1.0", "end")
        self.view.configure(state="disabled")

    def _show_message(self, role, content, src=None, stamp=""):
        who = "Вы" if role == "user" else "Ассистент"
        extra = " · голос" if src == "voice" else ""
        extra += f" · {stamp}" if stamp else ""
        self._append(f"{who}{extra}\n", "who_user" if role == "user" else "who_bot")
        self._append(content + "\n")

    # ----------------------------- список диалогов -----------------------------
    def refresh_list(self):
        self.infos = sessions.list_sessions()
        self.listbox.delete(0, "end")
        current = self.brain.session.path if self.brain.session else None
        for i, info in enumerate(self.infos):
            self.listbox.insert("end", f"{info.when:%d.%m %H:%M} · {info.title}")
            if current and info.path == current:
                self.listbox.selection_set(i)

    def on_select(self, _event=None):
        sel = self.listbox.curselection()
        if self.busy or not sel:
            return
        info = self.infos[sel[0]]
        self.brain.load_session(info.path)
        self._clear()
        for m in sessions.load_messages(info.path):
            self._show_message(m["role"], m["content"], m.get("src"), m.get("t", "")[11:16])

    def new_chat(self):
        if self.busy:
            return
        self.brain.reset()
        self._clear()
        self.listbox.selection_clear(0, "end")
        self.entry.focus_set()

    def delete_chat(self):
        sel = self.listbox.curselection()
        if self.busy or not sel:
            return
        info = self.infos[sel[0]]
        if not self.mb.askyesno("Удалить чат", f"Удалить диалог «{info.title}»?"):
            return
        if self.brain.session and self.brain.session.path == info.path:
            self.brain.reset()
            self._clear()
        sessions.delete(info.path)
        self.refresh_list()

    # ----------------------------- отправка -----------------------------
    def send(self):
        text = self.entry.get("1.0", "end").strip()
        if not text or self.busy:
            return
        self.entry.delete("1.0", "end")
        self.busy = True
        self.send_btn.state(["disabled"])
        self.status.configure(text="Думаю…")
        self._show_message("user", text)
        self._append("Ассистент\n", "who_bot")
        threading.Thread(target=self._worker, args=(text,), daemon=True).start()

    def _worker(self, text):
        try:
            self.brain.ask(text, on_token=lambda s: self.q.put(("tok", s)),
                           on_status=lambda s: self.q.put(("status", s)), src="text")
            self.q.put(("done", None))
        except Exception as e:
            traceback.print_exc()
            self.q.put(("err", str(e)))

    def _finish(self):
        self.busy = False
        self.send_btn.state(["!disabled"])
        self.status.configure(text=self.HINT)
        self.refresh_list()
        self.entry.focus_set()

    def _poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "tok":
                    self._append(val)
                elif kind == "status":
                    self.status.configure(text=val)
                elif kind == "done":
                    self._append("\n")
                    self._finish()
                elif kind == "err":
                    self._append(f"\n[Ошибка: {val}]\n", "meta")
                    self._finish()
                elif kind == "front":
                    self.root.deiconify()
                    self.root.lift()
                    self.root.focus_force()
        except queue.Empty:
            pass
        self.root.after(50, self._poll)


def _run():
    global _app
    try:
        _app = ChatApp()
        if _app.ok:
            _app.root.mainloop()
    except Exception:
        traceback.print_exc()
        log("Не удалось открыть окно чата (подробности выше).")
    finally:
        _app = None


def open_chat():
    """Открыть окно чата (если уже открыто, выводит его на передний план)."""
    global _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            if _app is not None:
                _app.q.put(("front", None))
            return
        _thread = threading.Thread(target=_run, daemon=True, name="chat-window")
        _thread.start()


def run_standalone():
    """Чат без голосовой части: python assistant.py --chat"""
    _run()
