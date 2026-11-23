"""Sprachen der Oberfläche.

Ausgangssprache ist Deutsch: Die Texte stehen deutsch im Code und werden mit ``tr()`` übersetzt.
Übersetzungen liegen als gettext-Dateien in ``cyclo/locale/<sprache>.po`` (z. B. mit Poedit
bearbeitbar). Fehlt eine Übersetzung, bleibt der deutsche Text stehen.

Die Sprache wird beim Start festgelegt – *bevor* die Oberflächenmodule geladen werden, denn
viele Texte stehen in Tabellen auf Modulebene. Umschalten = Oberfläche neu starten.

Reihenfolge: Umgebungsvariable ``CYCLO_LANG`` → Auswahl unter Einstell.
(``~/.config/lcnc-cyclo/language``) → ``[CYCLO] LANGUAGE`` in der INI → Deutsch.
"""

from __future__ import annotations

import ast
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LOCALE = os.path.join(HERE, "locale")
LANGUAGES = {"de": "Deutsch", "en": "English"}
USER_FILE = os.path.join(os.path.expanduser("~"), ".config", "lcnc-cyclo", "language")

_current = "de"
_table: dict[str, str] = {}


def tr(text: str) -> str:
    return _table.get(text, text) if _table else text


def N_(text: str) -> str:
    """Nur markieren (wird an anderer Stelle mit ``tr()`` übersetzt)."""
    return text


def current() -> str:
    return _current


def read_po(path: str) -> dict[str, str]:
    """Einfacher .po-Leser: msgid/msgstr mit Fortsetzungszeilen, ``#, fuzzy`` wird übersprungen."""
    out, msgid, msgstr, key, fuzzy = {}, None, None, None, False

    def flush():
        if msgid and msgstr and not fuzzy:
            out[msgid] = msgstr

    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln.startswith("#,") and "fuzzy" in ln:
                fuzzy = True
            elif ln.startswith("msgid "):
                flush()
                msgid, msgstr, key = ast.literal_eval(ln[6:]), None, "id"
            elif ln.startswith("msgstr "):
                msgstr, key = ast.literal_eval(ln[7:]), "str"
            elif ln.startswith('"') and key:
                if key == "id":
                    msgid += ast.literal_eval(ln)
                else:
                    msgstr += ast.literal_eval(ln)
            elif not ln:
                flush()
                msgid = msgstr = key = None
                fuzzy = False
    flush()
    return out


def set_language(lang: str | None) -> str:
    global _current, _table
    lang = (lang or "de").strip().lower()[:2]
    path = os.path.join(LOCALE, f"{lang}.po")
    if lang != "de" and os.path.exists(path):
        _table = read_po(path)
        _current = lang
    else:
        _table, _current = {}, "de"
    os.environ["CYCLO_LANG"] = _current
    return _current


def user_language() -> str | None:
    try:
        with open(USER_FILE, encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def save_user_language(lang: str):
    os.makedirs(os.path.dirname(USER_FILE), exist_ok=True)
    with open(USER_FILE, "w", encoding="utf-8") as f:
        f.write(lang + "\n")


def ini_language(ini_path: str | None) -> str | None:
    if not ini_path or not os.path.exists(ini_path):
        return None
    sect = None
    for ln in open(ini_path, encoding="utf-8", errors="replace"):
        t = ln.strip()
        if t.startswith("["):
            sect = t.strip("[]").strip().upper()
        elif sect in ("CYCLO", "TNC") and "=" in t and not t.startswith(("#", ";")):
            k, v = (x.strip() for x in t.split("=", 1))
            if k.upper() == "LANGUAGE" and v:
                return v.split("#")[0].strip()
    return None


def init(ini_path: str | None = None) -> str:
    """Beim Start: Sprache aus Umgebung, INI oder Benutzereinstellung wählen."""
    return set_language(os.environ.get("CYCLO_LANG") or user_language() or ini_language(ini_path) or "de")


_t = tr     # Kurzname im Code
