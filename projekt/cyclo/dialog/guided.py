"""Geführte Dialog-Eingabe: Funktionstaste -> neuer NC-Satz -> Dialogfragen.

Ablauf (z. B. Taste L):
  "Koordinaten?"                         Achsen und Werte, ENT = weiter
  "Radiuskorr.: RL/RR/keine Korr.?"       ENT = R0
  "Vorschub F=? F MAX = ENT"              ENT = FMAX
  "Zusatz-Funktion M?"                    ENT = keine, Satz fertig
Tasten: ENT übernimmt (leer = Vorgabewert der Frage bzw. vorhandener Wert bleibt),
NO ENT lässt den Parameter weg, END beendet den Satz mit dem, was eingegeben ist.

Dieses Modul kennt keine Oberfläche: ``Draft`` hält die Werte eines Satzes,
``format_draft`` macht daraus die Dialog-Programmzeile, ``parse_line`` den Entwurf aus einer
vorhandenen Zeile (Satz ändern).
"""

from __future__ import annotations

from ..i18n import _t

import re
from dataclasses import dataclass, field

AXES = "XYZABCUVW"
_NUM = r"[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)"
_QP = r"[+-]?Q[LRS]?\d+"
VALUE_RE = re.compile(rf"^(?:{_NUM}|{_QP})$", re.I)


@dataclass
class Step:
    key: str  # Feld im Entwurf
    prompt: str  # Dialogfrage
    hint: str = ""
    kind: str = "value"  # value | coords | choice | text | m
    ent: str | None = None  # Wert bei ENT auf leerer Eingabe (None = weglassen)
    choices: tuple = ()
    required: bool = False


_F_HINT = _t("Zahl, FAUTO oder Q-Parameter · NO ENT = ohne F")
_COORD_HINT = _t("z. B. X+10 Y-5 · IX = inkremental · ENT = weiter")

DIALOGS: dict[str, list[Step]] = {
    "L": [
        Step("coords", _t("Koordinaten?"), _COORD_HINT, "coords"),
        Step("R", _t("Radiuskorr.: RL/RR/keine Korr.?"), _t("RL, RR · ENT = keine Korr. (R0)"), "choice", "R0",
             ("RL", "RR", "R0")),
        Step("F", _t("Vorschub F=? F MAX = ENT"), _F_HINT, "feed", "FMAX"),
        Step("M", _t("Zusatz-Funktion M?"), _t("z. B. 3 oder 3 8 · ENT = keine"), "m"),
    ],
    "CC": [Step("coords", _t("Kreismittelpunkt Koordinaten?"), _t("z. B. X+50 Y+50 · IX = inkremental"), "coords",
                required=True)],
    "C": [
        Step("coords", _t("Koordinaten Kreisendpunkt?"), _COORD_HINT, "coords", required=True),
        Step("DR", _t("Drehsinn? DR-/DR+"), _t("+ = gegen den Uhrzeiger, - = im Uhrzeiger · ENT = DR+"), "choice", "+",
             ("+", "-")),
        Step("R", _t("Radiuskorr.: RL/RR/keine Korr.?"), _t("RL, RR · ENT = keine Korr. (R0)"), "choice", "R0",
             ("RL", "RR", "R0")),
        Step("F", _t("Vorschub F=? F MAX = ENT"), _F_HINT, "feed", "FMAX"),
        Step("M", _t("Zusatz-Funktion M?"), _t("ENT = keine"), "m"),
    ],
    "CR": [
        Step("coords", _t("Koordinaten Kreisendpunkt?"), _COORD_HINT, "coords", required=True),
        Step("RAD", _t("Kreisradius?"), _t("+ = Bogen bis 180°, - = Bogen über 180°"), "value", required=True),
        Step("DR", _t("Drehsinn? DR-/DR+"), _t("+ = gegen den Uhrzeiger, - = im Uhrzeiger · ENT = DR+"), "choice", "+",
             ("+", "-")),
        Step("R", _t("Radiuskorr.: RL/RR/keine Korr.?"), _t("RL, RR · ENT = keine Korr. (R0)"), "choice", "R0",
             ("RL", "RR", "R0")),
        Step("F", _t("Vorschub F=? F MAX = ENT"), _F_HINT, "feed", "FMAX"),
        Step("M", _t("Zusatz-Funktion M?"), _t("ENT = keine"), "m"),
    ],
    "CT": [
        Step("coords", _t("Koordinaten Kreisendpunkt?"), _COORD_HINT, "coords", required=True),
        Step("R", _t("Radiuskorr.: RL/RR/keine Korr.?"), _t("RL, RR · ENT = keine Korr. (R0)"), "choice", "R0",
             ("RL", "RR", "R0")),
        Step("F", _t("Vorschub F=? F MAX = ENT"), _F_HINT, "feed", "FMAX"),
        Step("M", _t("Zusatz-Funktion M?"), _t("ENT = keine"), "m"),
    ],
    "RND": [
        Step("RAD", _t("Rundungs-Radius?"), _t("Radius der Rundung zwischen zwei Konturelementen"), "value", required=True),
        Step("F", _t("Vorschub F?"), _t("nur für die Rundung · ENT = ohne"), "feed"),
    ],
    "CHF": [
        Step("LEN", _t("Fase-Abschnitt?"), _t("Länge der Fase ab der Ecke"), "value", required=True),
        Step("F", _t("Vorschub F?"), _t("nur für die Fase · ENT = ohne"), "feed"),
    ],
    "TOOL CALL": [
        Step("T", _t("Werkzeug-Nummer / Name?"), _t("Nummer oder Name aus der Werkzeugtabelle"), "text", required=True),
        Step("AX", _t("Spindelachse parallel X/Y/Z?"), _t("ENT = Z"), "choice", "Z", ("X", "Y", "Z")),
        Step("S", _t("Spindeldrehzahl S=?"), _t("U/min · ENT = ohne"), "value"),
        Step("F", _t("Vorschub F=?"), _t("mm/min · ENT = ohne"), "value"),
        Step("DL", _t("Aufmaß Werkzeug-Länge DL?"), _t("ENT = ohne"), "value"),
        Step("DR", _t("Aufmaß Werkzeug-Radius DR?"), _t("ENT = ohne"), "value"),
    ],
    "WMAT": [Step("M", _t("Werkstoff?"), _t("Name aus der Werkstoffliste (Tabellen → Schnittdaten) oder Gruppe wie N1"),
                  "text", required=True)],
    "TOOL DEF": [Step("T", _t("Werkzeug-Nummer / Name?"), _t("Werkzeug vorauswählen"), "text", required=True)],
    "LBL SET": [Step("LBL", _t("Label-Nummer / Name?"), _t("ENT = nächste freie Nummer"), "text", "NEXT")],
    "LBL CALL": [
        Step("LBL", _t("Label-Nummer / Name?"), "", "text", required=True),
        Step("REP", _t("Wiederholungen REP?"), _t("Programmteil-Wiederholung · ENT = Unterprogramm"), "value"),
    ],
    "STOP": [Step("M", _t("Zusatz-Funktion M?"), _t("ENT = keine"), "m")],
    "PGM CALL": [Step("PGM", _t("Programmname?"), _t("z. B. TEIL2.h"), "text", required=True)],
}

ACTION_KIND = {k: k for k in DIALOGS}


@dataclass
class Draft:
    kind: str
    values: dict = field(default_factory=dict)  # coords: list[(axis, inc, value)]
    comment: str = ""  # Kommentar hinter ";" bleibt beim Ändern erhalten

    @property
    def steps(self) -> list[Step]:
        return DIALOGS[self.kind]


class InputError(ValueError):
    pass


def _sign(v: str) -> str:
    v = v.strip().replace(",", ".").upper()
    if v and v[0] not in "+-":
        v = "+" + v
    return v


def norm_value(text: str) -> str:
    t = text.strip().replace(" ", "")
    if not VALUE_RE.match(t):
        raise InputError(_t('„{0}“ ist kein Zahlenwert oder Q-Parameter').format(text))
    return _sign(t)


def parse_coords(text: str) -> list[tuple[str, bool, str]]:
    """"X10 iy-5 Z+Q3" -> [("X", False, "+10"), ("Y", True, "-5"), ("Z", False, "+Q3")]."""
    t = text.upper().replace(",", ".")
    out = []
    pos = 0
    pat = re.compile(rf"\s*(I?)([{AXES}])\s*({_NUM}|{_QP})\s*", re.I)
    while pos < len(t):
        m = pat.match(t, pos)
        if not m:
            rest = t[pos:].strip()
            if not rest:
                break
            raise InputError(_t('Koordinate nicht verstanden: „{0}“ (z. B. X+10 IY-5)').format(rest))
        ax = m.group(2)
        val = _sign(m.group(3))
        out = [c for c in out if c[0] != ax]  # gleiche Achse ersetzt
        out.append((ax, m.group(1) == "I", val))
        pos = m.end()
    order = {a: i for i, a in enumerate(AXES)}
    return sorted(out, key=lambda c: order[c[0]])


def coords_text(coords) -> str:
    return " ".join(f"{'I' if inc else ''}{ax}{val}" for ax, inc, val in coords)


def apply(draft: Draft, step: Step, text: str, *, editing: bool = False) -> None:
    """Eingabe übernehmen (ENT). Leere Eingabe: vorhandener Wert bleibt, sonst Vorgabe der Frage."""
    t = text.strip()
    k = step.key
    if not t:
        if k in draft.values:
            return
        if step.required:
            raise InputError(_t("Eingabe erforderlich"))
        if step.ent is not None:
            draft.values[k] = step.ent
        return
    if step.kind == "coords":
        draft.values[k] = parse_coords(t)
    elif step.kind == "choice":
        u = t.upper().replace("DR", "")
        if step.key == "R" and u in ("R0", "0", "KEINE", "-"):
            u = "R0"
        if u not in step.choices:
            raise InputError(f"erlaubt: {' / '.join(step.choices)}")
        draft.values[k] = u
    elif step.kind == "feed":
        u = t.upper().replace(" ", "")
        if u in ("FMAX", "MAX"):
            draft.values[k] = "FMAX"
        elif u in ("FAUTO", "AUTO"):
            draft.values[k] = "FAUTO"
        else:
            u = u[1:] if u.startswith("F") else u
            v = norm_value(u)
            draft.values[k] = v.lstrip("+") if not v.startswith("-") else v
            if draft.values[k].startswith("-"):
                raise InputError(_t("Vorschub muss positiv sein"))
    elif step.kind == "m":
        ms = [m.upper().lstrip("M") for m in re.split(r"[\s,;]+", t) if m]
        if not all(m.isdigit() for m in ms):
            raise InputError(_t("M-Funktion als Zahl, z. B. 3 oder 3 8"))
        draft.values[k] = " ".join("M" + m for m in ms)
    elif step.kind == "text":
        draft.values[k] = t.upper() if re.fullmatch(r"[\w.\-]+", t) and not re.search(r"[a-z]", t) else t
    else:
        v = norm_value(t)
        if step.key in ("S", "REP") and v.startswith("-"):
            raise InputError(_t("Wert muss positiv sein"))
        draft.values[k] = v.lstrip("+") if step.key in ("S", "F", "REP") else v


def fill_defaults(draft: Draft, active_comp: str | None = None) -> None:
    """END: fehlende Angaben mit den Vorgabewerten der Fragen ergänzen.

    Innerhalb einer Kontur mit aktiver Radiuskorrektur (RL/RR) bleiben R und F weg – sie
    wirken modal weiter; ein R0/FMAX würde die Kontur abbrechen bzw. im Eilgang fräsen.
    """
    in_contour = active_comp in ("RL", "RR")
    for st in draft.steps:
        if st.key in draft.values or st.ent is None:
            continue
        if in_contour and (st.key == "R" or (st.key == "F" and st.ent == "FMAX")):
            continue
        draft.values[st.key] = st.ent


def active_comp(lines: list[str], before: int) -> str | None:
    """Zuletzt programmierte Radiuskorrektur (RL/RR/R0) vor Zeile ``before``."""
    for t in reversed(lines[:before]):
        u = t.split(";")[0].upper()
        if re.match(r"^\s*\d*\s*(L|C|CR|CT|LP|CP)\s", u):
            m = re.search(r"\b(RL|RR|R0)\b", u)
            if m:
                return m.group(1)
        if re.match(r"^\s*\d*\s*(TOOL CALL|BEGIN PGM)", u):
            return None
    return None


def no_ent(draft: Draft, step: Step) -> None:
    if step.required:
        raise InputError(_t("Diese Angabe ist erforderlich"))
    draft.values.pop(step.key, None)


def _feed(v):
    if v in (None, ""):
        return ""
    return " FMAX" if v == "FMAX" else " FAUTO" if v == "FAUTO" else f" F{v}"


def format_draft(d: Draft, next_label: int = 1) -> str:
    """Dialog-Programmzeile ohne Satznummer."""
    v = d.values
    k = d.kind
    co = coords_text(v.get("coords", []))
    r = f" {v['R']}" if v.get("R") else ""
    m = f" {v['M']}" if v.get("M") else ""
    if k == "L":
        return ("L " + co).rstrip() + r + _feed(v.get("F")) + m
    if k == "CC":
        return ("CC " + co).rstrip()
    if k == "C":
        return ("C " + co).rstrip() + (f" DR{v['DR']}" if v.get("DR") else "") + r + _feed(v.get("F")) + m
    if k == "CR":
        rad = f" R{v['RAD']}" if v.get("RAD") else ""
        return ("CR " + co).rstrip() + rad + (f" DR{v['DR']}" if v.get("DR") else "") + r + _feed(v.get("F")) + m
    if k == "CT":
        return ("CT " + co).rstrip() + r + _feed(v.get("F")) + m
    if k == "RND":
        return f"RND R{v.get('RAD', '').lstrip('+')}" + _feed(v.get("F"))
    if k == "CHF":
        return f"CHF {v.get('LEN', '').lstrip('+')}" + _feed(v.get("F"))
    if k == "TOOL CALL":
        s = f"TOOL CALL {v.get('T', '')} {v.get('AX', 'Z')}"
        if v.get("S"):
            s += f" S{v['S']}"
        if v.get("F"):
            s += f" F{v['F']}"
        if v.get("DL"):
            s += f" DL{v['DL']}"
        if v.get("DR"):
            s += f" DR{v['DR']}"
        return s
    if k == "TOOL DEF":
        return f"TOOL DEF {v.get('T', '')}"
    if k == "WMAT":
        return f'WMAT "{str(v.get("M", "")).strip().strip(chr(34))}"'
    if k == "LBL SET":
        lbl = v.get("LBL", "NEXT")
        return f"LBL {next_label if lbl == 'NEXT' else lbl}"
    if k == "LBL CALL":
        return f"CALL LBL {v.get('LBL', '')}" + (f" REP{v['REP']}" if v.get("REP") else "")
    if k == "STOP":
        return "STOP" + m
    if k == "PGM CALL":
        return f"CALL PGM {v.get('PGM', '')}"
    raise KeyError(k)


# --------------------------------------------------------------------------- vorhandenen Satz lesen
_LINE_RE = re.compile(r"^\s*(\d+)?\s*(.*?)\s*(;.*)?$")


def _common(body: str, d: Draft, allow_rad=False):
    """Koordinaten, R-Korrektur, F, M, DR, R (Radius) aus dem Rest des Satzes."""
    toks = body.split()
    coords = []
    for t in toks:
        u = t.upper()
        if u in ("RL", "RR", "R0"):
            d.values["R"] = u
        elif u in ("FMAX", "FAUTO"):
            d.values["F"] = u
        elif re.fullmatch(r"F(\d+(\.\d*)?|Q[LRS]?\d+)", u):
            d.values["F"] = u[1:]
        elif re.fullmatch(r"M\d+", u):
            d.values["M"] = (d.values.get("M", "") + " " + u).strip()
        elif re.fullmatch(r"DR[+-]", u):
            d.values["DR"] = u[2]
        elif allow_rad and re.fullmatch(rf"R{_NUM}|R{_QP}", u, re.I):
            d.values["RAD"] = _sign(u[1:])
        else:
            m = re.fullmatch(rf"(I?)([{AXES}])({_NUM}|{_QP})", u)
            if not m:
                return None  # unbekanntes Wort: nicht im Dialog bearbeiten
            coords.append((m.group(2), m.group(1) == "I", _sign(m.group(3))))
    if coords:
        d.values["coords"] = coords
    return d


def parse_line(text: str) -> Draft | None:
    """Vorhandene Zeile -> Entwurf; None wenn der Satz nicht per Dialog bearbeitbar ist."""
    if text.rstrip().endswith("~"):
        return None
    m = _LINE_RE.match(text)
    body = (m.group(2) if m else text).strip()
    d = _parse_body(body)
    if d is not None and m and m.group(3):
        d.comment = m.group(3)
    return d


def _parse_body(body: str) -> Draft | None:
    u = body.upper()
    for kw, kind in (("CC ", "CC"), ("CR ", "CR"), ("CT ", "CT"), ("C ", "C"), ("L ", "L")):
        if u.startswith(kw) or u == kw.strip():
            return _common(body[len(kw.strip()):], Draft(kind), allow_rad=(kind == "CR"))
    if m2 := re.fullmatch(rf"RND\s+R({_NUM}|{_QP})(?:\s+(F\S+))?", u):
        d = Draft("RND", {"RAD": _sign(m2.group(1))})
        if m2.group(2):
            d.values["F"] = m2.group(2)[1:] if m2.group(2) not in ("FMAX", "FAUTO") else m2.group(2)
        return d
    if m2 := re.fullmatch(rf"CHF\s+({_NUM}|{_QP})(?:\s+(F\S+))?", u):
        d = Draft("CHF", {"LEN": _sign(m2.group(1))})
        if m2.group(2):
            d.values["F"] = m2.group(2)[1:] if m2.group(2) not in ("FMAX", "FAUTO") else m2.group(2)
        return d
    if m2 := re.fullmatch(r"TOOL CALL\s+(\S+)(?:\s+([XYZ]))?(.*)", body, re.I):
        d = Draft("TOOL CALL", {"T": m2.group(1), "AX": (m2.group(2) or "Z").upper()})
        for w in m2.group(3).split():
            wu = w.upper()
            for key in ("DL", "DR", "S", "F"):
                if wu.startswith(key) and VALUE_RE.match(wu[len(key):] or "x"):
                    d.values[key] = wu[len(key):] if key in ("S", "F") else _sign(wu[len(key):])
                    break
            else:
                return None
        return d
    if m2 := re.fullmatch(r'WMAT\s+"([^"]*)"', body, re.I):
        return Draft("WMAT", {"M": m2.group(1)})
    if m2 := re.fullmatch(r"TOOL DEF\s+(\S+)", body, re.I):
        return Draft("TOOL DEF", {"T": m2.group(1)})
    if m2 := re.fullmatch(r"LBL\s+(\S+)", body, re.I):
        if m2.group(1) == "0":
            return None
        return Draft("LBL SET", {"LBL": m2.group(1)})
    if m2 := re.fullmatch(r"CALL LBL\s+(\S+)(?:\s+REP\s*(\d+))?", body, re.I):
        d = Draft("LBL CALL", {"LBL": m2.group(1)})
        if m2.group(2):
            d.values["REP"] = m2.group(2)
        return d
    if m2 := re.fullmatch(r"STOP((?:\s+M\d+)*)", u):
        d = Draft("STOP")
        if m2.group(1).strip():
            d.values["M"] = " ".join(m2.group(1).split())
        return d
    if m2 := re.fullmatch(r"CALL PGM\s+(.+)", body, re.I):
        return Draft("PGM CALL", {"PGM": m2.group(1).strip()})
    return None


def step_value_text(d: Draft, step: Step) -> str:
    """Aktueller Wert eines Schritts als Eingabetext (zum Vorbelegen beim Ändern)."""
    v = d.values.get(step.key)
    if v is None:
        return ""
    if step.kind == "coords":
        return coords_text(v)
    if step.kind == "feed":
        return v
    if step.kind == "m":
        return " ".join(x.lstrip("M") for x in v.split())
    return str(v)


def next_free_label(text: str) -> int:
    used = {int(n) for n in re.findall(r"^\s*\d+\s+LBL\s+(\d+)\s*$", text, re.M)}
    n = 1
    while n in used:
        n += 1
    return n
