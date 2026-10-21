# -*- coding: utf-8 -*-
"""Скелет проекта: для каждого .py-файла только докстринг модуля, классы и сигнатуры функций.
Запуск из папки проекта:  python dev/skeleton.py > skeleton.txt
Скелет (несколько страниц) + полный текст файлов, над которыми работаем, — этого достаточно для работы с проектом,
даже когда весь код целиком уже не помещается в чат."""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = {"venv", ".git", "cache", "data", "sessions", "vosk_model", "__pycache__"}


def sig(fn):
    args = ast.unparse(fn.args)
    ret = f" -> {ast.unparse(fn.returns)}" if fn.returns else ""
    return f"{'async ' if isinstance(fn, ast.AsyncFunctionDef) else ''}def {fn.name}({args}){ret}"


def first_line(node):
    doc = ast.get_docstring(node)
    return doc.strip().splitlines()[0] if doc else ""


def dump(tree, indent=""):
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            print(f"{indent}class {node.name}:  {first_line(node)}".rstrip())
            dump(node, indent + "    ")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            print(f"{indent}{sig(node)}:  {first_line(node)}".rstrip())
        elif isinstance(node, ast.Assign) and not indent and all(isinstance(t, ast.Name) and t.id.isupper() for t in node.targets):
            print(f"{indent}{', '.join(t.id for t in node.targets)} = ...")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    for p in sorted(ROOT.rglob("*.py")):
        if SKIP & set(p.relative_to(ROOT).parts):
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        print(f"\n=== {p.relative_to(ROOT).as_posix()}  — {first_line(tree)}")
        dump(tree)


if __name__ == "__main__":
    main()
