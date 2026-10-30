# -*- coding: utf-8 -*-
"""Сборка Windows-версии: dist/VoiceAssistant/ и dist/VoiceAssistant-windows.zip.
  python dev/build_exe.py            без консоли
  python dev/build_exe.py --console  с консолью (видны ошибки запуска)
Нужен PyInstaller: pip install -e ".[build]". Рядом с exe кладутся vosk_model и .env.example;
ваши data/, sessions/, cache/ и .env в сборку не попадают."""
import importlib.util
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "VoiceAssistant"
DIST = ROOT / "dist"

# пакеты с данными или DLL, которые PyInstaller сам не находит
COLLECT_ALL = ["silero", "vosk", "onnx_asr", "onnxruntime", "sounddevice", "_sounddevice_data",
               "trafilatura", "justext", "courlan", "htmldate", "dateparser", "tld", "ddgs",
               "num2words", "youtube_transcript_api", "pycaw", "comtypes"]


def main():
    try:
        import PyInstaller.__main__ as pyi
    except ImportError:
        sys.exit('Нужен PyInstaller: pip install -e ".[build]"')
    if not (ROOT / "vosk_model").is_dir():
        sys.exit("Нет папки vosk_model: без неё программа не запустится.")
    args = [str(ROOT / "assistant.py"), "--name", NAME, "--onedir", "--noconfirm", "--clean",
            "--console" if "--console" in sys.argv else "--noconsole",
            "--distpath", str(DIST), "--workpath", str(ROOT / "build"), "--specpath", str(ROOT / "build"),
            "--paths", str(ROOT), "--collect-submodules", "voiceapp"]
    for mod in COLLECT_ALL:
        if importlib.util.find_spec(mod):
            args += ["--collect-all", mod]
        else:
            print(f"пропускаю {mod}: не установлен")
    pyi.run(args)

    out = DIST / NAME
    shutil.copytree(ROOT / "vosk_model", out / "vosk_model", dirs_exist_ok=True)
    for extra in (".env.example", "LICENSE", "README.md"):
        if (ROOT / extra).is_file():
            shutil.copy(ROOT / extra, out / extra)
    archive = shutil.make_archive(str(DIST / f"{NAME}-windows"), "zip", DIST, NAME)
    print("Готово:", archive)


if __name__ == "__main__":
    main()
