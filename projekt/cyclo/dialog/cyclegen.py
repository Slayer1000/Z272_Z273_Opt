"""Bahnberechnung der Bearbeitungszyklen (Umsetzungsart "python").

Jeder Generator erhält die Zyklusparameter als Zahlen (``P``) und die Werkzeugdaten und
liefert G-Code-Zeilen für ein O-Unterprogramm. Die Bahn wird *relativ zur Aufrufposition*
ausgegeben: Das Unterprogramm merkt sich beim Aufruf die aktuelle Position (#5420/#5421)
und alle XY-Koordinaten werden als ``X[#<cx>+dx]`` geschrieben. So funktioniert derselbe
Zyklus an jeder Aufrufposition (``L X.. Y.. M99``, ``CYCL CALL PAT``, Muster 220/221).

Eigene Bahnberechnung je Zyklus, Vereinfachungen sind vermerkt.
"""

from __future__ import annotations

from ..i18n import _t
from . import pathgeom as pg

import math
from dataclasses import dataclass, field


class CycleError(Exception):
    pass


@dataclass
class Tool:
    number: int | None = None
    radius: float | None = None
    length: float = 0.0
    angle: float = 0.0  # Eintauchwinkel ANGLE (Helix/Pendeln)
    t_angle: float = 0.0  # Spitzenwinkel T-ANGLE (Bohrer, Zentrierer)
    feed: str | None = None  # F aus TOOL CALL (für FAUTO)

    def r(self) -> float:
        if self.radius is None or self.radius <= 0:
            raise CycleError(_t('Werkzeugradius von T{0} unbekannt – Werkzeugtabelle prüfen').format(self.number))
        return self.radius


def fmt(v: float) -> str:
    if abs(v) < 5e-7:
        return "0"
    return f"{v:.4f}".rstrip("0").rstrip(".")


class P(dict):
    """Zyklusparameter: Zahl oder Vorschub-Text (z. B. '#<_cyclo_fauto>')."""

    def n(self, q, default=0.0) -> float:
        v = self.get(q, default)
        if isinstance(v, str):
            raise CycleError(_t('Q{0}: Zahlenwert erwartet').format(q))
        return float(v)

    def f(self, q, default=None) -> str:
        v = self.get(q, default)
        if v is None:
            raise CycleError(_t('Vorschub Q{0} fehlt').format(q))
        return v if isinstance(v, str) else fmt(v)


@dataclass
class Emit:
    """Schreibt Bewegungen relativ zum Aufrufpunkt (rel=True) oder absolut."""

    rel: bool = True
    rot: float = 0.0  # Drehlage in Grad (um den Aufrufpunkt)
    lines: list = field(default_factory=list)
    cur: tuple | None = None  # aktuelle Position im lokalen System (x, y)
    warn: list = field(default_factory=list)
    # Spiegeln/Maßfaktor (Zyklus 8/11/26): x' = fx*x + ox (Vorzeichen von fx = gespiegelt);
    # bei Bahnen relativ zum Aufrufpunkt gilt nur fx
    fx: float = 1.0
    fy: float = 1.0
    fz: float = 1.0
    ox: float = 0.0
    oy: float = 0.0
    oz: float = 0.0

    @property
    def mirrored(self) -> bool:
        return self.fx * self.fy < 0

    def _rot(self, x, y):
        if self.rot:
            a = math.radians(self.rot)
            x, y = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
        return x, y

    def _tz(self, z):
        return self.oz + self.fz * z

    def _xy(self, x, y):
        gx, gy = self._rot(x, y)
        if self.rel:
            gx, gy = gx * self.fx, gy * self.fy
        else:
            gx, gy = self.ox + self.fx * gx, self.oy + self.fy * gy
        if self.rel:
            return (f"X{self._ofs('cx', gx)} Y{self._ofs('cy', gy)}")
        return f"X{fmt(gx)} Y{fmt(gy)}"

    @staticmethod
    def _ofs(name, v):
        if abs(v) < 5e-7:
            return f"#<{name}>"
        return f"[#<{name}>{'+' if v > 0 else '-'}{fmt(abs(v))}]"

    def begin(self, name):
        self.lines.append(f"o<{name}> sub")
        if self.rel:
            self.lines.append("#<cx> = #5420")
            self.lines.append("#<cy> = #5421")
        self.cur = None

    def end(self, name):
        self.lines.append(f"o<{name}> endsub")

    def raw(self, s):
        self.lines.append(s)

    def _put(self, line):
        """Doppelte Eilgangzeilen unterdrücken."""
        if not (self.lines and self.lines[-1] == line):
            self.lines.append(line)

    def rapid_z(self, z):
        self._put(f"G0 Z{fmt(self._tz(z))}")

    def feed_z(self, z, f):
        self.lines.append(f"G1 Z{fmt(self._tz(z))} F{f}")

    def rapid_xy(self, x, y):
        self._put(f"G0 {self._xy(x, y)}")
        self.cur = (x, y)

    def feed_xy(self, x, y, f=None, z=None):
        zz = f" Z{fmt(self._tz(z))}" if z is not None else ""
        ff = f" F{f}" if f else ""
        if self.cur is not None and abs(self.cur[0] - x) < 1e-7 and abs(self.cur[1] - y) < 1e-7 and z is None:
            return
        self.lines.append(f"G1 {self._xy(x, y)}{zz}{ff}")
        self.cur = (x, y)

    def arc(self, x, y, cx, cy, ccw, f=None, z=None):
        """Kreisbogen vom aktuellen Punkt nach (x, y) um (cx, cy)."""
        sx, sy = self.cur
        i, j = self._rot(cx - sx, cy - sy)
        i, j = i * self.fx, j * self.fy
        if self.mirrored:  # Spiegeln kehrt den Drehsinn um
            ccw = not ccw
        zz = f" Z{fmt(self._tz(z))}" if z is not None else ""
        ff = f" F{f}" if f else ""
        self.lines.append(f"{'G3' if ccw else 'G2'} {self._xy(x, y)}{zz} I{fmt(i)} J{fmt(j)}{ff}")
        self.cur = (x, y)

    def dwell(self, t):
        if t and t > 0:
            self.lines.append(f"G4 P{fmt(t)}")

    def path(self, segs, f=None, z=None):
        """Segmentliste [('L', x, y) | ('A', x, y, cx, cy, ccw)] abfahren."""
        first = True
        for s in segs:
            if s[0] == "L":
                self.feed_xy(s[1], s[2], f if first else None)
            else:
                self.arc(s[1], s[2], s[3], s[4], s[5], f if first else None)
            first = False


# =========================================================================== Höhen
def heights(p: P):
    surf = p.n(203)
    safe = surf + p.n(200)
    second = surf + p.n(204) if p.n(204, 0) > p.n(200) else safe
    return surf, safe, second


def retract(e: Emit, safe, second):
    e.rapid_z(safe)
    if second > safe:
        e.rapid_z(second)


# =========================================================================== Bohren
def drill_simple(p: P, t: Tool, e: Emit, num: int):
    """201 REIBEN, 206 GEWINDEBOHREN (Ausgleichsfutter), 240 ZENTRIEREN."""
    surf, safe, second = heights(p)
    e.rapid_z(safe)
    if num == 240:
        if p.n(343, 0) == 1:  # Durchmesser
            ta = t.t_angle or 90.0
            if not t.t_angle:
                e.warn.append(_t("T-ANGLE fehlt in der Werkzeugtabelle – 90° angenommen"))
            depth = -(p.n(344) / 2) / math.tan(math.radians(ta / 2))
        else:
            depth = p.n(201)
        e.feed_z(surf + depth, p.f(206))
        e.dwell(p.n(211, 0))
        e.rapid_z(safe)
    elif num == 201:
        e.feed_z(surf + p.n(201), p.f(206))
        e.dwell(p.n(211, 0))
        e.feed_z(safe, p.f(208))
    elif num == 206:
        e.feed_z(surf + p.n(201), p.f(206))
        e.dwell(p.n(211, 0))
        e.raw("M4")
        e.feed_z(safe, p.f(206))
        e.raw("M3")
    retract(e, safe, second)


_FREIFAHR = {1: (-1, 0), 2: (0, -1), 3: (1, 0), 4: (0, 1)}


def drill_bore(p: P, t: Tool, e: Emit, num: int):
    """202 AUSDREHEN: Bohren, Spindel orientieren, freifahren, zurückziehen."""
    surf, safe, second = heights(p)
    e.rapid_z(safe)
    e.feed_z(surf + p.n(201), p.f(206))
    e.dwell(p.n(211, 0))
    e.raw(f"M19 R{fmt(p.n(336, 0))}")
    d = _FREIFAHR.get(int(p.n(214, 0)))
    dist = p.n(357, 0.2) or 0.2
    if d:
        e.feed_xy(d[0] * dist, d[1] * dist, p.f(208))
    e.feed_z(safe, p.f(208))
    if d:
        e.rapid_xy(0, 0)
    e.raw("M3")
    retract(e, safe, second)


def drill_peck(p: P, t: Tool, e: Emit, num: int):
    """203 UNIVERSAL-BOHREN und 205 UNIVERSAL-TIEFBOHREN (Spanbruch, Abnahme, Vorhalteabstand)."""
    surf, safe, second = heights(p)
    bottom = surf + p.n(201)
    if p.n(201) >= 0:
        raise CycleError(_t("Tiefe Q201 muss negativ sein"))
    infeed = p.n(202) or abs(p.n(201))
    dec = p.n(212, 0)
    min_inf = p.n(205, 0)
    if num == 203:
        breaks = int(p.n(213, 0))
        chip_depth = None
    else:
        breaks = 0
        chip_depth = p.n(257, 0)
    back = p.n(256, 0.2) or 0.2
    stop_top = p.n(258, 0.2) if num == 205 else 0.2
    f_in = p.f(206)
    f_ret = p.f(208) if 208 in p and p.get(208) not in (0, "0") else None
    e.rapid_z(safe)
    z = surf
    if num == 205 and p.n(379, 0) > 0:  # vertiefter Startpunkt
        e.feed_z(surf - p.n(379) + p.n(200), p.f(253))
        z = surf - p.n(379)
    count = 0
    while z > bottom + 1e-6:
        step = max(infeed, min_inf) if min_inf else infeed
        target = max(z - step, bottom)
        if chip_depth:  # 205: Spanbruch innerhalb einer Zustellung
            zz = z
            while zz - chip_depth > target + 1e-6:
                zz -= chip_depth
                e.feed_z(zz, f_in)
                e.feed_z(zz + back, f_in)
            e.feed_z(target, f_in)
        else:
            e.feed_z(target, f_in)
        count += 1
        z = target
        infeed = max(infeed - dec, min_inf or 0.0001) if dec else infeed
        if z <= bottom + 1e-6:
            break
        if breaks and count % (breaks + 1) != 0:  # 203: Spanbruch statt Entspanen
            e.feed_z(z + back, f_ret or f_in)
            continue
        if f_ret:
            e.feed_z(safe, f_ret)
        else:
            e.rapid_z(safe)
        e.dwell(p.n(210, 0))
        e.rapid_z(z + stop_top)
    e.dwell(p.n(211, 0))
    if f_ret:
        e.feed_z(safe, f_ret)
    else:
        e.rapid_z(safe)
    retract(e, safe, second)


def drill_mill(p: P, t: Tool, e: Emit, num: int):
    """208 BOHRFRAESEN: schraubenförmig auf Solldurchmesser Q335."""
    surf, safe, second = heights(p)
    r = t.r()
    path_r = p.n(335) / 2 - r
    if path_r <= 0:
        raise CycleError(_t("Q335 Solldurchmesser muss größer als der Werkzeugdurchmesser sein"))
    pitch = p.n(334) or abs(p.n(201))
    ccw = p.n(351, 1) >= 0  # Gleichlauf innen -> CCW
    bottom = surf + p.n(201)
    f = p.f(206)
    e.rapid_z(safe)
    e.rapid_xy(0, 0)
    e.feed_z(surf, f)
    e.feed_xy(path_r, 0, f)
    z = surf
    while z > bottom + 1e-6:
        nz = max(z - pitch, bottom)
        e.arc(path_r, 0, 0, 0, ccw, f, z=nz)
        z = nz
    e.arc(path_r, 0, 0, 0, ccw, f)  # Vollkreis am Grund
    e.feed_xy(0, 0, f)
    e.rapid_z(safe)
    retract(e, safe, second)


def tap_rigid(p: P, t: Tool, e: Emit, num: int):
    """207 GEW.-BOHREN GS / 209 mit Spanbruch: LinuxCNC G33.1 (synchronisiert).

    209: jede Zustellung startet am Sicherheitsabstand (G33.1 kehrt immer zum Startpunkt zurück)."""
    surf, safe, second = heights(p)
    pitch = p.n(239)
    if pitch == 0:
        raise CycleError(_t("Q239 Gewindesteigung = 0"))
    e.rapid_z(safe)
    if pitch < 0:
        e.raw("M4")
    bottom = surf + p.n(201)
    if num == 209 and p.n(257, 0) > 0:
        z = surf
        while z > bottom + 1e-6:
            z = max(z - p.n(257), bottom)
            e.raw(f"G33.1 Z{fmt(e._tz(z))} K{fmt(abs(pitch))}")
    else:
        e.raw(f"G33.1 Z{fmt(e._tz(bottom))} K{fmt(abs(pitch))}")
    if pitch < 0:
        e.raw("M3")
    retract(e, safe, second)


def thread_mill(p: P, t: Tool, e: Emit, num: int):
    """262 GEWINDEFRAESEN (Innengewinde, ohne Nachsetzen): Helix über die Gewindetiefe."""
    surf, safe, second = heights(p)
    r = t.r()
    pitch = p.n(239)
    path_r = p.n(335) / 2 - r
    if path_r <= 0:
        raise CycleError(_t("Q335 Nenndurchmesser zu klein für das Werkzeug"))
    depth = surf + p.n(201)
    climb = p.n(351, 1) >= 0
    right = pitch > 0
    up = (climb and right) or (not climb and not right)  # Gleichlauf+Rechtsgewinde: von unten nach oben
    ccw = climb
    f_pre = p.f(253) if 253 in p else p.f(207)
    f = p.f(207)
    turns = max(1, math.ceil(abs(p.n(201)) / abs(pitch)))
    e.rapid_z(safe)
    e.rapid_xy(0, 0)
    z0 = depth if up else surf
    e.feed_z(z0, f_pre)
    # tangential anfahren (Halbkreis)
    e.arc(path_r, 0, path_r / 2, 0, ccw, f, z=z0 + (abs(pitch) / 8) * (1 if up else -1))
    z = z0 + (abs(pitch) / 8) * (1 if up else -1)
    for _ in range(turns):
        z += abs(pitch) * (1 if up else -1)
        e.arc(path_r, 0, 0, 0, ccw, f, z=z)
    e.arc(0, 0, path_r / 2, 0, ccw, f, z=z + (abs(pitch) / 8) * (1 if up else -1))
    e.rapid_z(safe)
    retract(e, safe, second)


# =========================================================================== Taschen / Zapfen
def rrect_loop(a, b, r, ccw=True, start="E"):
    """Abgerundetes Rechteck (Halbmaße a, b, Eckenradius r) als Segmentliste ab rechter Kante Mitte."""
    r = max(0.0, min(r, a, b))
    if b <= 1e-9:  # Linie (Nut-Mittellinie)
        segs = [("L", -a, 0.0), ("L", a, 0.0)]
        return (a, 0.0), segs
    pts = []
    # gegen den Uhrzeigersinn ab (a, 0)
    pts.append(("L", a, b - r))
    if r > 1e-9:
        pts.append(("A", a - r, b, a - r, b - r, True))
    pts.append(("L", -a + r, b))
    if r > 1e-9:
        pts.append(("A", -a, b - r, -a + r, b - r, True))
    pts.append(("L", -a, -b + r))
    if r > 1e-9:
        pts.append(("A", -a + r, -b, -a + r, -b + r, True))
    pts.append(("L", a - r, -b))
    if r > 1e-9:
        pts.append(("A", a, -b + r, a - r, -b + r, True))
    pts.append(("L", a, 0.0))
    pts = [s for i, s in enumerate(pts)
           if s[0] == "A" or i == 0 or (abs(s[1] - pts[i - 1][1]) > 1e-9 or abs(s[2] - pts[i - 1][2]) > 1e-9)]
    if ccw:
        return (a, 0.0), pts
    # umkehren
    rev = []
    nodes = [(a, 0.0)] + [(s[1], s[2]) for s in pts]
    for i in range(len(pts) - 1, -1, -1):
        s = pts[i]
        tgt = nodes[i]
        if s[0] == "L":
            rev.append(("L", tgt[0], tgt[1]))
        else:
            rev.append(("A", tgt[0], tgt[1], s[3], s[4], False))
    return (a, 0.0), rev


def circle_loop(rho, ccw=True):
    return (rho, 0.0), [("A", rho, 0.0, 0.0, 0.0, ccw)]


def _levels(top, bottom, step):
    if step <= 0 or step >= top - bottom:
        return [bottom]
    out = []
    z = top
    while z - step > bottom + 1e-6:
        z -= step
        out.append(z)
    out.append(bottom)
    return out


def _plunge(e: Emit, p: P, t: Tool, z_from, z_to, room, f_plunge, ccw):
    """Senkrecht oder pendelnd eintauchen (Nut/Zapfen). Taschen nutzen _helix_in."""
    mode = int(p.n(366, 0)) if 366 in p else 0
    if mode == 1 and t.angle > 0 and room > 0.3:
        sx, sy = e.cur
        _helix_in(e, t, sx, sy, min(t.r() * 0.75, room), z_from, z_to, f_plunge, ccw)
        e.feed_xy(sx, sy, f_plunge)
    else:
        if mode in (1, 2) and not t.angle:
            e.warn.append(_t("Eintauchwinkel ANGLE fehlt – Werkzeug taucht senkrecht ein"))
        e.feed_z(z_to, f_plunge)


def _helix_start_angle(t: Tool, rh, z_from, z_to, ccw, end_at):
    """Startwinkel, damit Helix samt ebenem Vollkreis bei end_at endet."""
    pitch = 2 * math.pi * rh * math.tan(math.radians(t.angle))
    total = max(z_from - z_to, 0.0) / pitch * 2 * math.pi + 2 * math.pi
    return end_at - (1 if ccw else -1) * total


def _helix_in(e: Emit, t: Tool, sx, sy, rh, z_from, z_to, f, ccw, start_at=None):
    """Helix um (sx, sy) mit Radius rh von z_from nach z_to, gleichbleibende Steigung (Winkel ANGLE),
    danach ein ebener Vollkreis. Erwartet das Werkzeug über dem Startpunkt (sx+rh, sy) bzw. start_at.
    Gibt (Endpunkt, Tangente) zurück."""
    pitch = 2 * math.pi * rh * math.tan(math.radians(t.angle))
    a = 0.0 if start_at is None else start_at
    sgn = 1 if ccw else -1
    p0 = (sx + rh * math.cos(a), sy + rh * math.sin(a))
    e.feed_xy(*p0, f)
    total = max(z_from - z_to, 0.0) / pitch * 2 * math.pi  # Drehwinkel bis zur Tiefe
    done = 0.0
    while total - done > 1e-6:
        step = min(math.pi, total - done)  # höchstens Halbkreise: eindeutige Bögen
        done += step
        ang = a + sgn * done
        z = z_from - (z_from - z_to) * done / total
        if step * rh < 1e-3:
            # winziger Restbogen: Anfang und Ende wären im G-Code gleich = ungewollter Vollkreis
            e.feed_xy(sx + rh * math.cos(ang), sy + rh * math.sin(ang), f, z=z)
        else:
            e.arc(sx + rh * math.cos(ang), sy + rh * math.sin(ang), sx, sy, ccw, f, z=z)
    ang = a + sgn * done
    for _ in range(2):  # ebener Vollkreis in zwei Hälften
        ang += sgn * math.pi
        e.arc(sx + rh * math.cos(ang), sy + rh * math.sin(ang), sx, sy, ccw, f)
    u = (math.cos(ang), math.sin(ang))
    tan = (-u[1], u[0]) if ccw else (u[1], -u[0])
    return (sx + rh * u[0], sy + rh * u[1]), tan, ang


def _sdf_rrect(x, y, a, b, r):
    """Vorzeichenbehafteter Abstand zum abgerundeten Rechteck (negativ = innen)."""
    r = max(0.0, min(r, a, b))
    qx, qy = abs(x) - (a - r), abs(y) - (b - r)
    return math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - r


def _segs_inside(start, segs, region, tol=1e-4):
    if not segs:
        return True
    return all(region(x, y) <= tol for x, y in pg.sample_segs(start, segs, 0.05))


def _out_normal(tan, ccw):
    """Normale nach außen (bei Gleichlauf in der Tasche = gegen den Uhrzeigersinn: rechts)."""
    return (tan[1], -tan[0]) if ccw else (-tan[1], tan[0])


def pocket(p: P, t: Tool, e: Emit, num: int):
    """251 RECHTECKTASCHE, 252 KREISTASCHE, 253 NUTENFRAESEN.

    Schruppen von innen nach außen: Helix in der Mitte, Ringe mit tangentialen S-Übergängen,
    deren Startpunkte entlang der Kontur weiterwandern; Ringecken gerundet. Schlichten der Wand
    mit tangentialem An- und Abfahrbogen."""
    surf, safe, second = heights(p)
    R = t.r()
    side = p.n(368, 0)
    k = max(p.n(370, 1) or 1, 0.0001) * R
    ccw = p.n(351, 1) >= 0  # Gleichlauf in der Tasche: gegen den Uhrzeigersinn
    phase = int(p.n(215, 0))
    if num == 251:
        A, B, Rc = p.n(218) / 2, p.n(219) / 2, p.n(220, 0)
        e.rot = p.n(224, 0)
        pos = int(p.n(367, 0))
        center = {0: (0, 0), 1: (A, B), 2: (-A, B), 3: (-A, -B), 4: (A, -B)}.get(pos, (0, 0))
    elif num == 253:
        A, B = p.n(218) / 2, p.n(219) / 2
        Rc = B
        e.rot = p.n(374, 0)
        pos = int(p.n(367, 0))
        center = {0: (0, 0), 1: (A, 0), 2: (A - B, 0), 3: (-(A - B), 0), 4: (-A, 0)}.get(pos, (0, 0))
    else:  # 252
        A = B = Rc = p.n(223) / 2
        center = (0, 0)
    cx, cy = center
    circ = num == 252
    d0 = R + side
    if min(A, B) - d0 < -1e-9:
        raise CycleError(_t("Werkzeug zu groß für die Tasche"))
    rmin = 0.064 * R  # kleinster Eckenradius der Innenringe (keine scharfen Richtungswechsel)
    dmax = min(A, B)
    ds = []
    d = d0
    while d < dmax - 1e-6:
        ds.append(d)
        d += k
    ds = list(reversed(ds))  # innen zuerst

    # Ringe als (Loop, Bereichsfunktion) im lokalen System (Taschenmitte = 0,0)
    rings = []
    if circ:
        for d in ds:
            rho = A - d
            rings.append((pg.Loop(*circle_loop(rho, ccw)), lambda x, y, rho=rho: math.hypot(x, y) - rho))
    else:
        if A - dmax > 1e-6:  # längliche Tasche: schmaler Innenring statt Mittellinie (keine Umkehr)
            b_in = rmin  # dünne Schleife um die Mittellinie (Abstand zum nächsten Ring <= k)
            if ds and dmax - b_in > ds[-1] + 1e-6:
                rings.append((pg.Loop(*rrect_loop(A - dmax + b_in, b_in, rmin, ccw)), None))
            else:
                rings.append((pg.Loop(*rrect_loop(A - dmax, 0.0, 0.0, ccw)), None))
        for d in ds:
            a_, b_, r_ = A - d, B - d, max(Rc - d, rmin)
            rings.append((pg.Loop(*rrect_loop(a_, b_, r_, ccw)),
                          lambda x, y, a_=a_, b_=b_, r_=r_: _sdf_rrect(x, y, a_, b_, r_)))
    rings = [rg for rg in rings if rg[0].prims]
    wall = rings[-1][1] if rings else (lambda x, y: 0.0)

    def link(p_end, t_end, loop, region, drift=1.5):
        """S-Übergang auf die nächste Bahn; Startpunkt wandert in Fahrtrichtung weiter."""
        i, u, pt, tan = loop.nearest(p_end)
        if math.dist(pt, p_end) < 1e-6 and tan[0] * t_end[0] + tan[1] * t_end[1] > 0.999:
            return [], loop.rotated(i, u)  # liegt schon tangential auf der Bahn
        n_out = _out_normal(t_end, ccw)
        for dr in (drift, drift / 2, 0.0):
            q = (p_end[0] + k * n_out[0] + dr * k * t_end[0], p_end[1] + k * n_out[1] + dr * k * t_end[1])
            i, u, pt, tan = loop.nearest(q)
            st, segs = loop.rotated(i, u)
            tr = pg.biarc(p_end, t_end, st, tan)
            if tr is not None and pg.max_sweep(p_end, tr) <= math.radians(150) and _segs_inside(p_end, tr, region):
                return tr, (st, segs)
        i, u, pt, tan = loop.nearest(p_end)
        st, segs = loop.rotated(i, u)
        return [("L", st[0], st[1])], (st, segs)

    def ring_path(p_end, t_end):
        """Alle Ringe ab (p_end, t_end) als eine zusammenhängende Segmentliste."""
        return ring_path_from(0, p_end, t_end)

    def at(s):
        if s[0] == "L":
            return ("L", s[1] + cx, s[2] + cy)
        return ("A", s[1] + cx, s[2] + cy, s[3] + cx, s[4] + cy, s[5])

    def emit(segs, f):
        e.path([at(s) for s in pg.merge_lines(e.cur and (e.cur[0] - cx, e.cur[1] - cy), segs)], f)

    lift = max(min(p.n(200), 1.0), 0.2)

    def lead_out(p_end, t_end, region, z, f, ra):
        """Tangential nach innen wegfahren und dabei auf z+lift anheben."""
        n_in = (-_out_normal(t_end, ccw)[0], -_out_normal(t_end, ccw)[1])
        while ra > 0.05:
            c = (p_end[0] + ra * n_in[0], p_end[1] + ra * n_in[1])
            q = (c[0] + ra * t_end[0], c[1] + ra * t_end[1])
            seg = [("A", q[0], q[1], c[0], c[1], ccw)]
            if _segs_inside(p_end, seg, region):
                s = at(seg[0])
                e.arc(s[1], s[2], s[3], s[4], s[5], f, z=z + lift)
                return
            ra /= 2
        e.feed_z(z + lift, f)

    bottom_rough = surf + p.n(201) + p.n(369, 0)
    bottom = surf + p.n(201)
    room = (dmax - d0)
    mode = int(p.n(366, 0)) if 366 in p else 0
    helix = mode == 1 and t.angle > 0 and room > 0.3
    rh = min(0.95 * R, room)
    rh2 = min(0.95 * R, room / 2)  # Kreistasche: Helix neben der Mitte
    if circ:
        helix = helix and rh2 > 0.3

    def spiral():
        """Kreistasche: Spirale aus Halbkreisen (Mitte abwechselnd versetzt), ab der Mitte bis zur
        Wandbahn, dort ein Vollkreis. Durchgehend tangential, ohne Übergänge."""
        rho_max = A - d0
        rhos = [r_ for r_ in (rho_max - i * k for i in range(1, 100000)) if r_ > 0.5 * k][::-1] + [rho_max]
        if rho_max <= 1e-6:
            return [], (0.0, 0.0), (0.0, 1.0 if ccw else -1.0)
        sg = 1.0 if ccw else -1.0
        segs, prev = [], 0.0
        for r_ in rhos:
            segs.append(("A", r_, 0.0, (r_ - prev) / 2, 0.0, ccw))   # unterer/oberer Halbbogen nach +X
            segs.append(("A", -r_, 0.0, 0.0, 0.0, ccw))             # Halbkreis um die Mitte nach -X
            prev = r_
        segs.append(("A", rho_max, 0.0, 0.0, 0.0, ccw))             # Wandbahn schließen
        return segs, (rho_max, 0.0), (0.0, sg)

    def rough_level(z_from, z, f_plunge, f_mill):
        if circ:
            segs, p_end, tan = spiral()
            if helix:
                hc = rh2  # Helixmitte versetzt: Helix endet tangential im Spiralanfang (Taschenmitte)
                a0 = _helix_start_angle(t, rh2, z_from, z, ccw, math.pi)
                e.rapid_xy(cx + hc + rh2 * math.cos(a0), cy + rh2 * math.sin(a0))
                e.feed_z(z_from, f_plunge) if first else e.rapid_z(z_from)
                _helix_in(e, t, cx + hc, cy, rh2, z_from, z, f_plunge, ccw, start_at=a0)
            else:
                if mode in (1, 2) and not t.angle:
                    e.warn.append(_t("Eintauchwinkel ANGLE fehlt – Werkzeug taucht senkrecht ein"))
                e.rapid_xy(cx, cy)
                if not first:
                    e.rapid_z(z_from)
                e.feed_z(z, f_plunge)
            emit(segs, f_mill)
            return p_end, tan
        if helix and num == 253:
            # Nut: Helix am Ende der Mittellinie, endet tangential an deren Anfang
            hx0 = -(A - dmax) - rmin + rh  # Helix endet in der Spitze der Innenschleife
            a0 = _helix_start_angle(t, rh, z_from, z, ccw, math.pi)
            e.rapid_xy(cx + hx0 + rh * math.cos(a0), cy + rh * math.sin(a0))
            e.feed_z(z_from, f_plunge) if first else e.rapid_z(z_from)
            _helix_in(e, t, cx + hx0, cy, rh, z_from, z, f_plunge, ccw, start_at=a0)
            p_end, tan = (hx0 - rh, 0.0), (0.0, -1.0 if ccw else 1.0)
        elif helix:
            e.rapid_xy(cx + rh, cy)
            if first:
                e.feed_z(z_from, f_plunge)
            else:
                e.rapid_z(z_from)
            (hx, hy), tan, _ = _helix_in(e, t, cx, cy, rh, z_from, z, f_plunge, ccw)
            p_end = (hx - cx, hy - cy)
        else:
            if mode in (1, 2) and not t.angle:
                e.warn.append(_t("Eintauchwinkel ANGLE fehlt – Werkzeug taucht senkrecht ein"))
            e.rapid_xy(cx, cy)
            if not first:
                e.rapid_z(z_from)
            e.feed_z(z, f_plunge)
            p_end, tan = (0.0, 0.0), (1.0, 0.0)
            if rings:
                lp = rings[0][0]
                st = lp.start
                e.feed_xy(st[0] + cx, st[1] + cy, f_mill)
                emit(lp.rotated(0, 0.0)[1], f_mill)
                p_end, tan = st, lp.at_start_tangent()
                segs, p_end, tan = ring_path_from(1, p_end, tan)
                emit(segs, f_mill)
                return p_end, tan
        segs, p_end, tan = ring_path(p_end, tan)
        emit(segs, f_mill)
        return p_end, tan

    def ring_path_from(i0, p_end, t_end):
        out = []
        for loop, region in rings[i0:]:
            tr, (st, segs) = link(p_end, t_end, loop, region or wall)
            out += tr + segs
            p_end = st
            t_end = pg.Loop(st, segs).at_start_tangent()
        return out, p_end, t_end

    e.rapid_z(safe)
    if phase in (0, 1):
        z_from = surf + min(lift, p.n(200))  # Helix beginnt knapp über der Oberfläche
        first = True
        for z in _levels(surf, bottom_rough, p.n(202)):
            p_end, tan = rough_level(z_from, z, p.f(206), p.f(207))
            lead_out(p_end, tan, wall, z, p.f(207), min(0.5 * R, k))
            z_from = z + lift
            first = False
    if phase in (0, 2):
        f_fin = p.f(385) if 385 in p else p.f(207)
        if p.n(369, 0) > 0:  # Boden schlichten
            e.rapid_z(min(safe, bottom + lift + p.n(369, 0)))
            e.rapid_xy(cx, cy)
            e.feed_z(bottom, p.f(206))
            p_end, tan = (0.0, 0.0), (1.0, 0.0)
            if circ:
                segs, p_end, tan = spiral()
                emit(segs, f_fin)
            elif rings:
                lp = rings[0][0]
                e.feed_xy(lp.start[0] + cx, lp.start[1] + cy, f_fin)
                emit(lp.rotated(0, 0.0)[1], f_fin)
                segs, p_end, tan = ring_path_from(1, lp.start, lp.at_start_tangent())
                emit(segs, f_fin)
            lead_out(p_end, tan, wall, bottom, f_fin, min(0.5 * R, k))
        # Seite schlichten (Bahn mit Werkzeugradius, ohne Aufmaß), tangential an- und abfahren
        if circ:
            fin = pg.Loop(*circle_loop(A - R, ccw))
            freg = lambda x, y: math.hypot(x, y) - (A - R)  # noqa: E731
        else:
            fa, fb, fr = A - R, B - R, Rc - R
            fin = pg.Loop(*rrect_loop(fa, fb, fr, ccw))
            freg = lambda x, y: _sdf_rrect(x, y, fa, fb, fr)  # noqa: E731
            if fin.prims and fin.prims[0][0] == "A":
                # Nut: Start läge im Endbogen – dort passt kein Anfahrbogen ins geschruppte Feld.
                # Stattdessen Mitte der längsten Geraden.
                lines = [i for i, pr in enumerate(fin.prims) if pr[0] == "L"]
                if lines:
                    fin = pg.Loop(*fin.rotated(max(lines, key=lambda i: fin.prims[i][5]), 0.5))
        st = fin.start
        tn = fin.at_start_tangent()
        n_in = (-_out_normal(tn, ccw)[0], -_out_normal(tn, ccw)[1])
        ra = min(R, max(min(A, B) - R, 0.0))
        lead = None
        while ra > 0.05:
            c = (st[0] + ra * n_in[0], st[1] + ra * n_in[1])
            l0 = (c[0] - ra * tn[0], c[1] - ra * tn[1])
            l1 = (c[0] + ra * tn[0], c[1] + ra * tn[1])
            seg_in = [("A", st[0], st[1], c[0], c[1], ccw)]
            seg_out = [("A", l1[0], l1[1], c[0], c[1], ccw)]
            # Eintauchpunkt im geschruppten Feld: mindestens um das Seitenaufmaß von der Fertigbahn weg
            # (sonst taucht das Werkzeug im Eilgang ins Aufmaß – „Eilgang im Material“)
            if freg(*l0) <= min(1e-4, -side + 1e-4) and _segs_inside(l0, seg_in, freg) \
                    and _segs_inside(st, seg_out, freg):
                lead = (l0, seg_in, seg_out)
                break
            ra /= 2
        e.rapid_z(safe)
        for z in _levels(surf, bottom, p.n(338, 0)):
            if lead:
                l0, seg_in, seg_out = lead
                e.rapid_xy(l0[0] + cx, l0[1] + cy)
            else:
                e.rapid_xy(cx, cy)
            e.rapid_z(min(safe, z + lift) if z < surf else safe)
            e.feed_z(z, p.f(206))
            if lead:
                emit(seg_in, f_fin)
            else:
                e.feed_xy(st[0] + cx, st[1] + cy, f_fin)
            emit(fin.rotated(0, 0.0)[1], f_fin)
            if lead:
                emit(seg_out, f_fin)
            e.feed_z(z + lift, f_fin)
    e.rapid_z(safe)
    retract(e, safe, second)


def stud(p: P, t: Tool, e: Emit, num: int):
    """256 RECHTECKZAPFEN, 257 KREISZAPFEN: von außen nach innen, Gleichlauf = im Uhrzeigersinn."""
    surf, safe, second = heights(p)
    R = t.r()
    side = p.n(368, 0)
    k = max(p.n(370, 1) or 1, 0.0001) * R
    ccw = p.n(351, 1) < 0  # Gleichlauf außen: im Uhrzeigersinn
    if num == 256:
        A, B, Rc = p.n(218) / 2, p.n(219) / 2, p.n(220, 0)
        BA, BB = p.n(424) / 2, p.n(425) / 2
        e.rot = p.n(224, 0)
        pos = int(p.n(367, 0))
        cx, cy = {0: (0, 0), 1: (A, B), 2: (-A, B), 3: (-A, -B), 4: (A, -B)}.get(pos, (0, 0))
        excess = max(BA - A, BB - B, 0)
    else:
        A = B = Rc = p.n(223) / 2
        excess = max(p.n(222) / 2 - A, 0)
        cx = cy = 0
    d0 = R + side
    d_out = excess + R + 2.0
    n = max(1, math.ceil((d_out - d0) / k))
    ds = [d0 + (d_out - d0) * j / n for j in range(n, -1, -1)]
    bottom = surf + p.n(201) + p.n(369, 0)
    e.rapid_z(safe)
    first = True
    for z in _levels(surf, bottom, p.n(202)):
        for d in ds:
            st, segs = (circle_loop(A + d, ccw) if num == 257 else rrect_loop(A + d, B + d, Rc + d if Rc > 0 else d, ccw))
            sx, sy = st[0] + cx, st[1] + cy
            if d == ds[0]:
                if first:
                    e.rapid_xy(sx, sy)
                    first = False
                else:
                    e.feed_xy(sx, sy, p.f(207))
                e.feed_z(z, p.f(206))
            else:
                e.feed_xy(sx, sy, p.f(207))
            e.path([(s[0], s[1] + cx, s[2] + cy, s[3] + cx, s[4] + cy, s[5]) if s[0] == "A" else (s[0], s[1] + cx, s[2] + cy)
                    for s in segs], p.f(207))
        st, _ = (circle_loop(A + ds[0], ccw) if num == 257 else rrect_loop(A + ds[0], B + ds[0], Rc + ds[0], ccw))
        e.feed_xy(st[0] + cx, st[1] + cy, p.f(207))
    e.rapid_z(safe)
    retract(e, safe, second)


def face(p: P, t: Tool, e: Emit, num: int):
    """233/232 PLANFRAESEN: mäanderförmig, Startecke = Aufrufposition (233) bzw. Q225/Q226 (232)."""
    R = t.r()
    if num == 232:
        e.rel = False
        x0, y0 = p.n(225), p.n(226)
    else:
        x0 = y0 = 0.0
    L, Wd = p.n(218), p.n(219)
    top, bottom = p.n(227), p.n(386)
    allow = p.n(369, 0)
    k = max(p.n(370, 1) or 1, 0.0001) * R * (1 if p.n(370, 1) <= 1 else 1)
    over = R + (p.n(357, 2) if 357 in p else 2.0)
    safe = top + p.n(200)
    second = top + p.n(204, 0) if p.n(204, 0) > p.n(200) else safe
    f = p.f(207)
    f_fin = p.f(385) if 385 in p else f
    f_pre = p.f(253) if 253 in p else f
    ny = max(1, math.ceil(Wd / k))
    ys = [y0 + Wd * i / ny for i in range(ny + 1)]
    e.rapid_z(safe)
    e.rapid_xy(x0 - over, ys[0])
    phase = int(p.n(215, 0)) if 215 in p else 0
    levels = _levels(top, bottom + allow, p.n(202)) if phase in (0, 1) else []
    if phase in (0, 2) and allow > 0:
        levels.append(bottom)
    elif phase in (0, 2) and not levels:
        levels = [bottom]
    for li, z in enumerate(levels):
        ff = f_fin if (allow > 0 and z == bottom and li == len(levels) - 1) else f
        e.rapid_xy(x0 - over, ys[0])
        e.feed_z(z, f_pre)
        # Mäander: Bahnwechsel tangential über einen Halbkreis (Radius = halbe Zustellung)
        # statt eckig quer zu fahren – wie die Bahnverbindung im CAM (Fusion).
        left = True
        for i, y in enumerate(ys):
            if i:
                xe = x0 - over if left else x0 + L + over
                dy = y - ys[i - 1]
                dx = 1 if not left else -1  # Fahrrichtung der eben beendeten Bahn
                e.arc(xe, y, xe, ys[i - 1] + dy / 2, dx * dy > 0, ff)
            e.feed_xy(x0 + L + over if left else x0 - over, y, ff)
            left = not left
        e.rapid_z(safe)
    retract(e, safe, second)


GENERATORS = {
    201: drill_simple, 206: drill_simple, 240: drill_simple,
    202: drill_bore,
    203: drill_peck, 205: drill_peck,
    208: drill_mill,
    207: tap_rigid, 209: tap_rigid,
    262: thread_mill,
    251: pocket, 252: pocket, 253: pocket,
    256: stud, 257: stud,
    232: face, 233: face,
}


def generate(num: int, params: P, tool: Tool, name: str, xf: dict | None = None):
    """-> (G-Code-Zeilen des Unterprogramms, Warnungen).

    xf: Spiegeln/Maßfaktor {"fx","fy","fz","ox","oy","oz"} (Zentrum nur für absolute Bahnen).
    """
    gen = GENERATORS[num]
    e = Emit()
    for k, v in (xf or {}).items():
        setattr(e, k, v)
    if num == 232:
        e.rel = False
    e.begin(name)
    gen(params, tool, e, num)
    e.end(name)
    return e.lines, e.warn


# =========================================================================== Polygon-Zyklen
def _clip():
    try:
        import pyclipper
    except ImportError:
        raise CycleError(_t("Python-Paket 'pyclipper' fehlt"))
    return pyclipper


def _levels_milling(e: Emit, p: P, seq, allowed, surf, safe, bottom, f_plunge, f_mill):
    from .slcycles import mill_level

    for z in _levels(surf, bottom, p.n(202)):
        mill_level(e, seq, allowed, z, safe, f_plunge, f_mill, True)
        e.rapid_z(safe)


def round_slot(p: P, t: Tool, e: Emit, num: int):
    """254 RUNDE NUT: Kreisbogen-Nut auf Teilkreis Q375, Startwinkel Q376, Öffnungswinkel Q248."""
    from .slcycles import SCALE, clearing_paths, loops_for

    pc = _clip()
    surf, safe, second = heights(p)
    R = t.r()
    rm, w = p.n(375) / 2, p.n(219)
    if w < 2 * R:
        raise CycleError(_t("Nutbreite Q219 kleiner als Werkzeugdurchmesser"))
    a0, open_ = p.n(376, 0), p.n(248)
    ref = int(p.n(367, 0))
    if ref == 0:
        e.rel = False
        cx, cy = p.n(216), p.n(217)
    else:  # Werkzeugposition = Start-, Mitte- oder End-Kreis der Nut
        ang = math.radians(a0 + {1: 0.0, 2: open_ / 2, 3: open_}.get(ref, 0.0))
        cx, cy = -rm * math.cos(ang), -rm * math.sin(ang)
    count = max(1, int(p.n(377, 1)))
    step = p.n(378, 0) or (360.0 / count if count > 1 else 0.0)
    climb = p.n(351, 1) >= 0
    e.rapid_z(safe)
    for n in range(count):
        s0 = math.radians(a0 + n * step)
        s1 = s0 + math.radians(open_)
        nseg = max(8, int(abs(open_) / 3))
        outer = [(cx + (rm + w / 2) * math.cos(s0 + (s1 - s0) * i / nseg), cy + (rm + w / 2) * math.sin(s0 + (s1 - s0) * i / nseg))
                 for i in range(nseg + 1)]
        inner = [(cx + (rm - w / 2) * math.cos(s1 - (s1 - s0) * i / nseg), cy + (rm - w / 2) * math.sin(s1 - (s1 - s0) * i / nseg))
                 for i in range(nseg + 1)]
        poly = outer + inner
        # Nutenden rund: Fläche um w/2 nach innen und wieder nach außen versetzen
        po = pc.PyclipperOffset()
        po.AddPath([(int(x * SCALE), int(y * SCALE)) for x, y in poly], pc.JT_MITER, pc.ET_CLOSEDPOLYGON)
        reg = po.Execute(-(w / 2 - 0.01) * SCALE)
        po = pc.PyclipperOffset()
        po.AddPaths(reg, pc.JT_ROUND, pc.ET_CLOSEDPOLYGON)
        reg = po.Execute((w / 2 - 0.01) * SCALE)
        phase = int(p.n(215, 0))
        if phase in (0, 1):
            seq, allowed = clearing_paths(reg, R, p.n(368, 0), R, climb)
            _levels_milling(e, p, seq, allowed, surf, safe, surf + p.n(201) + p.n(369, 0), p.f(206), p.f(207))
        if phase in (0, 2):
            lv = loops_for(reg, R, 1.0, ccw_pocket=climb)
            if lv:
                _levels_milling(e, p, lv[0][1], lv[0][2], surf, safe, surf + p.n(201), p.f(206),
                                p.f(385) if 385 in p else p.f(207))
    retract(e, safe, second)


def polygon_stud(p: P, t: Tool, e: Emit, num: int):
    """258 VIELECKZAPFEN: n-Eck um die Aufrufposition, Rohteil-Durchmesser Q222."""
    from .slcycles import SCALE, _flt

    pc = _clip()
    surf, safe, second = heights(p)
    R = t.r()
    n = max(3, int(p.n(572, 6)))
    rot = math.radians(p.n(224, 0))
    d = p.n(571) / 2
    rc = d / math.cos(math.pi / n) if int(p.n(573, 0)) == 0 else d  # Inkreis -> Umkreisradius
    poly = [(rc * math.cos(rot + 2 * math.pi * i / n), rc * math.sin(rot + 2 * math.pi * i / n)) for i in range(n)]
    path = [(int(x * SCALE), int(y * SCALE)) for x, y in poly]
    r_round = p.n(220, 0)
    if r_round > 0:  # Ecken runden: nach innen und wieder nach außen versetzen
        po = pc.PyclipperOffset()
        po.AddPath(path, pc.JT_MITER, pc.ET_CLOSEDPOLYGON)
        tmp = po.Execute(-r_round * SCALE)
        po = pc.PyclipperOffset()
        po.AddPaths(tmp, pc.JT_ROUND, pc.ET_CLOSEDPOLYGON)
        paths = po.Execute(r_round * SCALE)
    else:
        if r_round < 0:
            e.warn.append(_t("Fase an den Ecken (Q220 < 0) wird noch als scharfe Ecke gefräst"))
        paths = [path]
    k = max(p.n(370, 1) or 1, 0.0001) * R
    d0 = R + p.n(368, 0)
    d_out = max(p.n(222) / 2 - rc, 0) + R + 2.0
    steps = max(1, math.ceil((d_out - d0) / k))
    ds = [d0 + (d_out - d0) * j / steps for j in range(steps, -1, -1)]
    climb_cw = p.n(351, 1) >= 0  # außen Gleichlauf = im Uhrzeigersinn
    bottom = surf + p.n(201) + p.n(369, 0)
    e.rapid_z(safe)
    first = True
    for z in _levels(surf, bottom, p.n(202)):
        for i, dd in enumerate(ds):
            po = pc.PyclipperOffset(2.0, 0.005 * SCALE)
            po.AddPaths(paths, pc.JT_ROUND, pc.ET_CLOSEDPOLYGON)
            loops = po.Execute(dd * SCALE)
            for lp in loops:
                pts = _flt(lp)
                if climb_cw:
                    pts = list(reversed(pts))
                pts.append(pts[0])
                if i == 0:
                    if first:
                        e.rapid_xy(*pts[0])
                        first = False
                    else:
                        e.feed_xy(*pts[0], p.f(207))
                    e.feed_z(z, p.f(206))
                else:
                    e.feed_xy(*pts[0], p.f(207))
                for q in pts[1:]:
                    e.feed_xy(*q)
    e.rapid_z(safe)
    retract(e, safe, second)


GENERATORS[254] = round_slot
GENERATORS[258] = polygon_stud


# =========================================================================== Rückwärtssenken / Tiefbohren
def back_bore(p: P, t: Tool, e: Emit, num: int):
    """204 RUECKWAERTS-SENKEN: orientiert (M19) und exzentrisch durch die Bohrung, Senkung von unten."""
    surf, safe, second = heights(p)
    thick = p.n(250)
    ecc = p.n(251)
    edge = p.n(252)
    if thick <= 0 or ecc <= 0:
        raise CycleError(_t("Q250 Materialstärke und Q251 Exzentermaß müssen positiv sein"))
    d = int(p.n(214, 0))
    if d not in (1, 2, 3, 4):
        raise CycleError(_t("Q214 Freifahr-Richtung 1..4 angeben (0 ist bei Zyklus 204 nicht erlaubt)"))
    ox, oy = {1: (-ecc, 0.0), 2: (0.0, -ecc), 3: (ecc, 0.0), 4: (0.0, ecc)}[d]
    below = surf - thick - p.n(200) - edge  # Schneide im Sicherheitsabstand unter der Unterkante
    sink = surf - thick + p.n(249) - edge  # Schneide auf Senkungsgrund
    if sink <= below:
        raise CycleError(_t("Q249 Tiefe Senkung: Senkung liegt unter dem Eintauchpunkt"))
    orient = f"M19 R{fmt(p.n(336, 0))}"
    e.rapid_z(safe)
    e.raw(orient)
    e.rapid_xy(ox, oy)
    e.feed_z(below, p.f(253))
    e.rapid_xy(0, 0)
    e.raw("M3")
    e.feed_z(sink, p.f(254))
    e.dwell(p.n(255, 0))
    e.feed_z(below, p.f(254))
    e.raw(orient)
    e.rapid_xy(ox, oy)
    e.rapid_z(safe)
    e.rapid_xy(0, 0)
    e.raw("M3")
    retract(e, safe, second)


def deep_drill_241(p: P, t: Tool, e: Emit, num: int):
    """241 EINLIPPEN-TIEFBOHREN: Ein-/Ausfahren mit eigener Drehzahl/Drehrichtung, Verweiltiefe."""
    surf, safe, second = heights(p)
    if p.n(201) >= 0:
        raise CycleError(_t("Tiefe Q201 muss negativ sein"))
    bottom = surf + p.n(201)
    start = surf - p.n(379, 0)
    if start <= bottom:
        raise CycleError(_t("Q379 Startpunkt liegt unter der Bohrtiefe"))
    rot = {3: "M3", 4: "M4", 5: "M5"}.get(int(p.n(426, 5)))
    if rot is None:
        raise CycleError(_t("Q426 Spindeldrehrichtung 3, 4 oder 5"))
    s_in = p.n(427, 0)
    s_drill = p.n(428, 0)
    f_in = p.f(206)
    f_pre = p.f(253)
    f_ret = p.f(208)

    def spindle(m, s):
        e.raw(f"{m} S{fmt(s)}" if m != "M5" and s > 0 else m)

    e.rapid_z(safe)
    if start < surf - 1e-9:  # vertiefter Startpunkt (Pilotbohrung): mit Ein-/Ausfahrdrehzahl hinein
        spindle(rot, s_in)
        e.feed_z(start + p.n(200), f_pre)
        e.feed_z(start, f_pre)
    spindle("M3", s_drill)
    cool_on = int(p.n(429, 0))
    if cool_on:
        e.raw(f"M{cool_on}")
    dwell_z = surf - p.n(435, 0) if p.n(435, 0) > 0 else None
    infeed = p.n(202, 0) or abs(bottom - start)
    dec = p.n(212, 0)
    min_inf = p.n(205, 0)
    z = start
    reduced = False
    fact = p.n(401, 100) / 100.0
    while z > bottom + 1e-6:
        target = max(z - max(infeed, min_inf), bottom)
        if dwell_z is not None and not reduced and target <= dwell_z < z:
            e.feed_z(dwell_z, f_in)
            e.dwell(p.n(211, 0))
            reduced = True
            z = dwell_z
            continue
        f = f_in
        if reduced and fact < 1.0:
            f = fmt(float(f_in) * fact) if not str(f_in).startswith("#") else f"[{f_in}*{fmt(fact)}]"
        e.feed_z(target, f)
        z = target
        infeed = max(infeed - dec, min_inf or 0.0001) if dec else infeed
    if dwell_z is None:
        e.dwell(p.n(211, 0))
    cool_off = int(p.n(430, 0))
    if cool_off:
        e.raw(f"M{cool_off}")
    spindle(rot, s_in)
    back = start + p.n(200) if start < surf - 1e-9 else safe
    e.feed_z(back, f_ret) if f_ret not in ("0",) else e.rapid_z(back)
    e.rapid_z(safe)
    if second > safe:
        e.rapid_z(second)


# =========================================================================== Gewindefräsen 263..267
def _thread_dir(p: P, inner=True):
    """-> (ccw, up): Fräsrichtung und Steigrichtung aus Fräsart Q351 und Steigung Q239."""
    climb = p.n(351, 1) >= 0
    right = p.n(239) > 0
    ccw = climb if inner else not climb
    up = ccw if right else not ccw  # Schraubensinn der Bahn = Gewindesinn
    return ccw, up


def _circle_from_center(e: Emit, rho, ccw, f, z=None):
    """Aus der Mitte über einen Halbkreis auf rho, Vollkreis, Halbkreis zurück in die Mitte."""
    if rho <= 1e-6:
        return
    e.arc(rho, 0, rho / 2, 0, ccw, f, z=z)
    e.arc(rho, 0, 0, 0, ccw)
    e.arc(0, 0, rho / 2, 0, ccw)


def _front_sink(e: Emit, p: P, surf, f_pre, f_sink, ccw, rho):
    if p.n(358, 0) == 0:
        return
    e.feed_z(surf + p.n(358), f_pre)
    _circle_from_center(e, rho, ccw, f_sink)


def _thread_helix(e: Emit, pr, bottom, top, pitch, ccw, up, f, f_app, turns=None, start=None):
    """Tangential anfahren, ganze Gänge Schraubenlinie, tangential weg. start: Anfahrpunkt auf X (sonst Mitte).

    Abwärts beginnt die Schraube so hoch, dass sie genau auf ``bottom`` endet (Überlauf nach oben).
    """
    pitch = abs(pitch)
    sgn = 1 if up else -1
    if turns is None:
        turns = max(1, math.ceil((top - bottom) / pitch - 1e-9))
    turns = int(turns)
    z0 = bottom if up else bottom + turns * pitch
    sx = start if start is not None else 0.0
    e.feed_z(z0 - sgn * pitch / 8, f_app)
    e.arc(pr, 0, (sx + pr) / 2, 0, ccw, f_app, z=z0)
    z = z0
    for _ in range(turns):
        z += sgn * pitch
        e.arc(pr, 0, 0, 0, ccw, f, z=z)
    e.arc(sx, 0, (sx + pr) / 2, 0, ccw, f, z=z + sgn * pitch / 8)
    return z


def thread_mill_26x(p: P, t: Tool, e: Emit, num: int):
    """263 SENKGEWINDEFRAESEN, 264 BOHRGEWINDEFRAESEN, 265 HELIX-BOHRGEWINDEFR."""
    surf, safe, second = heights(p)
    r = t.r()
    pitch = p.n(239)
    if pitch == 0:
        raise CycleError(_t("Q239 Gewindesteigung darf nicht 0 sein"))
    pr = p.n(335) / 2 - r
    if pr <= 0:
        raise CycleError(_t("Q335 Solldurchmesser zu klein für das Werkzeug"))
    if p.n(201) >= 0:
        raise CycleError(_t("Q201 Gewindetiefe muss negativ sein"))
    bottom = surf + p.n(201)
    f_pre = p.f(253)
    f_mill = p.f(207)
    f_app = p.f(512) if p.get(512) not in (None, 0, 0.0, "0") else f_mill
    f_sink = p.f(254) if 254 in p else f_mill
    rho_front = p.n(359, 0)
    e.rapid_z(safe)
    e.rapid_xy(0, 0)
    if num == 265:
        right = pitch > 0
        ccw = not right  # nach unten: Rechtsgewinde im Uhrzeigersinn
        sink_after = int(p.n(360, 0)) == 1
        if not sink_after:
            _front_sink(e, p, surf, f_sink, f_sink, ccw, rho_front)
        e.feed_z(surf, f_pre)
        _thread_helix(e, pr, bottom, surf, pitch, ccw, False, f_mill, f_app)
        e.rapid_z(safe)
        if sink_after:
            _front_sink(e, p, surf, f_pre, f_sink, ccw, rho_front)
            e.rapid_z(safe)
        retract(e, safe, second)
        return
    ccw, up = _thread_dir(p)
    if num == 263:
        sink = surf + p.n(356)
        if p.n(356) >= 0:
            raise CycleError(_t("Q356 Senktiefe muss negativ sein"))
        if p.n(357, 0) > 0:
            e.feed_z(sink, f_pre)
        else:
            e.feed_z(sink + p.n(200), f_pre)
            e.feed_z(sink, f_sink)
        _circle_from_center(e, pr, ccw, f_sink)
        e.feed_z(safe, f_pre)
        _front_sink(e, p, surf, f_pre, f_sink, ccw, rho_front)
    else:  # 264: Bohren mit Zustellung, Spanbruch und Vorhalteabstand
        drill_bottom = surf + p.n(356)
        if p.n(356) >= 0:
            raise CycleError(_t("Q356 Bohrtiefe muss negativ sein"))
        infeed = p.n(202) or abs(p.n(356))
        chip = p.n(257, 0)
        back = p.n(256, 0.2) or 0.2
        stop = p.n(258, 0.2)
        f_in = p.f(206)
        z = surf
        while z > drill_bottom + 1e-6:
            target = max(z - infeed, drill_bottom)
            if chip > 0:
                zz = z
                while zz - chip > target + 1e-6:
                    zz -= chip
                    e.feed_z(zz, f_in)
                    e.feed_z(zz + back, f_in)
            e.feed_z(target, f_in)
            z = target
            if z <= drill_bottom + 1e-6:
                break
            if chip <= 0:
                e.rapid_z(safe)
                e.rapid_z(z + stop)
        e.rapid_z(safe)
        _front_sink(e, p, surf, f_pre, f_sink, ccw, rho_front)
    # Gewinde: eine 360°-Schraubenlinie über die Länge des Gewindefräsers
    e.feed_z((bottom if up else bottom + abs(pitch)) + abs(pitch) / 8 * (-1 if up else 1), f_pre)
    _thread_helix(e, pr, bottom, bottom + abs(pitch), pitch, ccw, up, f_mill, f_app, turns=1)
    e.rapid_z(safe)
    retract(e, safe, second)


def thread_mill_outer(p: P, t: Tool, e: Emit, num: int):
    """267 AUSSENGEWINDE FR.: Zapfen von außen, Nachsetzen Q355 (0/1 durchgehend, n Gänge je Schraube)."""
    surf, safe, second = heights(p)
    r = t.r()
    pitch = p.n(239)
    if pitch == 0:
        raise CycleError(_t("Q239 Gewindesteigung darf nicht 0 sein"))
    if p.n(201) >= 0:
        raise CycleError(_t("Q201 Gewindetiefe muss negativ sein"))
    pr = p.n(335) / 2 + r
    sx = pr + abs(pitch) + r * 0.5  # Startpunkt auf der Hauptachse außerhalb des Zapfens
    bottom = surf + p.n(201)
    f_pre = p.f(253)
    f_mill = p.f(207)
    f_app = p.f(512) if p.get(512) not in (None, 0, 0.0, "0") else f_mill
    f_sink = p.f(254) if 254 in p else f_mill
    ccw, up = _thread_dir(p, inner=False)
    e.rapid_z(safe)
    e.rapid_xy(sx, 0)
    if p.n(358, 0) != 0:  # stirnseitig senken: auf Kreis um den Versatz nach innen
        rho = pr - p.n(359, 0)
        e.feed_z(surf + p.n(358), f_pre)
        e.arc(rho, 0, (sx + rho) / 2, 0, ccw, f_sink)
        e.arc(rho, 0, 0, 0, ccw)
        e.arc(sx, 0, (sx + rho) / 2, 0, ccw)
    length = abs(p.n(201))
    n = int(p.n(355, 0))
    if n <= 1:
        _thread_helix(e, pr, bottom, surf, pitch, ccw, up, f_mill, f_app, start=sx)
    else:  # mehrere versetzte Schraubenlinien zu je n Gängen
        seg = n * abs(pitch)
        k = max(1, math.ceil(length / seg - 1e-9))
        for i in range(k):
            lo = bottom + i * seg if up else max(surf - (i + 1) * seg, bottom)
            hi = min(lo + seg, surf) if up else surf - i * seg
            _thread_helix(e, pr, lo, hi, pitch, ccw, up, f_mill, f_app, turns=n, start=sx)
    e.rapid_z(safe)
    e.rapid_xy(0, 0)
    retract(e, safe, second)


GENERATORS[204] = back_bore
GENERATORS[241] = deep_drill_241
GENERATORS[263] = thread_mill_26x
GENERATORS[264] = thread_mill_26x
GENERATORS[265] = thread_mill_26x
GENERATORS[267] = thread_mill_outer


def _engrave(p: P, t: Tool, e: Emit, num: int):
    from .engrave import engrave_225

    engrave_225(p, str(p.get(500, "")), t, e)


GENERATORS[225] = _engrave
