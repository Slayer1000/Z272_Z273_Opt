"""Bahn-Tracer für RS274NGC (LinuxCNC-Dialekt, Teilmenge).

Liefert die Werkzeugbahn eines G-Code-Programms als Liste von Bewegungen mit
G-Code-Zeilennummer. Grundlage für den Arbeitsbereich Simulation, den Ausführungs-
cursor in der Testsimulation und (später) die Abtragssimulation.

Unterstützt: G0/G1/G2/G3 (G17, I/J oder R, Helix), G90/G91, G4, G17/18/19 (Bögen nur
G17), Parameter (#1, #<lokal>, #<_global>, #5420..), Ausdrücke mit Funktionen,
O-Wörter sub/endsub/call/return, repeat, while, do, if/elseif/else, externe
Unterprogramme aus SUBROUTINE_PATH, G52, geschwenkte Bearbeitungsebene G68.2/G68.4/G69
(P0..P3, R) mit Ausrichtung G53.1/G53.2/G53.3/G53.6 über die Maschinenkinematik (``orient``).
Die Bewegungen werden in Werkstückkoordinaten (G5x) ausgegeben, also bereits durch
G52 und die geschwenkte Ebene transformiert.

Hinweis: Auf einer Maschine mit installiertem LinuxCNC ist der Original-Interpreter
(Modul ``gcode``) die Referenz. Dieser Tracer dient der Vorschau ohne LinuxCNC und
wird mit Tests gegen den Original-Interpreter abgeglichen.
"""

from __future__ import annotations

from ..i18n import _t

import math
import os
import re
from dataclasses import dataclass, field

AXES = "XYZABCUVW"


class TraceError(Exception):
    def __init__(self, line: int, msg: str, file: str = ""):
        super().__init__(_t('{0} Zeile {1}: {2}').format(os.path.basename(file) or 'Programm', line + 1, msg))
        self.line = line
        self.file = file


@dataclass
class Move:
    kind: str  # rapid | feed | arc
    line: int  # Zeile im Hauptprogramm (bei Unterprogrammen: Aufrufzeile)
    points: list  # [(x,y,z,a,b,c), ...] inkl. Startpunkt
    feed: float = 0.0
    tool: int = 0
    start_known: bool = True  # False: Startpunkt angenommen (Programmanfang, nach Werkzeugwechsel)


@dataclass
class TraceResult:
    moves: list[Move] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    bounds: tuple | None = None  # ((minx,miny,minz),(maxx,maxy,maxz)) der Vorschubbewegungen
    # Ereignisse ohne Bewegung für Programm-Test/Zeit: (Bewegungsindex davor, Art, Wert, G-Code-Zeile)
    # Art: "dwell" (Sekunden), "stop" (M0), "optstop" (M1), "toolchange" (Werkzeugnummer)
    events: list = field(default_factory=list)
    # vom Programm mit G28.1/G30.1 gesetzte Rückzugspunkte {5161: Maschinenwert, …}
    home_set: dict = field(default_factory=dict)


# ----------------------------------------------------------------- Ausdrücke
_ETOK = re.compile(
    r"\s*(?:(?P<num>\d+\.?\d*|\.\d+)|(?P<par>#<[^>]+>|#\d+)|(?P<word>[A-Z_]+)|(?P<op>\*\*|[-+*/\[\]#]))",
    re.I,
)
_FUNCS = {
    "SIN": lambda x: math.sin(math.radians(x)),
    "COS": lambda x: math.cos(math.radians(x)),
    "TAN": lambda x: math.tan(math.radians(x)),
    "ASIN": lambda x: math.degrees(math.asin(x)),
    "ACOS": lambda x: math.degrees(math.acos(x)),
    "SQRT": math.sqrt,
    "ABS": abs,
    "FIX": math.floor,
    "FUP": math.ceil,
    "ROUND": lambda x: float(round(x)),
    "LN": math.log,
    "EXP": math.exp,
}
_BINOPS = [
    {"OR": lambda a, b: float(bool(a) or bool(b)), "XOR": lambda a, b: float(bool(a) != bool(b)),
     "AND": lambda a, b: float(bool(a) and bool(b))},
    {"EQ": lambda a, b: float(a == b), "NE": lambda a, b: float(a != b), "GT": lambda a, b: float(a > b),
     "GE": lambda a, b: float(a >= b), "LT": lambda a, b: float(a < b), "LE": lambda a, b: float(a <= b)},
    {"+": lambda a, b: a + b, "-": lambda a, b: a - b},
    {"*": lambda a, b: a * b, "/": lambda a, b: a / b, "MOD": lambda a, b: math.fmod(a, b)},
    {"**": lambda a, b: a ** b},
]


class _Expr:
    def __init__(self, text: str, lookup):
        self.toks = []
        pos = 0
        text = text.strip()
        while pos < len(text):
            m = _ETOK.match(text, pos)
            if not m or m.end() == pos:
                raise ValueError(_t('Ausdruck nicht lesbar: {0!r}').format(text[pos:]))
            pos = m.end()
            self.toks.append((m.lastgroup, m.group(m.lastgroup).upper() if m.lastgroup != "par" else m.group("par")))
        self.i = 0
        self.lookup = lookup

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def take(self):
        t = self.peek()
        self.i += 1
        return t

    def value(self):
        v = self.binary(0)
        return v

    def binary(self, level):
        if level == len(_BINOPS):
            return self.unary()
        v = self.binary(level + 1)
        while True:
            k, t = self.peek()
            if t in _BINOPS[level]:
                self.take()
                v = _BINOPS[level][t](v, self.binary(level + 1))
            else:
                return v

    def unary(self):
        k, t = self.peek()
        if t == "-":
            self.take()
            return -self.unary()
        if t == "+":
            self.take()
            return self.unary()
        return self.atom()

    def atom(self):
        k, t = self.take()
        if k == "num":
            return float(t)
        if k == "par":
            return self.lookup(t)
        if t == "[":
            v = self.binary(0)
            if self.take()[1] != "]":
                raise ValueError(_t("fehlende ]"))
            return v
        if t == "#":
            return self.lookup("#%d" % int(self.atom()))
        if k == "word":
            if t == "ATAN":
                y = self.atom()
                if self.take()[1] != "/":
                    raise ValueError("ATAN[y]/[x] erwartet")
                x = self.atom()
                return math.degrees(math.atan2(y, x))
            if t == "EXISTS":
                return 1.0
            if t in _FUNCS:
                return _FUNCS[t](self.atom())
        raise ValueError(_t('Unerwartet im Ausdruck: {0}').format(t))


# ----------------------------------------------------------------- Interpreter
_OWORD = re.compile(r"^O\s*(<[^>]+>|\d+)\s*(SUB|ENDSUB|CALL|RETURN|REPEAT|ENDREPEAT|WHILE|ENDWHILE|DO|IF|ELSEIF|ELSE|ENDIF|BREAK|CONTINUE)\b(.*)$", re.I)


def _strip(line: str) -> str:
    line = re.sub(r"\([^)]*\)", "", line)
    line = line.split(";", 1)[0]
    return line.strip()


@dataclass
class _File:
    path: str
    lines: list[str]


@dataclass
class _Frame:
    file: _File
    ret_pc: int
    locals: dict
    call_line: int
    label: str


def _rot(axis: int, deg: float):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    if axis == 1:
        return [[1, 0, 0], [0, c, -s], [0, s, c]]
    if axis == 2:
        return [[c, 0, s], [0, 1, 0], [-s, 0, c]]
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def _mm(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _mv(a, v):
    return [sum(a[i][k] * v[k] for k in range(3)) for i in range(3)]


def _mtv(a, v):  # transponiert * v
    return [sum(a[k][i] * v[k] for k in range(3)) for i in range(3)]


def _unit(v):
    n = math.sqrt(sum(x * x for x in v))
    if n < 1e-12:
        raise ValueError(_t("Nullvektor in G68.2"))
    return [x / n for x in v]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _frame(xd, zd):
    x = _unit(xd)
    z = list(zd)
    d = sum(x[i] * z[i] for i in range(3))
    z = _unit([z[i] - d * x[i] for i in range(3)])
    y = _cross(z, x)
    return [[x[i], y[i], z[i]] for i in range(3)]  # Spalten = Achsen der Ebene


class Tracer:
    def __init__(self, subroutine_path: list[str] | None = None, max_moves: int = 500000, arc_seg_deg: float = 6.0,
                 tool_lengths: dict | None = None, tool_radii: dict | None = None, orient=None,
                 work_offset=None, params: dict | None = None):
        self.subpath = subroutine_path or []
        # Startwerte nummerierter Parameter (z. B. G28/G30-Position #5161…, #5181… aus der .var-Datei)
        self.start_params = dict(params or {})
        # Lage des G5x-Nullpunkts in Maschinenkoordinaten (X, Y, Z): macht G53-Bewegungen berechenbar
        self.work_offset = work_offset
        # orient(normale) -> {"B": winkel, ...}: Drehachsstellung für G53.x (Maschinenmodell)
        self.orient = orient
        self.tool_radii = tool_radii or {}
        # Werkzeuglängen {T: L}: G43 ändert die Programm-Z-Position, die Maschine bleibt stehen
        self.tool_lengths = tool_lengths or {}
        self.max_moves = max_moves
        self.arc_seg = math.radians(arc_seg_deg)

    # -- Parameter
    def _get(self, name: str):
        if name.startswith("#<"):
            key = name[2:-1].lower()
            store = self.globals if key.startswith("_") else self.frames[-1].locals
            if key not in store:
                raise ValueError(_t('Parameter {0} nicht gesetzt').format(name))
            return store[key]
        n = int(name[1:])
        if 5420 <= n <= 5428:
            return self.pos[n - 5420]
        if n == 5410:
            return 0.0
        if 1 <= n <= 30:
            return self.frames[-1].locals.get(n, 0.0)
        return self.numbered.get(n, 0.0)

    def _set(self, name: str, v: float):
        if name.startswith("#<"):
            key = name[2:-1].lower()
            (self.globals if key.startswith("_") else self.frames[-1].locals)[key] = v
        else:
            n = int(name[1:])
            if 1 <= n <= 30:
                self.frames[-1].locals[n] = v
            else:
                self.numbered[n] = v

    def eval(self, text: str) -> float:
        e = _Expr(text, self._get)
        v = e.value()
        if e.i != len(e.toks):
            raise ValueError(_t('Ausdruck unvollständig: {0}').format(text))
        return v

    # -- Dateien / Unterprogramme
    def _load_sub(self, name: str) -> tuple[_File, int]:
        if name in self.subs:
            return self.subs[name]
        for d in self.subpath:
            p = os.path.join(d, name.strip("<>") + ".ngc")
            if os.path.exists(p):
                with open(p, encoding="utf-8", errors="replace") as f:
                    fobj = _File(p, f.read().splitlines())
                self._index_subs(fobj)
                if name in self.subs:
                    return self.subs[name]
        raise ValueError(_t('Unterprogramm o{0} nicht gefunden').format(name))

    def _index_subs(self, f: _File):
        for i, raw in enumerate(f.lines):
            m = _OWORD.match(_strip(raw))
            if m and m.group(2).upper() == "SUB":
                self.subs[m.group(1).lower()] = (f, i)

    def _find(self, f: _File, start: int, label: str, kinds: tuple[str, ...]) -> int:
        depth_label = label.lower()
        for i in range(start, len(f.lines)):
            m = _OWORD.match(_strip(f.lines[i]))
            if m and m.group(1).lower() == depth_label and m.group(2).upper() in kinds:
                return i
        raise ValueError(f"o{label}: kein passendes {'/'.join(kinds)}")

    # -- Hauptschleife
    def trace_text(self, text: str, path: str = "", start_pos=None) -> TraceResult:
        self.res = TraceResult()
        self.globals: dict = {}
        self.numbered: dict = dict(self.start_params)
        self.subs: dict = {}
        self.pos = list(start_pos) if start_pos else [0.0] * 9
        self.absolute = True
        self.motion = 0
        self.feed = 0.0
        self.plane = 17
        self.tool = 0
        self.tlo = 0.0
        self.known = False
        self.comp = None  # (seite +1 links / -1 rechts, radius)
        self.comp_buf = []
        self.base_shift = [0.0, 0.0, 0.0]  # G52/G92 unter der Ebene
        self.twp = None  # (Ursprung in G5x, Drehmatrix) der geschwenkten Ebene
        self.plane_shift = [0.0, 0.0, 0.0]  # G52 in der Ebene
        self.twp_pending = None  # mehrsätzige G68.2 P2/P3-Definition
        main = _File(path, text.splitlines())
        self._index_subs(main)
        self.frames = [_Frame(main, -1, {}, -1, "")]
        f, pc = main, 0
        loops: list = []
        steps = 0
        try:
            while pc < len(f.lines):
                steps += 1
                if steps > 5_000_000:
                    raise ValueError(_t("Endlosschleife?"))
                raw = f.lines[pc]
                line = _strip(raw)
                main_line = pc if len(self.frames) == 1 else self.frames[1].call_line
                if not line or line == "%":
                    pc += 1
                    continue
                m = _OWORD.match(line)
                if m:
                    f, pc, loops = self._oword(m, f, pc, loops, main_line)
                    continue
                am = re.match(r"^(#<[^>]+>|#\d+)\s*=\s*(.+)$", line)
                if am:
                    self._set(am.group(1), self.eval(am.group(2)))
                    pc += 1
                    continue
                if self._exec_line(line, main_line):
                    break
                pc += 1
        except (ValueError, ZeroDivisionError) as e:
            self.res.errors.append(str(TraceError(pc, str(e), f.path)))
        self._flush_comp(None)
        self._bounds()
        return self.res

    def _oword(self, m, f, pc, loops, main_line):
        label, kw, rest = m.group(1).lower(), m.group(2).upper(), m.group(3).strip()
        if kw == "SUB":
            return f, self._find(f, pc + 1, label, ("ENDSUB",)) + 1, loops
        if kw == "CALL":
            args = [self.eval(a) for a in re.findall(r"\[[^\]]*(?:\[[^\]]*\][^\]]*)*\]", rest)]
            sf, start = self._load_sub(label)
            loc = {i + 1: v for i, v in enumerate(args)}
            self.frames.append(_Frame(f, pc + 1, loc, main_line, label))
            loops.append(("CALLMARK", len(self.frames)))
            return sf, start + 1, loops
        if kw in ("ENDSUB", "RETURN"):
            if len(self.frames) == 1:
                return f, pc + 1, loops
            fr = self.frames.pop()
            while loops and loops[-1] != ("CALLMARK", len(self.frames) + 1):
                loops.pop()
            if loops:
                loops.pop()
            return fr.file, fr.ret_pc, loops
        if kw == "REPEAT":
            n = int(self.eval(rest))
            if n <= 0:
                return f, self._find(f, pc + 1, label, ("ENDREPEAT",)) + 1, loops
            loops.append(("REPEAT", label, pc, n))
            return f, pc + 1, loops
        if kw == "ENDREPEAT":
            _, lab, start, n = loops.pop()
            if n > 1:
                loops.append(("REPEAT", lab, start, n - 1))
                return f, start + 1, loops
            return f, pc + 1, loops
        if kw == "WHILE":
            if self.eval(rest):
                loops.append(("WHILE", label, pc))
                return f, pc + 1, loops
            return f, self._find(f, pc + 1, label, ("ENDWHILE",)) + 1, loops
        if kw == "ENDWHILE":
            if rest:  # do ... while
                start = loops[-1][2]
                if self.eval(rest):
                    return f, start + 1, loops
                loops.pop()
                return f, pc + 1, loops
            _, lab, start = loops.pop()
            return f, start, loops
        if kw == "DO":
            loops.append(("DO", label, pc))
            return f, pc + 1, loops
        if kw == "IF":
            return f, self._branch(f, pc, label, self.eval(rest)), loops
        if kw in ("ELSEIF", "ELSE"):
            return f, self._find(f, pc + 1, label, ("ENDIF",)) + 1, loops
        if kw == "ENDIF":
            return f, pc + 1, loops
        if kw == "BREAK":
            kind = loops.pop()
            end = {"REPEAT": "ENDREPEAT", "WHILE": "ENDWHILE", "DO": "ENDWHILE"}[kind[0]]
            return f, self._find(f, pc + 1, label, (end,)) + 1, loops
        if kw == "CONTINUE":
            kind = loops[-1]
            end = {"REPEAT": "ENDREPEAT", "WHILE": "ENDWHILE", "DO": "ENDWHILE"}[kind[0]]
            return f, self._find(f, pc + 1, label, (end,)), loops
        raise ValueError(_t('O-Wort {0} nicht unterstützt').format(kw))

    def _branch(self, f, pc, label, cond):
        if cond:
            return pc + 1
        i = pc + 1
        while True:
            i = self._find(f, i, label, ("ELSEIF", "ELSE", "ENDIF"))
            m = _OWORD.match(_strip(f.lines[i]))
            kw = m.group(2).upper()
            if kw == "ENDIF" or kw == "ELSE":
                return i + 1
            if self.eval(m.group(3)):
                return i + 1
            i += 1

    # -- Sätze
    def _words(self, line: str) -> list[tuple[str, float]]:
        out = []
        i = 0
        s = line.upper()
        while i < len(s):
            ch = s[i]
            if ch.isspace():
                i += 1
                continue
            if not ch.isalpha():
                raise ValueError(_t('Unerwartetes Zeichen {0!r}').format(ch))
            i += 1
            while i < len(s) and s[i].isspace():
                i += 1
            if i < len(s) and s[i] == "[":
                depth, j = 0, i
                while j < len(s):
                    depth += s[j] == "["
                    depth -= s[j] == "]"
                    j += 1
                    if depth == 0:
                        break
                out.append((ch, self.eval(line[i:j])))
                i = j
            elif i < len(s) and s[i] == "#":
                m = re.match(r"#<[^>]+>|#\d+", line[i:])
                out.append((ch, self._get(m.group(0))))
                i += m.end()
            else:
                m = re.match(r"[-+]?(?:\d+\.?\d*|\.\d+)", s[i:])  # 0.  .5  1.25  -3
                if not m:
                    raise ValueError(_t('Zahl nach {0} erwartet').format(ch))
                out.append((ch, float(m.group(0))))
                i += m.end()
        return out

    # -- Koordinatensysteme: Programm (in der Ebene) <-> Werkstück (G5x)
    def _to_work(self, p):
        if self.twp is None:
            return [p[i] + self.base_shift[i] for i in range(3)]
        o, r = self.twp
        v = _mv(r, [p[i] + self.plane_shift[i] for i in range(3)])
        return [o[i] + v[i] for i in range(3)]

    def _from_work(self, w):
        if self.twp is None:
            return [w[i] - self.base_shift[i] for i in range(3)]
        o, r = self.twp
        v = _mtv(r, [w[i] - o[i] for i in range(3)])
        return [v[i] - self.plane_shift[i] for i in range(3)]

    def _xf(self, mv: Move) -> Move:
        if self.twp is None and not any(self.base_shift):
            return mv
        mv.points = [tuple(self._to_work(p[:3])) + tuple(p[3:]) for p in mv.points]
        return mv

    def _set_frame(self, twp):
        w = self._to_work(self.pos[:3])
        self.twp = twp
        if twp is None:
            self.plane_shift = [0.0, 0.0, 0.0]
        self.pos[:3] = self._from_work(w)

    def _special(self, words, gs, main_line) -> bool:
        """G52, G68.x/G69, G53.x, G12.1/G13.1. -> True wenn behandelt."""
        wd = {l: v for l, v in words if l != "G"}
        if 52.0 in gs:
            w = self._to_work(self.pos[:3])
            tgt = self.plane_shift if self.twp is not None else self.base_shift
            for i, a in enumerate("XYZ"):
                if a in wd:
                    tgt[i] = wd[a]
            self.pos[:3] = self._from_work(w)
            return True
        if 69.0 in gs:
            self._set_frame(None)
            self.twp_pending = None
            return True
        if 12.1 in gs or 13.1 in gs:
            return True
        if 68.3 in gs:
            self.res.messages.append("G68.3 (Ebene aus der Werkzeugachse) wird in der Vorschau nicht dargestellt")
            return True
        if 68.2 in gs or 68.4 in gs:
            self._g68(wd, relative=68.4 in gs)
            return True
        for g in (53.1, 53.2, 53.3, 53.6):
            if g in gs:
                self._g53x(g, wd, main_line)
                return True
        return False

    def _g68(self, wd, relative):
        if relative and self.twp is None:
            raise ValueError("G68.4 ohne aktive Ebene")
        p = int(wd.get("P", 0))
        xyz = [wd.get(a, 0.0) for a in "XYZ"]
        rr = wd.get("R", 0.0)
        r = None
        if p in (0, 1):
            q = str(int(wd.get("Q", 313 if p == 0 else 123)))
            if len(q) != 3 or any(c not in "123" for c in q):
                raise ValueError(f"G68.2 Q{q} ungültig")
            ang = [wd.get(a, 0.0) for a in "IJK"]
            r = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
            for k in range(3):
                m = _rot(int(q[k]), ang[k])
                r = _mm(r, m) if p == 0 else _mm(m, r)
        elif p == 3:
            q = int(wd.get("Q", 1))
            if q == 1:
                self.twp_pending = {"P": 3, "xyz": xyz, "x": [wd.get(a, 0.0) for a in "IJK"], "R": rr}
                return
            pend = self.twp_pending
            if not pend or pend.get("P") != 3:
                raise ValueError("G68.2 P3 Q2 ohne Q1")
            self.twp_pending = None
            r = _frame(pend["x"], [wd.get(a, 0.0) for a in "IJK"])
            xyz, rr = pend["xyz"], pend["R"]
        elif p == 2:
            q = int(wd.get("Q", 1))
            pend = self.twp_pending if self.twp_pending and self.twp_pending.get("P") == 2 else {"P": 2, "R": 0.0}
            pend[q] = xyz
            pend["R"] = pend["R"] or rr
            self.twp_pending = pend
            if q != 3:
                return
            self.twp_pending = None
            p1, p2, p3 = pend[1], pend[2], pend[3]
            xd = [p2[i] - p1[i] for i in range(3)]
            yd = [p3[i] - p1[i] for i in range(3)]
            r = _frame(xd, _cross(xd, yd))
            if 0 in pend:  # Q0: Verschiebung entlang der Ebene (nach R)
                r2 = _mm(r, _rot(3, pend["R"]))
                sh = _mv(r2, pend[0])
                p1 = [p1[i] + sh[i] for i in range(3)]
            xyz, rr = p1, pend["R"]
        else:
            raise ValueError(f"G68.2 P{p} nicht unterstützt")
        if rr:
            r = _mm(r, _rot(3, rr))
        if relative:
            o_old, r_old = self.twp
            v = _mv(r_old, xyz)
            o = [o_old[i] + v[i] for i in range(3)]
            r = _mm(r_old, r)
        else:
            o = [self.base_shift[i] + xyz[i] for i in range(3)]
        self._set_frame((o, r))

    def _g53x(self, g, wd, main_line):
        if self.twp is None:
            raise ValueError(f"G{g} ohne geschwenkte Ebene (G68.2)")
        normal = [row[2] for row in self.twp[1]]
        if self.orient is None:
            self.res.messages.append(f"G{g}: kein Maschinenmodell, Drehachsen in der Vorschau nicht gestellt")
            return
        try:
            sol = self.orient(normal)
        except ValueError as e:
            raise ValueError(f"G{g}: {e}")
        new = list(self.pos)
        for ax, v in sol.items():
            new[AXES.index(ax)] = v
        if g == 53.2:
            for i, ax in enumerate("XYZABC"):
                val = new[i]
                self.globals[f"_orient_{ax.lower()}"] = val
                self.numbered[5071 + i] = val
            self.globals["_orient_valid"] = 1.0
            self.numbered[5080] = 1.0
            return
        if g == 53.3:
            for i, a in enumerate("XYZ"):
                if a in wd:
                    new[i] = wd[a]
        self._add(Move("rapid", main_line, [tuple(self.pos[:6]), tuple(new[:6])], self.feed, self.tool))
        self.pos = new
        if g == 53.1:  # Linearachsen bleiben stehen: die Spitze schwenkt mit -> Lage unbekannt
            self.known = False

    def _exec_line(self, line: str, main_line: int) -> bool:
        words = self._words(line)
        gs = {round(v, 1) for l, v in words if l == "G"}
        if gs & {52.0, 69.0, 12.1, 13.1, 68.2, 68.3, 68.4, 53.1, 53.2, 53.3, 53.6}:
            if self._special(words, gs, main_line):
                return False
        target = list(self.pos)
        has_axis = False
        ij = {}
        r = None
        motion = None
        comp_cmd = None
        hval = next((v for l, v in words if l == "H"), None)
        dval = next((v for l, v in words if l == "D"), None)
        gset = {round(v, 1) for l, v in words if l == "G"}
        if 4.0 in gset:
            pval = next((v for l, v in words if l == "P"), 0.0)
            self.res.events.append((len(self.res.moves), "dwell", float(pval), main_line))
        for letter, v in words:
            if letter == "M" and int(v) in (0, 1, 6):
                kind = {0: "stop", 1: "optstop", 6: "toolchange"}[int(v)]
                tval = next((t for l, t in words if l == "T"), self.tool)
                self.res.events.append((len(self.res.moves), kind, float(tval), main_line))
            if letter == "G":
                g = round(v, 1)
                if g == 43 or g == 49:
                    new = 0.0 if g == 49 else self.tool_lengths.get(int(hval) if hval is not None else self.tool, 0.0)
                    self.pos[2] += self.tlo - new
                    self.tlo = new
                    self.known = False
                    continue
                if g in (40.0, 41.0, 42.0, 41.1, 42.1):
                    comp_cmd = g
                    continue
                if g == 33.1:
                    motion = 331
                elif g in (0, 1, 2, 3):
                    motion = int(g)
                elif g == 90:
                    self.absolute = True
                elif g == 91:
                    self.absolute = False
                elif g in (17, 18, 19):
                    self.plane = int(g)
            elif letter in AXES:
                k = AXES.index(letter)
                target[k] = v if self.absolute else self.pos[k] + v
                has_axis = True
            elif letter in "IJK":
                ij[letter] = v
            elif letter == "R":
                r = v
            elif letter == "F":
                self.feed = v
            elif letter == "T":
                self.tool = int(v)
            elif letter == "M" and int(v) in (2, 30):
                return True
        if motion == 331:  # Gewindebohren synchronisiert: hinein und zurück zum Startpunkt
            down = list(self.pos)
            down[2] = target[2]
            self._add(Move("feed", main_line, [tuple(self.pos[:6]), tuple(down[:6])], self.feed, self.tool))
            self._add(Move("feed", main_line, [tuple(down[:6]), tuple(self.pos[:6])], self.feed, self.tool))
            return False
        if motion is not None:
            self.motion = motion
        exit_comp = False
        if comp_cmd is not None:
            if comp_cmd == 40.0:
                exit_comp = self.comp is not None
            else:
                side = 1 if comp_cmd in (41.0, 41.1) else -1
                if comp_cmd in (41.1, 42.1):
                    rad = (dval or 0.0) / 2
                else:
                    rad = self.tool_radii.get(int(dval) if dval else self.tool, 0.0)
                self._flush_comp(None)
                self.comp = (side, rad) if rad > 0 else None
                self.comp_buf = []
        home = 28.0 if 28.0 in gset else 30.0 if 30.0 in gset else None
        if home is not None:
            self._home_move(home, words, target, has_axis, main_line)
            return False
        if gset & {28.1, 30.1}:  # aktuelle Lage als G28-/G30-Position merken (Maschinenkoordinaten)
            base = 5161 if 28.1 in gset else 5181
            if self.work_offset is not None and self.twp is None and self.known:
                for k in range(6):
                    v = self.pos[k] + (self.work_offset[k] + (self.tlo if k == 2 else 0.0) if k < 3 else 0.0)
                    self.numbered[base + k] = v
                    self.res.home_set[base + k] = v
            return False
        if has_axis and 53.0 in gs and self.work_offset is not None and self.twp is None and self.known:
            # Maschinenkoordinaten bei bekanntem Nullpunkt: in G5x-Koordinaten umrechnen
            tgt = list(self.pos)
            for letter, v in words:
                if letter in AXES:
                    k = AXES.index(letter)
                    tgt[k] = v - (self.work_offset[k] + (self.tlo if k == 2 else 0.0) if k < 3 else 0.0)
            self._add(Move("rapid" if (motion if motion is not None else self.motion) == 0 else "feed", main_line,
                           [tuple(self.pos[:6]), tuple(tgt[:6])], self.feed, self.tool))
            self.pos = tgt
            return False
        if has_axis and 53.0 in gs:
            # Maschinenkoordinaten: Lage im Werkstücksystem unbekannt (Vorschau ohne Maschinenmodell)
            for i, a in enumerate(AXES):
                if i >= 3 and target[i] != self.pos[i]:
                    self.pos[i] = target[i]
            self.known = False
            return False
        if has_axis:
            if self.motion in (2, 3):
                pw = next((v for l, v in words if l == "P"), None)
                self._arc(target, ij, r, main_line, turns=int(round(pw)) if pw is not None else 1)
            else:
                self._add(Move("rapid" if self.motion == 0 else "feed", main_line,
                               [tuple(self.pos[:6]), tuple(target[:6])], self.feed, self.tool))
            self.pos = target
        if exit_comp:
            exit_mv = self.comp_buf.pop() if self.comp_buf else None
            self._flush_comp(exit_mv)
            self.comp = None
        return False

    def _home_move(self, home, words, target, has_axis, line):
        """G28/G30 wie LinuxCNC: Eilgang zum Zwischenpunkt (Achsworte, G90/G91 beachtet), dann die
        genannten Achsen – ohne Achsworte alle – im Eilgang zur gespeicherten Position
        (#5161… bzw. #5181…, Maschinenkoordinaten)."""
        if has_axis:
            if self.known:
                self._add(Move("rapid", line, [tuple(self.pos[:6]), tuple(target[:6])], self.feed, self.tool))
            # unbekannte Startlage (z. B. G28 G91 Z0. am Programmanfang): Zwischenpunkt nur übernehmen –
            # eine Fahrt dorthin wäre geraten und würde falsche Endschalter-Meldungen erzeugen
            self.pos = list(target)
        named = [AXES.index(l) for l, _ in words if l in AXES]
        axes = named or list(range(len(AXES)))
        base = 5161 if home == 28.0 else 5181
        if self.work_offset is None or self.twp is not None:
            self.known = False  # Lage der Referenzposition im Werkstücksystem unbekannt
            return
        tgt = list(self.pos)
        for k in axes:
            if k >= 6:
                continue
            m = float(self.numbered.get(base + k, 0.0))
            tgt[k] = m - (self.work_offset[k] + (self.tlo if k == 2 else 0.0)) if k < 3 else m
        self._add(Move("rapid", line, [tuple(self.pos[:6]), tuple(tgt[:6])], self.feed, self.tool))
        self.pos = tgt

    # -- Werkzeugradiuskorrektur G41/G42 (wie LinuxCNC: Außenecken Bogen, Innenecken Schnittpunkt)
    def _flush_comp(self, exit_mv):
        buf, self.comp_buf = self.comp_buf, []
        comp, self.comp = self.comp, None
        if not buf:
            if exit_mv:
                self.res.moves.append(self._xf(exit_mv))
            return
        side, rad = comp
        verts = [(buf[0].points[0], buf[0].line, buf[0].kind, buf[0].feed)]
        for mv in buf:
            for q in mv.points[1:]:
                verts.append((q, mv.line, mv.kind, mv.feed))
        pts = [v[0] for v in verts]
        segs = []  # (i0, i1, d, n)
        i0 = 0
        for i in range(1, len(pts)):
            dx, dy = pts[i][0] - pts[i0][0], pts[i][1] - pts[i0][1]
            ln = math.hypot(dx, dy)
            if ln < 1e-7:
                continue
            d = (dx / ln, dy / ln)
            n = (-d[1] * side, d[0] * side)
            segs.append((i0, i, d, n))
            i0 = i
        out = []  # (punkt, zeile, art, vorschub)

        def off(i, n):
            p = pts[i]
            return (p[0] + n[0] * rad, p[1] + n[1] * rad) + tuple(p[2:])

        cur = pts[0]
        for k, (a, b, d, n) in enumerate(segs):
            end = off(b, n)
            if k + 1 < len(segs):
                a2, b2, d2, n2 = segs[k + 1]
                cross = d[0] * d2[1] - d[1] * d2[0]
                convex = cross * side < -1e-9
                if convex:
                    out.append((end, verts[b][1], verts[b][2], verts[b][3]))
                    st = off(b, n2)
                    c = pts[b]
                    a0 = math.atan2(end[1] - c[1], end[0] - c[0])
                    a1 = math.atan2(st[1] - c[1], st[0] - c[0])
                    sw = a1 - a0
                    while sw > math.pi:
                        sw -= 2 * math.pi
                    while sw < -math.pi:
                        sw += 2 * math.pi
                    nseg = max(1, int(abs(sw) / self.arc_seg))
                    for j in range(1, nseg + 1):
                        aa = a0 + sw * j / nseg
                        out.append(((c[0] + rad * math.cos(aa), c[1] + rad * math.sin(aa)) + tuple(c[2:]),
                                    verts[b][1], "arc", verts[b][3]))
                    continue
                if abs(cross) > 1e-9:  # Innenecke: Schnittpunkt der versetzten Geraden
                    p1 = off(a, n)
                    q1 = off(a2, n2)
                    den = d[0] * d2[1] - d[1] * d2[0]
                    t = ((q1[0] - p1[0]) * d2[1] - (q1[1] - p1[1]) * d2[0]) / den
                    end = (p1[0] + d[0] * t, p1[1] + d[1] * t) + tuple(pts[b][2:])
            out.append((end, verts[b][1], verts[b][2], verts[b][3]))
        prev = cur
        for pt, line, kind, feed in out:
            self.res.moves.append(self._xf(Move("rapid" if kind == "rapid" else "feed", line,
                                                [tuple(prev[:6]), tuple(pt[:6])], feed, self.tool)))
            prev = pt
        if exit_mv:
            exit_mv.points[0] = tuple(prev[:6])
            self.res.moves.append(self._xf(exit_mv))

    # Ebenen wie in LinuxCNC: (erste Achse, zweite Achse, Mittelpunkt-Wörter); die dritte Achse läuft
    # als Schraubenlinie mit. G18 rechnet in der Reihenfolge Z, X (Drehsinn von +Y aus gesehen).
    _PLANES = {17: (0, 1, "I", "J"), 18: (2, 0, "K", "I"), 19: (1, 2, "J", "K")}

    def _arc(self, target, ij, r, line, turns: int = 1):
        if self.plane not in self._PLANES:
            raise ValueError(_t("Bögen vorerst nur in G17"))
        a_, b_, ca, cb = self._PLANES[self.plane]
        sx, sy = self.pos[a_], self.pos[b_]
        ex, ey = target[a_], target[b_]
        cw = self.motion == 2
        if r is not None:
            dx, dy = ex - sx, ey - sy
            d = math.hypot(dx, dy)
            if d < 1e-9 or abs(r) < d / 2 - 1e-6:
                raise ValueError(_t("Radius zu klein für Bogen"))
            h = math.sqrt(max(r * r - d * d / 4, 0))
            mx, my = (sx + ex) / 2, (sy + ey) / 2
            # LinuxCNC: R>0 kleiner Bogen, R<0 großer Bogen
            sgn = (1 if cw else -1) * (1 if r > 0 else -1)
            cx, cy = mx + sgn * h * dy / d, my - sgn * h * dx / d
        else:
            cx, cy = sx + ij.get(ca, 0.0), sy + ij.get(cb, 0.0)
        a0 = math.atan2(sy - cy, sx - cx)
        a1 = math.atan2(ey - cy, ex - cx)
        rad = math.hypot(sx - cx, sy - cy)
        if cw:
            sweep = a0 - a1
            if sweep <= 1e-9:
                sweep += 2 * math.pi
            sweep = -sweep
        else:
            sweep = a1 - a0
            if sweep <= 1e-9:
                sweep += 2 * math.pi
        if turns < 1:
            raise ValueError(_t("P beim Bogen muss eine ganze Zahl ≥ 1 sein"))
        sweep += math.copysign(2 * math.pi * (turns - 1), sweep)  # P = Anzahl Umläufe (LinuxCNC)
        seg = self.arc_seg if self.comp is None else math.radians(0.5)  # unter G41/G42 feiner (Eckpunkte genau)
        n = max(2, int(abs(sweep) / seg) + 1)
        pts = []
        for i in range(n + 1):
            t = i / n
            a = a0 + sweep * t
            p = list(self.pos[:6])
            for k in range(6):
                p[k] = self.pos[k] + (target[k] - self.pos[k]) * t
            p[a_] = cx + rad * math.cos(a)
            p[b_] = cy + rad * math.sin(a)
            pts.append(tuple(p))
        pts[-1] = tuple(target[:6])
        self._add(Move("arc", line, pts, self.feed, self.tool))

    def _add(self, mv: Move):
        if len(self.res.moves) >= self.max_moves:
            raise ValueError(_t("Zu viele Bewegungen für die Vorschau"))
        mv.start_known = self.known
        self.known = True
        if self.comp is not None:
            self.comp_buf.append(mv)
            return
        self.res.moves.append(self._xf(mv))

    def _bounds(self):
        pts = [p for m in self.res.moves if m.kind != "rapid" for p in m.points]
        if not pts:
            pts = [p for m in self.res.moves for p in m.points]
        if pts:
            self.res.bounds = (
                tuple(min(p[i] for p in pts) for i in range(3)),
                tuple(max(p[i] for p in pts) for i in range(3)),
            )


def trace(text: str, subroutine_path: list[str] | None = None, path: str = "") -> TraceResult:
    return Tracer(subroutine_path).trace_text(text, path)
