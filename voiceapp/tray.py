# -*- coding: utf-8 -*-
"""Иконка в системном трее."""


class Tray:
    COLORS = {"idle": (120, 120, 120), "ready": (90, 90, 200), "listening": (46, 160, 67),
              "thinking": (230, 150, 30), "speaking": (50, 120, 230), "error": (200, 50, 50)}

    def __init__(self, on_quit, on_reset, on_chat):
        import pystray
        from PIL import Image, ImageDraw
        self.Image, self.ImageDraw = Image, ImageDraw
        self.icon = pystray.Icon(
            "voice_assistant", self._img("idle"), "Ассистент: загрузка",
            menu=pystray.Menu(
                pystray.MenuItem("Открыть чат", lambda icon, item: on_chat(), default=True),
                pystray.MenuItem("Новая сессия", lambda icon, item: on_reset()),
                pystray.MenuItem("Выход", lambda icon, item: on_quit())))

    def _img(self, state):
        img = self.Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        self.ImageDraw.Draw(img).ellipse((6, 6, 58, 58), fill=self.COLORS[state] + (255,))
        return img

    def set(self, state, text):
        try:
            self.icon.icon = self._img(state)
            self.icon.title = f"Ассистент: {text}"[:120]
        except Exception:
            pass

    def run(self):
        self.icon.run()

    def stop(self):
        self.icon.stop()
