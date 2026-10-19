' Запуск ассистента без окна консоли. Лог: assistant.log
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "E:\Projects\VoiceAssistant"
sh.Run """E:\Projects\VoiceAssistant\venv\Scripts\pythonw.exe"" ""E:\Projects\VoiceAssistant\assistant.py""", 0, False
