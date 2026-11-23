"""Hilfsfunktionen für den Dialog-Editor: Satznummern, Vorlagen."""

from __future__ import annotations

import re

_BLOCKNR = re.compile(r"^(\s*)(\d+)(\s+)")


def renumber(text: str) -> str:
    """Satznummern fortlaufend ab 0 vergeben (Fortsetzungszeilen mit ~ bleiben)."""
    out, n, cont = [], 0, False
    for line in text.splitlines():
        if not cont and line.strip():
            m = _BLOCKNR.match(line)
            body = line[m.end():] if m else line.lstrip()
            line = f"{n} {body}"
            n += 1
        out.append(line)
        cont = line.rstrip().endswith("~")
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def new_program(name: str, unit: str = "MM") -> str:
    return (f"0 BEGIN PGM {name} {unit}\n"
            f"1 BLK FORM 0.1 Z X+0 Y+0 Z-20\n"
            f"2 BLK FORM 0.2 X+100 Y+100 Z+0\n"
            f"3 END PGM {name} {unit}\n")


# Vorlagen der Bahnfunktionstasten (Dialog-Tastatur). "|" markiert die Cursorposition.
TEMPLATES = {
    "L": "L X+| Y+0 R0 FMAX",
    "CC": "CC X+| Y+0",
    "C": "C X+| Y+0 DR+",
    "CR": "CR X+| Y+0 R+10 DR+",
    "CT": "CT X+| Y+0",
    "RND": "RND R|",
    "CHF": "CHF |",
    "LBL SET": "LBL |",
    "LBL CALL": "CALL LBL |",
    "TOOL CALL": "TOOL CALL | Z S1000 F500",
    "WMAT": 'WMAT "|"',
    "CYCL CALL": "CYCL CALL",
    "Q": "Q| = ",
    "STOP": "STOP",
    "M30": "M30",
    "TCPM": "FUNCTION TCPM F TCP AXIS POS PATHCTRL AXIS",
    "* Gliederung": "* - |",
}

# PLANE-Funktionen (SPEC FCT > BEARBEITUNGSEBENE) und Koordinatenumrechnung
PLANE_TEMPLATES = {
    "PLANE SPATIAL": "PLANE SPATIAL SPA+0 SPB+| SPC+0 TURN MB MAX FMAX",
    "PLANE PROJECTED": "PLANE PROJECTED PROPR+| PROMIN+0 PROROT+0 TURN MB MAX FMAX",
    "PLANE EULER": "PLANE EULER EULPR+| EULNU+0 EULROT+0 TURN MB MAX FMAX",
    "PLANE VECTOR": "PLANE VECTOR BX+1 BY+0 BZ+0 NX+| NY+0 NZ+1 TURN MB MAX FMAX",
    "PLANE POINTS": "PLANE POINTS P1X+0 P1Y+0 P1Z+0 P2X+| P2Y+0 P2Z+0 P3X+0 P3Y+10 P3Z+0 TURN MB MAX FMAX",
    "PLANE RELATIV": "PLANE RELATIV SPB+| TURN MB MAX FMAX",
    "PLANE AXIAL": "PLANE AXIAL B+| TURN MB MAX FMAX",
    "PLANE RESET": "PLANE RESET TURN MB MAX FMAX",
    "TRANS DATUM": "TRANS DATUM AXIS X+| Y+0 Z+0",
    "TRANS DATUM RESET": "TRANS DATUM RESET",
}


# --------------------------------------------------------------------------- Zyklus-Sätze
_CYC = re.compile(r"^\s*\d*\s*CYCL DEF\s+(\d+)", re.I)
_QLINE = re.compile(r"^(\s*QS?(\d+)\s*=\s*)([^;~]*?)(\s*;[^~]*)?(\s*~)?\s*$", re.I)


def find_cycle_block(lines: list[str], line_no: int):
    """Liefert (start, ende, zyklusnummer) des CYCL-DEF-Satzes, in dem ``line_no`` liegt."""
    if not (0 <= line_no < len(lines)):
        return None
    start = line_no
    # nach oben: solange die vorherige Zeile mit ~ endet, gehört die aktuelle zum selben Satz
    while start > 0 and lines[start - 1].rstrip().endswith("~"):
        start -= 1
    m = _CYC.match(lines[start])
    if not m:
        return None
    end = start
    while end + 1 < len(lines) and lines[end].rstrip().endswith("~"):
        end += 1
    return start, end, int(m.group(1))


def cycle_values(lines: list[str], start: int, end: int) -> dict[int, tuple[int, str]]:
    """Q-Nummer -> (Zeilenindex, Wert-Text) innerhalb eines CYCL-DEF-Satzes."""
    out = {}
    for i in range(start + 1, end + 1):
        m = _QLINE.match(lines[i])
        if m:
            out[int(m.group(2))] = (i, m.group(3).strip())
    return out


def set_cycle_value(line: str, value: str) -> str:
    m = _QLINE.match(line)
    if not m:
        return line
    v = value.strip()
    if re.fullmatch(r"\d*\.?\d+", v):
        v = "+" + v
    return f"{m.group(1)}{v}{m.group(4) or ''}{m.group(5) or ''}"


def parse_range(text: str) -> tuple[float | None, float | None]:
    """'–99999.9999...+99999.9999 alternativ PREDEF' -> (min, max)."""
    t = text.replace("–", "-").split(" alternativ")[0]
    m = re.match(r"\s*([-+]?\d*\.?\d+)\s*\.\.\.\s*([-+]?\d*\.?\d+)", t)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None, None


def norm_value(value: str, text: bool = False) -> str:
    """Eingabe -> Dialog-Wert: Komma als Punkt, positive Zahlen mit Vorzeichen.

    text=True (String-Parameter QS): in Anführungszeichen, ohne ; und ~.
    """
    if text:
        v = value.strip()
        if len(v) >= 2 and v[0] == v[-1] == '"':
            v = v[1:-1]
        return '"' + v.replace('"', "").replace(";", "").replace("~", "") + '"'
    v = value.strip().replace(",", ".").upper()
    if re.fullmatch(r"\d*\.?\d+", v):
        v = "+" + v
    return v


def format_cycle_block(header: str, cycle, values: dict) -> list[str]:
    """Kompletten CYCL-DEF-Satz neu aufbauen.

    header: erste Zeile ohne "~" (z. B. "5 CYCL DEF 200 BOHREN"); values: Q -> Text.
    Fehlende Parameter bekommen den Vorgabewert, unbekannte Q aus dem Satz bleiben erhalten.
    """
    from .cycles import _fmt_default

    head = header.rstrip()
    if head.endswith("~"):
        head = head[:-1].rstrip()
    params = list(cycle.params) if cycle else []
    known = {p.q for p in params}
    rows = []
    for p in params:
        v = values.get(p.q)
        if p.mode == "text":
            rows.append((p.q, norm_value(v or "", True), p.label, "QS"))
            continue
        v = norm_value(v) if v not in (None, "") else _fmt_default(p.default)
        rows.append((p.q, v, p.label, "Q"))
    for q, v in values.items():
        if q not in known and v not in (None, ""):
            rows.append((q, norm_value(v), "", "Q"))
    if not rows:
        return [head]
    out = [head + " ~"]
    for i, (q, v, lab, qq) in enumerate(rows):
        tail = " ~" if i < len(rows) - 1 else ""
        out.append(f"  {qq}{q}={v} ;{lab}{tail}" if lab else f"  {qq}{q}={v}{tail}")
    return out
