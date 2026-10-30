' Запуск ассистента без окна консоли. Лог: assistant.log
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "E:\Projects\VoiceAssistant"
' Сбрасываем метку Low Integrity после работы ИИ-харнесса (выполняется скрыто и ждёт завершения):
sh.Run "icacls ""E:\Projects\VoiceAssistant\venv\Scripts"" /setintegritylevel (OI)(CI)M /T /C", 0, True
sh.Run """E:\Projects\VoiceAssistant\venv\Scripts\pythonw.exe"" ""E:\Projects\VoiceAssistant\assistant.py""", 0, False