# VoiceAssistant: архитектура и «контракты» между частями

Этот файл нужен, чтобы работать над одной частью проекта, не зная остальных (например, дать помощнику
только `voiceapp/ui/` и этот файл). Главное правило: **части общаются только через описанное здесь**.

## Слои

```
┌─ voiceapp/ui/ ─────────────┐   окно чата, окно настроек, трей (PySide6)
│  знает только: Services,   │   НЕ знает про микрофон, Vosk, Silero, инструменты
│  bus, settings, schema,    │
│  sessions, Brain (методы)  │
└───────────▲────────────────┘
            │ события (bus)            вызовы Brain / settings
┌───────────┴────────────────┐
│ voiceapp/llm.py   Brain    │   модель, история, активный диалог, инструменты
│ voiceapp/core.py  Assistant│   голос: кодовое слово, запись, озвучка
└───────────┬────────────────┘
            │
   tools.py · web.py · pc.py · notes.py · reminders.py · sessions.py · audio.py · stt.py
```

## 1. События: `voiceapp/bus.py`

Ядро делает `bus.emit(имя, **поля)`, интерфейс подписывается `bus.subscribe(имя, fn)`.
Обработчики вызываются в потоке отправителя (в Qt их превращает в сигналы `ui/bridge.py`).

| событие | поля | когда |
|---|---|---|
| `USER_MESSAGE` | turn, text, src | началась обработка реплики (`src`: `"voice"` или `"text"`) |
| `ASSISTANT_START` | turn, src | модель начала отвечать |
| `TOKEN` | turn, delta, full | кусок ответа; `full` — весь текст на данный момент |
| `STATUS` | turn, text | вызван инструмент («Ищу в интернете…») |
| `ASSISTANT_DONE` | turn, text | ответ готов и сохранён |
| `ASSISTANT_ERROR` | turn, message | запрос не удался |
| `SESSION_CHANGED` | path | сменился активный диалог |
| `SESSIONS_UPDATED` | — | изменился список диалогов |
| `VOICE_PARTIAL` | text | то, что вы говорите сейчас (`""` = запись окончена) |
| `STATE` | state, text | состояние голоса: idle / ready / listening / thinking / speaking / error |
| `NOTIFY` | title, text | уведомление (сработал таймер) |

`turn` растёт на единицу с каждым запросом; по нему окно отличает уже показанное от нового.

## 2. Brain: `voiceapp/llm.py`

Один экземпляр на программу. **Активный диалог** = `brain.session`; голос и текст всегда идут в него.

```
brain.ask(text, speaker=None, src="text"|"voice")   # блокирует поток; события идут в bus
brain.cancel()                                      # прервать ответ
brain.new_session(wait=True) / open_session(path, wait=False) / delete_session(path, wait=False)
                                                    # wait=False: если модель занята, сразу вернуть False
brain.session.path   brain.is_draft   brain.busy   brain.turn   brain.inflight
brain.reset_client()                                # после смены ключа
```
Пустой диалог (черновик) не создаёт файл: он появляется вместе с первой репликой.
Таймаут простоя (`CONTEXT_TIMEOUT_MIN`) действует только на голосовые запросы.

## 3. Настройки: `voiceapp/config.py`, `settings.py`, `schema.py`

- Значения по умолчанию: `config.py` и `settings._DEFAULTS`.
- Пользовательские изменения: `data/settings.json` (только отличия от умолчаний). `config.py` накладывает их при импорте.
- `settings.get(name)`, `settings.default(name)`, `settings.save({имя: значение})` (применяет сразу), `settings.reset(...)`.
- Ключ OpenRouter: `.env` (`settings.env_get/env_set`).
- `schema.py` описывает каждую настройку для окна (группа, название, подсказка, тип, диапазон, `restart`).
  **Новая настройка** = значение по умолчанию + одна строка `Field(...)` в `schema.py`.
  Читайте её через `cfg.ИМЯ` (config.py) или `settings.get("ИМЯ")` в момент использования, а не при импорте,
  иначе она не сможет меняться без перезапуска.

## 4. Что интерфейс получает от программы: `ui.Services`

```python
Services(brain, quit, restart=None, silence=None, reset_session=None, preview_voice=None, voice=True)
UiApp(services, standalone=False).run(show_chat=False) -> нужно_ли_перезапускать
```
`main.py` собирает `Services` и больше интерфейс ни с чем не связывает.

## 5. Как работать над частью проекта

- **Интерфейс:** дайте `ARCHITECTURE.md` + `voiceapp/ui/*` + `voiceapp/schema.py`. Для проверки без голоса: `python assistant.py --chat`.
- **Голос:** `ARCHITECTURE.md` + `core.py`, `audio.py`, `stt.py`, `text_utils.py`.
- **Инструменты:** `ARCHITECTURE.md` + `tools.py` и нужный модуль (`web.py`, `pc.py`, `notes.py`, `reminders.py`).
- **Всё остальное «в общих чертах»:** `python dev/skeleton.py > skeleton.txt`: сигнатуры и докстринги всех файлов
  (в разы короче полного кода), приложите его.
- Перед каждым заданием делайте git-коммит: откат бесплатный.
