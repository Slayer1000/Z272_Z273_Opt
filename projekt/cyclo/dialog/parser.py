"""Parser für Dialogprogramme (.h).

Der Parser zerlegt ein Programm in Sätze (Blocks). Jeder Satz kennt seine
Quellzeile, damit Editor, Simulation und Programmlauf den Ausführungscursor auf
den richtigen Dialogsatz setzen können.

Unterstützt (Stand Grundgerüst):
  BEGIN PGM / END PGM, BLK FORM 0.1/0.2, TOOL CALL, TOOL DEF,
  L, CC, C, CR, RND, CHF, LBL, CALL LBL [REP], CALL PGM,
  CYCL DEF (mehrzeilig mit ~), CYCL CALL, FN 0..8, Q-Formeln,
  STOP, M-Funktionen, FUNCTION TCPM / FUNCTION RESET TCPM,
  PLANE (SPATIAL, PROJECTED, EULER, VECTOR, POINTS, RELATIV, AXIAL, RESET),
  * Gliederungssätze und ; Kommentare.
"""

from __future__ import annotations

from ..i18n import _t

import re
from dataclasses import dataclass, field

AXES = "XYZABCUVW"

_COORD = re.compile(r"^(I?)([XYZABCUVW])([+-]?)(Q[LR]?\d+|\d*\.?\d+)$")
_NUM = r"[+-]?(?:Q[LR]?\d+|\d*\.?\d+)"


class ParseError(ValueError):
    def __init__(self, line: int, msg: str):
        super().__init__(_t('Zeile {0}: {1}').format(line + 1, msg))
        self.line = line
        self.msg = msg


@dataclass
class Value:
    """Zahl oder Q-Parameter mit Vorzeichen, z. B. +10, -Q5, QL3."""

    text: str  # Originaltext ohne Achsbuchstaben, z. B. "+Q5"

    @property
    def sign(self) -> int:
        return -1 if self.text.startswith("-") else 1

    @property
    def body(self) -> str:
        return self.text.lstrip("+-")

    @property
    def is_param(self) -> bool:
        return self.body.upper().startswith("Q")

    def number(self) -> float | None:
        return None if self.is_param else self.sign * float(self.body)


@dataclass
class Coord:
    axis: str
    value: Value
    incremental: bool = False


@dataclass
class Block:
    line: int  # Quellzeile (0-basiert, erste Zeile des Satzes)
    number: int | None  # Satznummer
    kind: str
    text: str  # Satztext ohne Satznummer/Kommentar
    comment: str = ""
    skip: bool = False  # "/" Satz ausblenden
    data: dict = field(default_factory=dict)
    end_line: int = 0  # letzte Quellzeile (bei ~-Fortsetzung)


def _split_comment(text: str) -> tuple[str, str]:
    # ";" außerhalb von Anführungszeichen trennt den Kommentar ab
    q = False
    for i, ch in enumerate(text):
        if ch == '"':
            q = not q
        elif ch == ";" and not q:
            return text[:i].rstrip(), text[i + 1 :].strip()
    return text.rstrip(), ""


def _join_continuations(lines: list[str]) -> list[tuple[int, int, str]]:
    """Fasst mit '~' fortgesetzte Zeilen zusammen -> (start, ende, text)."""
    out = []
    i = 0
    while i < len(lines):
        start = i
        parts = [lines[i].rstrip("\r\n")]
        while parts[-1].rstrip().endswith("~") and i + 1 < len(lines):
            parts[-1] = parts[-1].rstrip()[:-1]
            i += 1
            parts.append(lines[i].rstrip("\r\n"))
        out.append((start, i, "\n".join(parts)))
        i += 1
    return out


def parse_coords(tokens: list[str], line: int) -> tuple[list[Coord], list[str]]:
    """Trennt Koordinatenwörter von den übrigen Wörtern."""
    coords, rest = [], []
    for tok in tokens:
        m = _COORD.match(tok.upper())
        if m:
            inc, axis, sign, body = m.groups()
            coords.append(Coord(axis, Value((sign or "+") + body), bool(inc)))
        else:
            rest.append(tok)
    return coords, rest


def _parse_feed_and_m(rest: list[str], data: dict, line: int, allow_r=True):
    unknown = []
    data.setdefault("m", [])
    for tok in rest:
        t = tok.upper()
        if allow_r and t in ("R0", "RL", "RR", "R+", "R-"):
            data["radius_comp"] = t
        elif t == "FMAX":
            data["feed"] = "FMAX"
        elif t == "FAUTO":
            data["feed"] = "FAUTO"
        elif re.fullmatch(r"F" + _NUM, t):
            data["feed"] = Value(t[1:] if t[1] in "+-" else "+" + t[1:])
        elif re.fullmatch(r"M\d+", t):
            data["m"].append(int(t[1:]))
        else:
            unknown.append(tok)
    if unknown:
        raise ParseError(line, f"Unbekannte Wörter: {' '.join(unknown)}")


def _parse_cycle_params(body: str) -> tuple[dict[int, Value], dict[int, str]]:
    params, names = {}, {}
    for raw in body.split("\n")[1:]:
        ms = re.match(r'\s*QS(\d+)\s*=\s*"([^"]*)"', raw)
        if ms:
            q = int(ms.group(1))
            params[q] = Value('"' + ms.group(2) + '"')
            names[q] = _split_comment(raw[ms.end():])[1]
            continue
        code, comment = _split_comment(raw)
        m = re.match(r"\s*Q(\d+)\s*=\s*(" + _NUM + r"|PREDEF|FAUTO|FMAX)\s*$", code.upper())
        if m:
            q = int(m.group(1))
            params[q] = Value(m.group(2) if m.group(2)[0] in "+-PF" else "+" + m.group(2))
            names[q] = comment
    return params, names


def parse_block(start: int, end: int, raw: str) -> Block | None:
    first, *more = raw.split("\n")
    if not first.strip():
        return None
    code, comment = _split_comment(first)
    m = re.match(r"\s*(/?)\s*(\d+)\s*(/?)\s*(.*)$", code)   # "/" vor oder nach der Satznummer
    if m:
        number, skip, text = int(m.group(2)), bool(m.group(1) or m.group(3)), m.group(4).strip()
    else:
        number, skip, text = None, False, code.strip()

    blk = Block(line=start, number=number, kind="", text=text, comment=comment, skip=skip, end_line=end)
    up = text.upper()
    tokens = text.split()

    if text.startswith("*"):
        blk.kind = "STRUCT"
        blk.comment = text.lstrip("* -").strip()
    elif up == "" and comment:
        blk.kind = "COMMENT"
    elif up.startswith("BEGIN PGM"):
        blk.kind = "BEGIN_PGM"
        blk.data["name"] = tokens[2] if len(tokens) > 2 else ""
        blk.data["unit"] = tokens[3].upper() if len(tokens) > 3 else "MM"
    elif up.startswith("END PGM"):
        blk.kind = "END_PGM"
    elif up.startswith("BLK FORM"):
        blk.kind = "BLK_FORM"
        mm = re.match(r"BLK FORM\s+(0\.1|0\.2|CYLINDER)\s*(.*)", up)
        if not mm:
            raise ParseError(start, "BLK FORM nicht erkannt")
        blk.data["which"] = mm.group(1)
        toks = mm.group(2).split()
        if toks and toks[0] in "XYZ" and len(toks[0]) == 1:
            blk.data["tool_axis"] = toks.pop(0)
        coords, rest = parse_coords(toks, start)
        blk.data["coords"] = coords
        blk.data["extra"] = rest
    elif up.startswith("TOOL CALL"):
        blk.kind = "TOOL_CALL"
        toks = re.findall(r'"[^"]*"|\S+', text[len("TOOL CALL"):])
        d = blk.data
        for tok in toks:
            t = tok.upper()
            if tok.startswith('"'):
                d["tool"] = tok.strip('"')
            elif re.fullmatch(r"\d+(\.\d+)?", t) and "tool" not in d:
                d["tool"] = int(float(t))
            elif t in ("X", "Y", "Z"):
                d["axis"] = t
            elif re.fullmatch(r"S" + _NUM, t):
                d["s"] = Value(t[1:] if t[1] in "+-" else "+" + t[1:])
            elif re.fullmatch(r"F" + _NUM, t):
                d["f"] = Value(t[1:] if t[1] in "+-" else "+" + t[1:])
            elif re.fullmatch(r"(DL|DR2|DR)" + _NUM, t):
                k = re.match(r"(DL|DR2|DR)", t).group(1)
                d[k.lower()] = Value(t[len(k):])
            else:
                raise ParseError(start, f"Unbekanntes Wort im TOOL CALL: {tok}")
    elif re.match(r"WMAT\b", up):
        blk.kind = "WMAT"
        mm = re.match(r'WMAT\s+"([^"]*)"\s*$', text, re.I)
        if not mm:
            raise ParseError(start, 'WMAT erwartet einen Werkstoff in Anführungszeichen: WMAT "AlMg3"')
        blk.data["material"] = mm.group(1)
    elif up.startswith("TOOL DEF"):
        blk.kind = "TOOL_DEF"
        blk.data["tool"] = tokens[2] if len(tokens) > 2 else None
    elif up.startswith("CYCL DEF"):
        blk.kind = "CYCL_DEF"
        mm = re.match(r"CYCL DEF\s+(\d+)(?:\.(\d+))?\s*(.*)", up)
        if not mm:
            raise ParseError(start, "CYCL DEF nicht erkannt")
        blk.data["cycle"] = int(mm.group(1))
        blk.data["sub"] = int(mm.group(2)) if mm.group(2) else None
        head = mm.group(3)
        inline = re.findall(r"\bQ(\d+)\s*=\s*(" + _NUM + r"|PREDEF|FAUTO|FMAX)", head)
        blk.data["head"] = re.sub(r"\s*\bQ\d+\s*=\s*\S+", "", head).strip()
        params, names = _parse_cycle_params(raw)
        for q, v in inline:  # einzeilige Form: CYCL DEF 200 BOHREN Q200=+2 Q201=-10 ...
            params.setdefault(int(q), Value(v if v[0] in "+-PF" else "+" + v))
        blk.data["params"] = params
        blk.data["param_names"] = names
    elif up.startswith("PATTERN DEF"):
        blk.kind = "PATTERN"
        blk.data["points"] = _parse_pattern(raw, start)
    elif up.startswith("TRANS DATUM"):
        blk.kind = "TRANS"
        if "RESET" in up:
            blk.data["reset"] = True
        else:
            coords, _ = parse_coords(text.split()[3:] if "AXIS" in up else text.split()[2:], start)
            blk.data["coords"] = coords
    elif up.startswith("CYCL CALL"):
        blk.kind = "CYCL_CALL"
        rest = tokens[2:]
        if rest and rest[0].upper() in ("PAT", "POS"):
            blk.data["variant"] = rest.pop(0).upper()
        _parse_feed_and_m(rest, blk.data, start, allow_r=False)
    elif re.match(r"LBL\b", up):
        blk.kind = "LBL"
        arg = text[3:].strip()
        blk.data["label"] = arg.strip('"') if arg.startswith('"') else int(arg)
    elif up.startswith("CALL LBL"):
        blk.kind = "CALL_LBL"
        mm = re.match(r'CALL LBL\s+("[^"]+"|\d+)\s*(?:REP\s*(\d+)(?:/\d+)?)?\s*$', text, re.I)
        if not mm:
            raise ParseError(start, "CALL LBL nicht erkannt")
        lab = mm.group(1)
        blk.data["label"] = lab.strip('"') if lab.startswith('"') else int(lab)
        blk.data["rep"] = int(mm.group(2)) if mm.group(2) else 0
    elif up.startswith("CALL PGM"):
        blk.kind = "CALL_PGM"
        blk.data["path"] = text[8:].strip().strip('"')
    elif re.match(r"FN\s*\d+\s*:", up):
        blk.kind = "QFORMULA"
        blk.data.update(_parse_fn(up, start))
    elif re.match(r"Q[LR]?\d+\s*=", up):
        blk.kind = "QFORMULA"
        lhs, rhs = up.split("=", 1)
        blk.data["target"] = lhs.strip()
        blk.data["expr"] = rhs.strip()
    elif up.startswith("FUNCTION RESET TCPM"):
        blk.kind = "TCPM"
        blk.data["on"] = False
    elif up.startswith("FUNCTION TCPM"):
        blk.kind = "TCPM"
        blk.data["on"] = True
        blk.data["options"] = tokens[2:]
    elif re.match(r"PLANE\b", up):
        blk.kind = "PLANE"
        blk.data.update(_parse_plane(raw, start))
    elif up == "STOP" or up.startswith("STOP "):
        blk.kind = "STOP"
        _parse_feed_and_m(tokens[1:], blk.data, start, allow_r=False)
    elif tokens and tokens[0].upper() in ("L", "CC", "C", "CR", "CT"):
        blk.kind = tokens[0].upper()
        coords, rest = parse_coords(tokens[1:], start)
        blk.data["coords"] = coords
        if blk.kind == "CR":
            rr = [t for t in rest if re.fullmatch(r"R" + _NUM, t.upper())]
            if not rr:
                raise ParseError(start, "CR ohne Radius R")
            blk.data["radius"] = Value(rr[0][1:] if rr[0][1] in "+-" else "+" + rr[0][1:])
            rest.remove(rr[0])
        if blk.kind in ("C", "CR"):
            dr = [t for t in rest if t.upper() in ("DR+", "DR-")]
            if not dr:
                raise ParseError(start, f"{blk.kind} ohne Drehsinn DR+ / DR-")
            blk.data["dir"] = dr[0][2]
            rest.remove(dr[0])
        if blk.kind == "CC":
            if rest:
                raise ParseError(start, f"Unbekannte Wörter: {' '.join(rest)}")
        else:
            _parse_feed_and_m(rest, blk.data, start)
    elif tokens and tokens[0].upper() in ("RND", "CHF"):
        blk.kind = tokens[0].upper()
        rest = tokens[1:]
        size = None
        for tok in list(rest):
            t = tok.upper()
            if blk.kind == "RND" and re.fullmatch(r"R" + _NUM, t):
                size = Value(t[1:] if t[1] in "+-" else "+" + t[1:])
                rest.remove(tok)
            elif blk.kind == "CHF" and re.fullmatch(_NUM, t):
                size = Value(t if t[0] in "+-" else "+" + t)
                rest.remove(tok)
        if size is None:
            raise ParseError(start, f"{blk.kind} ohne Größe")
        blk.data["size"] = size
        _parse_feed_and_m(rest, blk.data, start, allow_r=False)
    elif tokens and all(re.fullmatch(r"M\d+", t.upper()) for t in tokens):
        blk.kind = "M"
        blk.data["m"] = [int(t[1:]) for t in tokens]
    else:
        blk.kind = "UNKNOWN"
    return blk


PLANE_MODES = ("SPATIAL", "PROJECTED", "EULER", "VECTOR", "POINTS", "RELATIV", "AXIAL", "RESET")
PLANE_WORDS = {
    "SPATIAL": ("SPA", "SPB", "SPC"),
    "PROJECTED": ("PROPR", "PROMIN", "PROROT"),
    "EULER": ("EULPR", "EULNU", "EULROT"),
    "VECTOR": ("BX", "BY", "BZ", "NX", "NY", "NZ"),
    "POINTS": ("P1X", "P1Y", "P1Z", "P2X", "P2Y", "P2Z", "P3X", "P3Y", "P3Z"),
    "RELATIV": ("SPA", "SPB", "SPC"),
    "AXIAL": ("A", "B", "C"),
    "RESET": (),
}


def _signed(t: str) -> Value:
    return Value(t if t[:1] in "+-" else "+" + t)


def _parse_plane(raw: str, line: int) -> dict:
    """PLANE-Funktion (Bearbeitungsebene schwenken).

    -> {"mode", "values": {wort: Value}, "pos": MOVE|TURN|STAY|None, "mb": None|"MAX"|Value,
        "dist", "f": None|"FMAX"|"FAUTO"|Value, "seq": +1|-1|None, "rot": "COORD"|"TABLE"|None}
    """
    code = " ".join(_split_comment(part)[0] for part in raw.split("\n"))
    code = re.sub(r"^\s*\d+\s*/?\s*", "", code).replace("~", " ")
    toks = code.upper().split()[1:]
    if not toks or toks[0] not in PLANE_MODES:
        raise ParseError(line, "PLANE: Art fehlt (SPATIAL, PROJECTED, EULER, VECTOR, POINTS, RELATIV, AXIAL, RESET)")
    d = {"mode": toks.pop(0), "values": {}, "pos": None, "mb": None, "dist": None, "f": None, "seq": None,
         "rot": None}
    names = sorted(PLANE_WORDS[d["mode"]], key=len, reverse=True)
    i = 0
    while i < len(toks):
        t = toks[i]
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        i += 1
        if t in ("MOVE", "TURN", "STAY"):
            d["pos"] = t
        elif t in ("COORD", "TABLE") and nxt == "ROT":
            d["rot"] = t
            i += 1
        elif re.fullmatch(r"(SEQ|SYM)[+-]", t):
            d["seq"] = 1 if t.endswith("+") else -1
        elif t == "MB" and nxt:
            d["mb"] = "MAX" if nxt == "MAX" else _signed(nxt)
            i += 1
        elif t == "MBMAX":
            d["mb"] = "MAX"
        elif re.fullmatch(r"MB" + _NUM, t):
            d["mb"] = _signed(t[2:])
        elif re.fullmatch(r"DIST" + _NUM, t):
            d["dist"] = _signed(t[4:])
        elif t in ("FMAX", "FAUTO"):
            d["f"] = t
        elif re.fullmatch(r"F" + _NUM, t):
            d["f"] = _signed(t[1:])
        else:
            for n in names:
                if t.startswith(n) and re.fullmatch(_NUM, t[len(n):]):
                    d["values"][n] = _signed(t[len(n):])
                    break
            else:
                raise ParseError(line, f"PLANE: unbekanntes Wort {t}")
    if d["mode"] in ("VECTOR", "POINTS"):
        missing = [n for n in PLANE_WORDS[d["mode"]] if n not in d["values"]]
        if missing:
            raise ParseError(line, f"PLANE {d['mode']}: es fehlen {' '.join(missing)}")
    if d["mode"] == "RELATIV" and len(d["values"]) != 1:
        raise ParseError(line, "PLANE RELATIV: genau einen Winkel SPA, SPB oder SPC angeben")
    if d["mode"] != "RESET" and d["pos"] is None:
        d["pos"] = "STAY"
    return d


def _pattern_words(body: str) -> dict:
    out = {}
    for m in re.finditer(r"(NUMX|NUMY|ROTX|ROTY|START|STEP|NUM|ROT|DX|DY|D|X|Y|Z)\s*([-+]?\d*\.?\d+)", body.upper()):
        out.setdefault(m.group(1), float(m.group(2)))
    return out


def _parse_pattern(raw: str, line: int) -> list[tuple[float, float, float]]:
    """PATTERN DEF: POSn, ROWn, PATn/FRAMEn, CIRCn, PITCHCIRCn -> Punkte (x, y, z)."""
    import math

    pts = []
    text = re.sub(r";[^\n]*", "", raw)
    for m in re.finditer(r"\b(POS|ROW|PAT|FRAME|PITCHCIRC|CIRC)\d*\s*\(([^)]*)\)", text, re.I):
        kind, w = m.group(1).upper(), _pattern_words(m.group(2))
        x0, y0, z = w.get("X", 0.0), w.get("Y", 0.0), w.get("Z", 0.0)
        if kind == "POS":
            pts.append((x0, y0, z))
        elif kind == "ROW":
            a = math.radians(w.get("ROT", 0.0))
            for i in range(int(w.get("NUM", 1))):
                d = i * w.get("D", 0.0)
                pts.append((x0 + d * math.cos(a), y0 + d * math.sin(a), z))
        elif kind in ("PAT", "FRAME"):
            a = math.radians(w.get("ROT", 0.0))
            nx, ny = int(w.get("NUMX", 1)), int(w.get("NUMY", 1))
            for j in range(ny):
                for i in range(nx):
                    if kind == "FRAME" and 0 < i < nx - 1 and 0 < j < ny - 1:
                        continue
                    dx, dy = i * w.get("DX", 0.0), j * w.get("DY", 0.0)
                    pts.append((x0 + dx * math.cos(a) - dy * math.sin(a), y0 + dx * math.sin(a) + dy * math.cos(a), z))
        else:  # CIRC / PITCHCIRC
            n = int(w.get("NUM", 1))
            r = w.get("D", 0.0) / 2
            step = w.get("STEP", 360.0 / n if n else 0.0) if kind == "PITCHCIRC" else 360.0 / max(n, 1)
            for i in range(n):
                a = math.radians(w.get("START", 0.0) + i * step)
                pts.append((x0 + r * math.cos(a), y0 + r * math.sin(a), z))
    if not pts:
        raise ParseError(line, "PATTERN DEF ohne erkennbare Punkte (POS/ROW/PAT/FRAME/CIRC/PITCHCIRC)")
    return pts


_FN_OPS = {1: "+", 2: "-", 3: "*", 4: "/"}


def _parse_fn(up: str, line: int) -> dict:
    m = re.match(r"FN\s*(\d+)\s*:\s*(Q[LR]?\d+)\s*=\s*(.*)$", up)
    if not m:
        raise ParseError(line, "FN-Satz nicht erkannt (Sprünge FN 9..12 folgen später)")
    fn, target, rhs = int(m.group(1)), m.group(2), m.group(3).strip()
    if fn == 0:
        expr = rhs
    elif fn in _FN_OPS:
        toks = rhs.split()
        if len(toks) != 3 or toks[1] not in ("+", "-", "*", "/", "DIV"):
            raise ParseError(line, f"FN {fn}: Form 'a op b' erwartet")
        expr = f"({toks[0]}) {_FN_OPS[fn]} ({toks[2]})"
    elif fn == 5:
        expr = "SQRT(" + rhs.replace("SQRT", "").strip() + ")"
    elif fn == 6:
        expr = "SIN(" + rhs.replace("SIN", "").strip() + ")"
    elif fn == 7:
        expr = "COS(" + rhs.replace("COS", "").strip() + ")"
    elif fn == 8:
        a, b = rhs.split("LEN")
        expr = f"SQRT(SQ({a.strip()}) + SQ({b.strip()}))"
    else:
        raise ParseError(line, f"FN {fn} wird noch nicht unterstützt")
    return {"target": target, "expr": expr, "fn": fn}


@dataclass
class Program:
    name: str
    unit: str
    blocks: list[Block]
    source: list[str]


def parse_program(text: str) -> tuple[Program, list[ParseError]]:
    """Parst ein komplettes Dialogprogramm. Fehler werden gesammelt, nicht geworfen."""
    lines = text.splitlines()
    blocks, errors = [], []
    for start, end, raw in _join_continuations(lines):
        try:
            blk = parse_block(start, end, raw)
        except ParseError as e:
            errors.append(e)
            continue
        except (ValueError, IndexError) as e:  # defensive: nie den Editor abstürzen lassen
            errors.append(ParseError(start, str(e)))
            continue
        if blk is not None:
            if blk.kind == "UNKNOWN":
                errors.append(ParseError(start, f"Unbekannter Satz: {blk.text}"))
            blocks.append(blk)
    name, unit = "", "MM"
    for b in blocks:
        if b.kind == "BEGIN_PGM":
            name, unit = b.data["name"], b.data["unit"]
            break
    return Program(name, unit, blocks, lines), errors
