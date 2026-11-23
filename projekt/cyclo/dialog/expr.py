"""Übersetzung von Dialog-Formeln (Q-Parameter) in LinuxCNC-Ausdrücke.

Dialog:  Q1 = Q2 + 3 * SIN(30) - SQ(QL5)
LinuxCNC:  #<_q1> = [#<_q2> + 3 * SIN[30] - [[#<ql5>]**2]]

Q-Parameter-Zuordnung (siehe ARCHITEKTUR.md):
  Qn   -> #<_qn>   globaler benannter Parameter
  QLn  -> #<qln>   lokaler benannter Parameter (gilt im aktuellen Unterprogramm)
  QRn  -> #<_qrn>  remanent (vorerst global, Persistenz folgt)
"""

from __future__ import annotations

from ..i18n import _t

import re

__all__ = ["ExprError", "q_name", "translate_expr", "try_eval"]


class ExprError(ValueError):
    pass


_TOKEN = re.compile(
    r"\s*(?:"
    r"(?P<num>\d+\.?\d*|\.\d+)"
    r"|(?P<q>Q[LRS]?\d+)"
    r"|(?P<name>[A-Z]+)"
    r"|(?P<op>[-+*/^()])"
    r")"
)

# Dialog-Funktion -> (LinuxCNC-Vorlage)
_FUNCS = {
    "SIN": "SIN[{0}]",
    "COS": "COS[{0}]",
    "TAN": "TAN[{0}]",
    "ASIN": "ASIN[{0}]",
    "ACOS": "ACOS[{0}]",
    "ATAN": "ATAN[{0}]/[1]",
    "SQRT": "SQRT[{0}]",
    "SQ": "[[{0}]**2]",
    "ABS": "ABS[{0}]",
    "INT": "FIX[{0}]",
    "FRAC": "[[{0}]-FIX[{0}]]",
    "LN": "LN[{0}]",
    "LOG": "[LN[{0}]/LN[10]]",
    "EXP": "EXP[{0}]",
    "NEG": "[-[{0}]]",
}


def q_name(token: str) -> str:
    """Q-Parameter-Name -> LinuxCNC-Parametername."""
    t = token.upper()
    if t.startswith("QL"):
        return f"#<ql{int(t[2:])}>"
    if t.startswith("QR"):
        return f"#<_qr{int(t[2:])}>"
    if t.startswith("QS"):
        raise ExprError(_t("String-Parameter QS werden noch nicht unterstützt"))
    return f"#<_q{int(t[1:])}>"


def _tokenize(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    pos = 0
    text = text.upper().strip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise ExprError(_t('Unerwartetes Zeichen in Formel: {0!r}').format(text[pos:]))
        pos = m.end()
        kind = m.lastgroup
        out.append((kind, m.group(kind)))
    return out


class _Parser:
    """Rekursiver Abstieg: liefert (linuxcnc_text, statischer_wert | None)."""

    def __init__(self, tokens, values=None):
        self.t = tokens
        self.i = 0
        self.values = values or {}

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def parse(self):
        res = self.expr()
        if self.i != len(self.t):
            raise ExprError(_t('Überzählige Zeichen in Formel ab {0!r}').format(self.t[self.i][1]))
        return res

    def expr(self):
        txt, val = self.term()
        while self.peek() in (("op", "+"), ("op", "-")):
            op = self.take()[1]
            t2, v2 = self.term()
            txt = f"{txt} {op} {t2}"
            val = None if val is None or v2 is None else (val + v2 if op == "+" else val - v2)
        return txt, val

    def term(self):
        txt, val = self.power()
        while self.peek() in (("op", "*"), ("op", "/")):
            op = self.take()[1]
            t2, v2 = self.power()
            txt = f"{txt} {op} {t2}"
            if val is None or v2 is None:
                val = None
            elif op == "*":
                val = val * v2
            else:
                val = val / v2 if v2 != 0 else None
        return txt, val

    def power(self):
        txt, val = self.unary()
        if self.peek() == ("op", "^"):
            self.take()
            t2, v2 = self.power()
            txt = f"{txt} ** {t2}"
            val = None if val is None or v2 is None else val ** v2
        return txt, val

    def unary(self):
        if self.peek() == ("op", "+"):
            self.take()
            return self.unary()
        if self.peek() == ("op", "-"):
            self.take()
            t, v = self.unary()
            return f"[-{t}]" if not _is_simple(t) else f"-{t}", (None if v is None else -v)
        return self.atom()

    def atom(self):
        kind, tok = self.take()
        if kind == "num":
            return _fmt(float(tok)), float(tok)
        if kind == "q":
            return q_name(tok), self.values.get(tok)
        if kind == "op" and tok == "(":
            t, v = self.expr()
            if self.take() != ("op", ")"):
                raise ExprError(_t("Fehlende schließende Klammer"))
            return f"[{t}]", v
        if kind == "name":
            if tok == "PI":
                return "3.14159265358979", 3.14159265358979
            if tok in _FUNCS:
                t, v = self.unary()  # SIN(30) oder SIN 30
                if t.startswith("[") and t.endswith("]"):
                    t = t[1:-1]
                return _FUNCS[tok].format(t), _eval_func(tok, v)
            raise ExprError(_t('Unbekannte Funktion {0}').format(tok))
        raise ExprError(_t('Unerwartetes Token {0!r}').format(tok))


def _is_simple(t: str) -> bool:
    return bool(re.fullmatch(r"[\d.]+|#<[\w]+>", t))


def _eval_func(name, v):
    import math

    if v is None:
        return None
    try:
        return {
            "SIN": lambda x: math.sin(math.radians(x)),
            "COS": lambda x: math.cos(math.radians(x)),
            "TAN": lambda x: math.tan(math.radians(x)),
            "ASIN": lambda x: math.degrees(math.asin(x)),
            "ACOS": lambda x: math.degrees(math.acos(x)),
            "ATAN": lambda x: math.degrees(math.atan(x)),
            "SQRT": math.sqrt,
            "SQ": lambda x: x * x,
            "ABS": abs,
            "INT": lambda x: float(int(x)),
            "FRAC": lambda x: x - int(x),
            "LN": math.log,
            "LOG": math.log10,
            "EXP": math.exp,
            "NEG": lambda x: -x,
        }[name](v)
    except (ValueError, OverflowError):
        return None


def _fmt(v: float) -> str:
    s = f"{v:.6f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def translate_expr(text: str, values: dict | None = None) -> tuple[str, float | None]:
    """Formel übersetzen. Gibt (LinuxCNC-Text, statischer Wert oder None) zurück.

    ``values`` enthält bekannte Q-Parameter-Werte (z. B. {"Q1": 5.0}); ist ein Wert
    unbekannt, bleibt der statische Wert None und der Ausdruck wird zur Laufzeit
    von LinuxCNC berechnet.
    """
    return _Parser(_tokenize(text), values).parse()


def try_eval(text: str, values: dict | None = None) -> float | None:
    try:
        return translate_expr(text, values)[1]
    except ExprError:
        return None
