# -*- coding: utf-8 -*-
"""Безопасный калькулятор: модели плохо считают в уме, а это быстро и точно."""
import ast
import math
import operator
import re


def _pow(a, b):
    if abs(b) > 10000 or abs(b) * math.log10(max(abs(a), 1.0001)) > 3000:
        raise ValueError("слишком большая степень")
    return a ** b


def _fact(n):
    if int(n) != n or n < 0 or n > 1000:
        raise ValueError("факториал только для целых от 0 до 1000")
    return math.factorial(int(n))


_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: _pow}
_UN = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {"sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan, "asin": math.asin,
          "acos": math.acos, "atan": math.atan, "log": math.log, "ln": math.log, "log10": math.log10,
          "log2": math.log2, "exp": math.exp, "abs": abs, "round": round, "floor": math.floor,
          "ceil": math.ceil, "min": min, "max": max, "factorial": _fact, "radians": math.radians,
          "degrees": math.degrees, "pow": _pow}
_CONST = {"pi": math.pi, "e": math.e, "tau": math.tau}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        return _BIN[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UN:
        return _UN[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Name) and node.id.lower() in _CONST:
        return _CONST[node.id.lower()]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id.lower() in _FUNCS \
            and not node.keywords:
        return _FUNCS[node.func.id.lower()](*[_eval(a) for a in node.args])
    raise ValueError("не понимаю выражение")


def calculate(expression):
    expr = str(expression or "").strip()
    if not expr:
        return "Пустое выражение."
    if len(expr) > 200:
        return "Слишком длинное выражение."
    expr = (expr.replace("×", "*").replace("÷", "/").replace("−", "-").replace("^", "**")
            .replace("\u00a0", " "))
    if re.search(r"[A-Za-zА-Яа-я_]\w*\s*=", expr):
        return "Нужно выражение без присваивания."
    try:
        value = _eval(ast.parse(expr, mode="eval"))
    except ZeroDivisionError:
        return "Ошибка: деление на ноль."
    except (ValueError, SyntaxError, TypeError, OverflowError, RecursionError) as e:
        return f"Ошибка вычисления: {e}"
    if isinstance(value, float):
        if value != value or value in (math.inf, -math.inf):
            return "Результат не определён."
        if value.is_integer() and abs(value) < 1e15:
            value = int(value)
        else:
            value = float(format(value, ".10g"))
    return f"{expr} = {value}"
