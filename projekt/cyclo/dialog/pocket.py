"""Konturtaschen-Zyklen: 271/272/273/274/277 und Figuren 1271–1278, 1281/1282.

Umsetzung auf der Geometrie der SL-Zyklen (pyclipper):
  * Bearbeitungsfläche = Taschen − Inseln (Zyklus 14 / CONTOUR DEF + 271) bzw. aus einer
    Standardfigur (Tasche, Insel innerhalb einer Begrenzung 1281/1282, Planfläche).
  * 272 Schruppen: konturparallele Bahnen mit seitlicher Zustellung k = Q370 · R (so
    definiert), geschlossene Tasche von innen nach außen mit Helix-Eintauchen (Winkel ANGLE aus
    der Werkzeugtabelle), offene Begrenzung (Q569=1, Figurtyp 2) von außen nach innen mit
    Eintauchen außerhalb des Materials. Vorschub beim Eintauchen Q207·Q568, Drehzahl Q576/Q579.
  * 273 Schlichten Tiefe: Boden mit Q370·R, Seitenaufmaß bleibt.
  * 274 Schlichten Seite: Wände auf Endmaß (Restaufmaß Q14), Zustellung Q338.
  * 277 Anfasen: Werkzeugmitte um (Kegelradius an der Oberfläche − Fasenbreite) neben der Kante.

272 geschlossene Tasche: adaptives Räumen mit gleichbleibender Eingriffsbreite k (adaptive.py):
Helix, Spirale, Restmaterial wandparallel von innen nach außen, angehobene Verbindungen.
Nicht nachgebildet: Restmaterial (Q438), Zustellstrategie Q575.
"""

from __future__ import annotations

from ..i18n import _t

import dataclasses
import math

from .cyclegen import CycleError, Emit, P, Tool, fmt
from .slcycles import (_flt, _int, _levels, _need_clipper, _rotate_to_nearest, _segment_inside, inside,
                       loops_for, offset, pyclipper)

FIGURES = (1271, 1272, 1273, 1278)
BOUNDARIES = (1281, 1282)


# --------------------------------------------------------------------------- Figuren
def _rot(pts, ang, cx, cy):
    if not ang:
        return pts
    a = math.radians(ang)
    c, s = math.cos(a), math.sin(a)
    return [(cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c) for x, y in pts]


def _circle(cx, cy, r, n=None):
    n = n or max(24, int(2 * math.pi * r / 0.5))
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def _corners(poly, kind, size):
    """Ecken eines Polygons (gegen den Uhrzeigersinn) runden (kind 0) oder anfasen (kind 1)."""
    if size <= 0:
        return poly
    out = []
    n = len(poly)
    for i in range(n):
        p0, p1, p2 = poly[i - 1], poly[i], poly[(i + 1) % n]
        a = (p0[0] - p1[0], p0[1] - p1[1])
        b = (p2[0] - p1[0], p2[1] - p1[1])
        la, lb = math.hypot(*a), math.hypot(*b)
        ua, ub = (a[0] / la, a[1] / la), (b[0] / lb, b[1] / lb)
        ang = math.acos(max(-1.0, min(1.0, ua[0] * ub[0] + ua[1] * ub[1])))
        if kind == 1:
            d = size
            out += [(p1[0] + ua[0] * d, p1[1] + ua[1] * d), (p1[0] + ub[0] * d, p1[1] + ub[1] * d)]
            continue
        d = size / math.tan(ang / 2)
        if d > min(la, lb) / 2 + 1e-9:
            raise CycleError(_t('Eckenradius {0:g} zu groß für die Figur').format(size))
        t1 = (p1[0] + ua[0] * d, p1[1] + ua[1] * d)
        bis = (ua[0] + ub[0], ua[1] + ub[1])
        lbis = math.hypot(*bis)
        h = size / math.sin(ang / 2)
        c = (p1[0] + bis[0] / lbis * h, p1[1] + bis[1] / lbis * h)
        a0 = math.atan2(t1[1] - c[1], t1[0] - c[0])
        t2 = (p1[0] + ub[0] * d, p1[1] + ub[1] * d)
        a1 = math.atan2(t2[1] - c[1], t2[0] - c[0])
        da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        m = max(2, int(abs(da) * size / 0.3))
        out += [(c[0] + size * math.cos(a0 + da * j / m), c[1] + size * math.sin(a0 + da * j / m)) for j in range(m + 1)]
    return out


def figure_polygon(num: int, v: P, px: float, py: float):
    """-> (Polygon gegen den Uhrzeigersinn, Figurmitte) für die Werkzeugposition (px, py)."""
    if num == 1271:
        a, b = v.n(218), v.n(219)
        if a <= 0 or b <= 0:
            raise CycleError(_t("Seitenlängen Q218/Q219 müssen positiv sein"))
        off = {0: (0, 0), 1: (a / 2, b / 2), 2: (-a / 2, b / 2), 3: (-a / 2, -b / 2), 4: (a / 2, -b / 2)}
        dx, dy = off.get(int(v.n(367, 0)), (0, 0))
        cx, cy = px + dx, py + dy
        poly = [(cx - a / 2, cy - b / 2), (cx + a / 2, cy - b / 2), (cx + a / 2, cy + b / 2), (cx - a / 2, cy + b / 2)]
        kind = int(v.n(660, 0))
        if kind >= 2:
            kind, size = 0, 0.0  # Eckenfreifräsung: hier scharfe Ecken
        else:
            size = v.n(220, 0)
        poly = _corners(poly, kind, size)
    elif num == 1272:
        r = v.n(223) / 2
        if r <= 0:
            raise CycleError(_t("Kreisdurchmesser Q223 muss positiv sein"))
        off = {0: (0, 0), 1: (0, -r), 2: (-r, 0), 3: (0, r), 4: (r, 0)}
        dx, dy = off.get(int(v.n(367, 0)), (0, 0))
        cx, cy = px + dx, py + dy
        return _circle(cx, cy, r), (cx, cy)
    elif num == 1273:
        L, W = v.n(218), v.n(219)
        if W <= 0 or L < W:
            raise CycleError(_t("Nutbreite Q219 muss positiv und höchstens so groß wie die Nutlänge Q218 sein"))
        off = {0: 0, 1: L / 2, 2: L / 2 - W / 2, 3: -(L / 2 - W / 2), 4: -L / 2}
        cx, cy = px + off.get(int(v.n(367, 0)), 0), py
        r, h = W / 2, L / 2 - W / 2
        n = max(12, int(math.pi * r / 0.4))
        poly = [(cx + h + r * math.cos(-math.pi / 2 + math.pi * i / n), cy + r * math.sin(-math.pi / 2 + math.pi * i / n))
                for i in range(n + 1)]
        poly += [(cx - h + r * math.cos(math.pi / 2 + math.pi * i / n), cy + r * math.sin(math.pi / 2 + math.pi * i / n))
                 for i in range(n + 1)]
    else:  # 1278 Vieleck
        n = int(v.n(572))
        if n < 3:
            raise CycleError(_t("Anzahl der Ecken Q572 mindestens 3"))
        d = v.n(571)
        ru = d / 2 if v.n(573, 0) else d / 2 / math.cos(math.pi / n)  # Umkreisradius
        cx, cy = px, py
        poly = [(cx + ru * math.cos(2 * math.pi * i / n), cy + ru * math.sin(2 * math.pi * i / n)) for i in range(n)]
        kind = int(v.n(660, 0))
        poly = _corners(poly, kind, v.n(220, 0))
    poly = _rot(poly, v.n(224, 0), px, py)
    return poly, (cx, cy)


def boundary_polygon(num: int, v: P, fcx: float, fcy: float):
    if v.n(654, 0):
        fcx, fcy = 0.0, 0.0  # Mitte am Nullpunkt
    cx, cy = fcx + v.n(655, 0), fcy + v.n(656, 0)
    if num == 1281:
        a, b = v.n(651), v.n(652)
        return [(cx - a / 2, cy - b / 2), (cx + a / 2, cy - b / 2), (cx + a / 2, cy + b / 2), (cx - a / 2, cy + b / 2)]
    return _circle(cx, cy, v.n(653) / 2)


def _ccw(poly):
    a = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
            for i in range(len(poly)))
    return poly if a > 0 else list(reversed(poly))


class _Region(list):
    """Clipper-Fläche (Liste von Pfaden), die ihre Inselkonturen mitführt. Bei offener Begrenzung sind
    die Inseln aus der fertigen Fläche nicht mehr abzulesen, sobald eine Insel die Begrenzung berührt
    oder kreuzt (dann ist sie kein Loch mehr, sondern eine Einbuchtung der Außenkontur)."""
    islands = None


def region_from_polys(pockets, islands, boundary=None):
    """Clipper-Fläche: (Begrenzung ∪ Taschen) − Inseln. Das Ergebnis führt die Inselkonturen als
    .islands mit (siehe _Region); ocm_cycle wertet sie bei offener Begrenzung aus."""
    _need_clipper()
    subj = [_int(_ccw(p)) for p in pockets]
    if boundary is not None:
        subj.append(_int(_ccw(boundary)))
    pc = pyclipper.Pyclipper()
    pc.AddPaths(subj, pyclipper.PT_SUBJECT, True)
    if islands:
        pc.AddPaths([_int(_ccw(p)) for p in islands], pyclipper.PT_CLIP, True)
    reg = _Region(pc.Execute(pyclipper.CT_DIFFERENCE, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO))
    reg.islands = [_int(_ccw(p)) for p in islands]
    return reg


# --------------------------------------------------------------------------- Bahnen
def _num_feed(f, factor):
    try:
        return fmt(float(f) * factor)
    except (TypeError, ValueError):
        return f"[{f}*{fmt(factor)}]"


def _helix_down(e: Emit, x, y, z_from, z_to, rh, angle_deg, f, ccw):
    """Helix-Eintauchen um den Punkt (x - rh, y), endet in (x, y) auf z_to mit einem Vollkreis."""
    pitch = 2 * math.pi * rh * math.tan(math.radians(angle_deg))
    cx, cy = x - rh, y
    z = z_from
    while z > z_to + 1e-6:
        z = max(z - pitch, z_to)
        e.arc(x, y, cx, cy, ccw, f, z=z)
    e.arc(x, y, cx, cy, ccw, f)  # Vollkreis am Grund: Platz für die Späne


def _outward_point(reg_float, pt, dist):
    """Punkt außerhalb der Fläche in Richtung vom Schwerpunkt weg."""
    xs = [p[0] for path in reg_float for p in path]
    ys = [p[1] for path in reg_float for p in path]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    dx, dy = pt[0] - mx, pt[1] - my
    ln = math.hypot(dx, dy) or 1.0
    return pt[0] + dx / ln * dist, pt[1] + dy / ln * dist


def _open_parts(reg, islands=None):
    """Offene Begrenzung -> (Rohteilkontur, Inseln). Die Rohteilkontur ist die Außenkontur der Fläche
    EINSCHLIESSLICH der Inseln: eine Insel ist Material, auch wenn sie die Begrenzung berührt oder über
    sie hinausragt – außerhalb der Rohteilkontur ist Luft, in einer Insel nie.
    islands: Inselkonturen (Clipper-Pfade); ohne Angabe die von region_from_polys mitgeführten. Fehlen
    beide (Fläche aus anderer Quelle), bleiben nur die Löcher der Fläche als Inseln – eine Insel an der
    Begrenzung ist dann nicht erkennbar."""
    from . import adaptive as ad
    if islands is None:
        islands = getattr(reg, "islands", None)
    outer, holes = [], []
    for comp in ad.components(reg):
        outer.append(comp[0])
        holes += [list(reversed(h)) for h in comp[1:]]
    isl = ad._clean([list(q) for q in islands]) if islands else []
    if isl:
        # zum Rohteil gehören die Inseln, die es berühren oder überlappen (0,01 mm Fangbereich); eine Insel
        # ganz abseits bleibt geschützt, erweitert das Rohteil aber nicht
        near = [q for comp in ad.components(isl) if ad.intersect(ad.grow(comp, 0.01), outer) for q in comp]
        if near:
            outer = [comp[0] for comp in ad.components(ad.union(outer, near))]
        holes = holes + isl
    return outer, holes


def _work_area(reg, R, allow, k, open_bnd, stock, over=None, islands=None):
    """-> (zulässige Werkzeugmitte, Fläche mit Material oder None = überall).
    Geschlossene Tasche: Fläche um R + Aufmaß verkleinert; mit Rohteil (stock) gilt alles außerhalb
    des Rohteils als Luft (offene Seite). Offene Begrenzung: die Begrenzung samt Inseln ist das Rohteil,
    die Werkzeugmitte darf um R + Aufmaß + 2k hinaus, Inseln bleiben um R + Aufmaß frei (_open_parts)."""
    from . import adaptive as ad
    if open_bnd:
        outer, holes = _open_parts(reg, islands)
        keep_out = offset(holes, -(R + allow)) if holes else []
        over = R + allow + 2 * k if over is None else over
        return ad.difference(offset(outer, -over), keep_out), outer
    solid = None
    if stock is not None:
        x0, y0, x1, y1 = stock
        solid = [_int([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])]
    return offset(reg, R + allow), solid


def _plan(tool, *args, **kw):
    """adaptive.plan_regions mit verständlichen Fehlermeldungen."""
    from . import adaptive as ad
    try:
        plans = ad.plan_regions(*args, **kw)
    except ad.PlanError as ex:
        if ex.args[0] == "size":
            raise CycleError(_t("Bearbeitungsfläche zu groß für die Bahnberechnung ({0} × {1} mm) – "
                                "Kontur aufteilen").format(fmt(round(ex.args[1])), fmt(round(ex.args[2]))))
        if ex.args[0] == "memory":
            raise CycleError(_t("Bahnberechnung bräuchte etwa {0} MB Arbeitsspeicher (Grenze {1} MB) – Kontur "
                                "aufteilen oder Fläche verkleinern").format(fmt(round(ex.args[1])),
                                                                         fmt(round(ex.args[2]))))
        if ex.args[0] == "entry":
            raise CycleError(_t("Bahnplaner findet keinen sicheren Anfahrweg nach X{0} Y{1} (kein Nachweis, "
                                "dass es keinen gibt) – Zyklus nicht berechnet"
                                ).format(fmt(ex.args[1]), fmt(ex.args[2])))
        if ex.args[0] == "noentry":
            raise CycleError(_t("Bahnplaner findet bei X{0} Y{1} weder Helix noch Rampe zum Eintauchen (kein "
                                "Nachweis, dass keine möglich ist) – Zyklus nicht berechnet"
                                ).format(fmt(ex.args[1]), fmt(ex.args[2])))
        raise CycleError(_t("Bahn verlässt die zulässige Fläche – Zyklus nicht berechnet"))
    if not plans:
        raise CycleError(_t("Werkzeug zu groß für die Kontur"))
    return plans


def _plunge_tool(tool):
    """-> (Werkzeug mit brauchbarem Eintauchwinkel, ANGLE war unbrauchbar). Helix und Rampe gibt es nur
    für 0 < ANGLE < 90°. Jeder andere Eintrag (negativ, 90° und mehr) wird wie ein fehlender behandelt:
    senkrecht mit dem Eintauchvorschub und mit Warnung – sonst rechnet die Helix mit einer unendlichen
    oder negativen Steigung."""
    a = tool.angle or 0.0
    if a and not 0.0 < a < 90.0:
        return dataclasses.replace(tool, angle=0.0), True
    return tool, False


def _bad_angle_text():
    return _t("Eintauchwinkel ANGLE = {0}° in der Werkzeugtabelle liegt nicht zwischen 0 und 90° – Werkzeug "
              "taucht senkrecht ein")


def _entry_warnings(e, tool, plans, R=None, bad_angle=None):
    """bad_angle: ANGLE-Eintrag der Werkzeugtabelle, der außerhalb 0…90° lag (siehe _plunge_tool)."""
    closed = [pl for pl in plans if not pl["open"]]
    if bad_angle is not None and closed:
        e.warn.append(_bad_angle_text().format(fmt(bad_angle)))
    elif not tool.angle and closed:
        e.warn.append(_t("Eintauchwinkel ANGLE fehlt in der Werkzeugtabelle – Werkzeug taucht senkrecht ein"))
    elif any(pl.get("vertical") for pl in closed):
        e.warn.append(_t("Kein Platz für Helix oder Rampe (Werkzeug füllt die Tasche aus) – Werkzeug taucht "
                         "senkrecht ein"))
    if any(pl.get("ramp") for pl in closed):
        if tool.angle:
            e.warn.append(_t("Nut kaum breiter als das Werkzeug – Eintauchen über Pendelrampe im Vollschnitt"))
        else:
            e.warn.append(_t("Nut kaum breiter als das Werkzeug – nach dem senkrechten Einstich Vollschnitt "
                             "entlang der Nut"))
    # Helix mit sehr kleinem Radius: für ein Werkzeug ohne Zentrumsschnitt praktisch ein senkrechter Einstich
    if R and tool.angle:
        small = [pl["rh"] for pl in closed if not pl.get("ramp") and not pl.get("vertical") and 0 < pl["rh"] < 0.3 * R]
        if small:
            e.warn.append(_t("Helixradius nur {0} mm (Tasche kaum größer als das Werkzeug) – Eintauchen fast "
                             "senkrecht, Werkzeug mit Zentrumsschnitt nötig").format(fmt(round(min(small), 3))))
    if plans and plans[0].get("skipped"):
        _skipped_passage_warning(e)


def _skipped_passage_warning(e):
    e.warn.append(_t("Durchgang kaum breiter als das Werkzeug (unter 0,02 mm Luft) wird nicht bearbeitet – "
                     "dort bleibt Material stehen"))


def _stock_warnings(e, reg, solid, plans):
    """Rohteil laut BLK FORM bestimmt die Bahn: Fehler, wenn die Tasche ganz daneben liegt (sonst käme ein
    leeres Unterprogramm), Warnung, wenn eine Seite der Tasche laut BLK FORM offen ist."""
    from . import adaptive as ad
    part = ad.intersect(reg, solid)
    if not part or not ad.offset(part, 0.05):
        raise CycleError(_t("Tasche liegt ganz außerhalb des Rohteils (BLK FORM) – nichts zu bearbeiten"))
    if any(pl["open"] for pl in plans):
        e.warn.append(_t("Tasche seitlich offen laut BLK FORM – Werkzeug startet neben dem Rohteil und stellt "
                         "dort mit Q253 zu; die BLK FORM muss dem wirklichen Rohteil entsprechen"))


class _Feed:
    """Gibt das F-Wort nur aus, wenn es sich ändert."""

    def __init__(self, base):
        self.base, self.last = base, None

    def word(self, factor=1.0, f=None):
        w = f if f is not None else (self.base if factor >= 0.999 else _num_feed(self.base, factor))
        if w == self.last:
            return None
        self.last = w
        return w

    def reset(self):
        self.last = None


def _out(e: Emit, q, f=None, z0=None, z1=None):
    """Ein Bahnelement ausgeben – der einzige Weg, auf dem 272/273 Geraden und Bögen schreiben.
    Bögen werden in Teile von höchstens 162° zerlegt (immer eindeutig, nie mehr als ein Halbkreis).
    Ein Bogen, dessen Anfang und Ende im G-Code gleich wären (nach Runden und Transformation), würde
    als Vollkreis gefahren: er wird als Gerade ausgegeben. z0/z1: Höhe am Anfang/Ende (linear)."""
    parts = [q]
    if q.kind == "A" and abs(q.sweep) > math.pi * 0.9:
        n = int(math.ceil(abs(q.sweep) / (math.pi * 0.9)))
        parts, rest = [], q
        for i in range(n - 1):
            a, rest = rest.split(1.0 / (n - i))
            parts.append(a)
        parts.append(rest)
    s = 0.0
    for i, part in enumerate(parts):
        s += part.length
        zz = None
        if z1 is not None:
            zz = z1 if z0 is None else z0 + (z1 - z0) * (s / q.length if q.length > 1e-12 else 1.0)
        ff = f if i == 0 else None
        x, y = part.p1
        if (part.kind == "L" or math.dist(part.p0, part.p1) < 1e-3
                or (e.cur is not None and e._xy(*e.cur) == e._xy(x, y))):
            e.feed_xy(x, y, ff, z=zz)
        else:
            e.arc(x, y, part.c[0], part.c[1], part.sweep > 0, ff, z=zz)


def _emit_prims(e: Emit, prims, fw: _Feed, z=None, z_from=None):
    """Bahnelemente ausgeben (siehe _out). z_from/z: Höhe läuft über die Elemente von z_from nach z
    (Rampe), sonst bleibt sie."""
    total = sum(q.length for q in prims) if z_from is not None else 0.0
    s = 0.0
    for q in prims:
        f = fw.word(q.ff)
        if z_from is None:
            _out(e, q, f)
        else:
            za = z_from + (z - z_from) * (s / total if total > 1e-9 else 1.0)
            s += q.length
            _out(e, q, f, za, z_from + (z - z_from) * (s / total if total > 1e-9 else 1.0))


def _split_prims(prims, length):
    """Elementfolge nach der Weglänge length teilen -> (Anfang, Rest)."""
    if length < 0.05:
        return [], list(prims)
    head, s = [], 0.0
    for i, q in enumerate(prims):
        if s + q.length <= length + 1e-9:
            head.append(q)
            s += q.length
            continue
        f = (length - s) / q.length
        if f > 1e-3:
            a, b = q.split(f)
            return head + [a], [b] + list(prims[i + 1:])
        return head, list(prims[i:])
    return head, []


def adaptive_272(e: Emit, reg, tool: Tool, p: P, data: P, open_bnd=False, stock=None, islands=None):
    """Adaptives Räumen mit begrenzter Umschlingung (Rechenweise siehe adaptive.py)."""
    from . import adaptive as ad
    R = tool.r()
    angle_in = tool.angle
    tool, bad_angle = _plunge_tool(tool)
    allow = data.n(368, 0)
    surf, depth = data.n(203), data.n(201)
    if depth >= 0:
        raise CycleError(_t("Tiefe Q201 muss negativ sein"))
    bottom = surf + depth + data.n(369, 0)
    safe = surf + p.n(200, 2)
    clear = max(data.n(260, safe), safe)
    k = min(max(p.n(370, 0.4), 0.04), 1.9) * R
    climb = p.n(351, 1) >= 0
    ra = max(p.n(577, 0.2), 0.05) * R                 # Q577: Radius der An-/Abfahr- und Verbindungsbögen
    rho_min = max(data.n(578, 0.2), 0.05) * R         # Q578: kleinster Bahnradius der Räumbahnen in Innenecken
    allowed, solid = _work_area(reg, R, allow, k, open_bnd, stock, islands=islands)
    if not allowed:
        raise CycleError(_t("Werkzeug zu groß für die Kontur"))
    if stock is not None and not open_bnd:
        _stock_warnings(e, reg, solid, [])
    plans = _plan(tool, allowed, solid, R, k, climb, 0.95 * R if tool.angle else 0.0, rho_min, ra)
    if stock is not None and not open_bnd:
        _stock_warnings(e, reg, solid, plans)
    f_mill = p.f(207)
    f_plunge = _num_feed(f_mill, p.n(568, 0.5))
    f_pre = p.f(253) if p.n(253, 0) < 99999 else None
    s = p.n(576, 0)
    s_plunge = s * p.n(579, 1.0) if s else 0
    if s:
        e.raw(f"S{fmt(s)}")
    _entry_warnings(e, tool, plans, R, angle_in if bad_angle else None)
    if any(pl["stats"]["slow_len"] > 0.5 for pl in plans):
        e.warn.append(_t("Engstelle: Umschlingung über dem Sollwert – Vorschub dort abgesenkt"))
    lift = 0.2
    fw = _Feed(f_mill)
    levels = _levels_equal(surf, bottom, p.n(202))
    # Q575 Zustellfolge: 0 = Ebene für Ebene über alle Teilflächen, 1/2 = Teilfläche für Teilfläche
    if int(p.n(575, 0)) == 0:
        seq = [(zi, pl) for zi in range(len(levels)) for pl in plans]
    else:
        seq = [(zi, pl) for pl in plans for zi in range(len(levels))]
    e.rapid_z(clear)
    for zi, pl in seq:
        z = levels[zi]
        top = (levels[zi - 1] + 0.5) if zi else min(safe, surf + 1.0)
        _emit_plan(e, pl, z, top, safe, tool, climb, fw, f_mill, f_plunge, f_pre, lift, s, s_plunge,
                   blank=solid if stock is not None and not open_bnd else None)
    e.rapid_z(clear)


def _ramp_in(e, tool, a, b, top, z, safe, f, f_pre=None):
    """Geprüfte Pendelstrecke: gleichmäßige Zustellung <= ANGLE, danach die Strecke auf Tiefe.
    Beide Richtungen und ein möglicher Anschluss müssen vom Aufrufer geometrisch geprüft sein.
    Endpunkt ist b. Gemeinsame Ausgabe für 272 und beide Schlichtstrategien von 273."""
    L = math.dist(a, b)
    e.rapid_xy(*a)
    e.rapid_z(safe)
    e.feed_z(top, f_pre or f)
    if not tool.angle:
        # Werkzeug ohne ANGLE: senkrecht bei a, dann die Sehne einmal auf Tiefe (Vollschnitt)
        e.feed_z(z, f)
        e.feed_xy(b[0], b[1], None)
    else:
        n = max(2, int(math.ceil((top - z) / (L * math.tan(math.radians(tool.angle))) - 1e-9)))
        n += n % 2
        for i in range(1, n + 1):
            q = b if i % 2 else a
            e.feed_xy(q[0], q[1], f if i == 1 else None, z=top + (z - top) * i / n)
        e.feed_xy(b[0], b[1], None)


def _emit_plan(e: Emit, pl, z, top, safe, tool, climb, fw, f_mill, f_plunge, f_pre, lift, s=0, s_plunge=0,
               rapid_down=True, blank=None):
    """Einen 2D-Plan (adaptive.plan_regions) auf der Tiefe z ausgeben. top: Höhe, bis zu der über der
    Einstichstelle sicher kein Material steht (ab dort Helix bzw. Vorschub). rapid_down: nach einem
    Rückzug im Eilgang bis 1 mm über z (nur an im Plan nachweislich freien Stellen), sonst wird ab
    Sicherheitshöhe im Vorschub zugestellt. blank: Rohteilfläche laut BLK FORM – neben ihr (Luft nur
    laut Rohteildefinition, nicht selbst geräumt) wird nie im Eilgang, sondern mit Q253 zugestellt."""
    from .cyclegen import _helix_in, _helix_start_angle
    c, rh = pl["center"], pl["rh"]
    fw.reset()
    if not pl["open"]:
        if s_plunge and s_plunge != s:
            e.raw(f"S{fmt(s_plunge)}")
        if pl.get("ramp"):
            a, b = pl["ramp"]
            _ramp_in(e, tool, a, b, top, z, safe, f_plunge, f_pre)
        elif rh > 0:
            a0 = _helix_start_angle(tool, rh, top, z, climb, 0.0)
            e.rapid_xy(c[0] + rh * math.cos(a0), c[1] + rh * math.sin(a0))
            e.rapid_z(safe)
            e.feed_z(top, f_pre or f_plunge)
            _helix_in(e, tool, c[0], c[1], rh, top, z, f_plunge, climb, start_at=a0)
        else:
            e.rapid_xy(*c)
            e.rapid_z(safe)
            e.feed_z(top, f_pre or f_plunge)
            e.feed_z(z, f_plunge)
        if s_plunge and s_plunge != s:
            e.raw(f"S{fmt(s)}")
        _emit_prims(e, pl["spiral"], fw)
    else:
        e.rapid_z(safe)
    down = not pl["open"]
    for op in pl["ops"]:
        if op.kind == "jump":
            e.rapid_z(safe)
            e.rapid_xy(*op.p)
            if not rapid_down:
                e.feed_z(min(safe, top), f_pre or f_plunge)
            elif blank is not None and not inside(blank, op.p):
                e.feed_z(z + 1.0, f_pre or f_plunge)
            elif op.slow:  # Stelle nicht nachweislich frei: ab Oberkante der Ebene im Vorschub
                e.rapid_z(min(safe, top))
            else:
                e.rapid_z(min(safe, z + 1.0))
            e.feed_z(z + lift, f_plunge)
            fw.reset()
            down = False
        elif op.kind == "out":
            _emit_link(e, op.prims, z, lift, fw.word() or f_mill, fall=False)
            fw.last = f_mill
        elif op.kind == "link":
            if not down:  # Anfahrweg nach dem Eintauchen: dabei auf Tiefe
                _emit_link(e, op.prims, z, lift, fw.word() or f_mill, rise=False)
                down = True
            else:
                _emit_link(e, op.prims, z, lift, fw.word() or f_mill)
            fw.last = f_mill
        else:
            prims = op.prims
            if not down:  # nach dem Eintauchen: auf dem Luftstück (Vorlauf) schräg auf Tiefe
                head, prims = _split_prims(prims, min(op.air, 2.0))
                if head:
                    _emit_prims(e, head, fw, z=z, z_from=z + lift)
                else:
                    e.feed_z(z, f_plunge)
                down = True
            _emit_prims(e, prims, fw)
    e.rapid_z(safe)


def _levels_equal(top, bottom, step):
    """Zustellebenen in gleichen Schritten (höchstens step), die letzte auf bottom."""
    step = abs(step)
    span = top - bottom
    if step <= 0 or step >= span - 1e-9:
        return [bottom]
    n = int(math.ceil(span / step - 1e-9))
    return [top - span * i / n for i in range(1, n)] + [bottom]


def _emit_link(e: Emit, prims, z, lift, f, rise=True, fall=True):
    """Verbindung abfahren: auf dem ersten Stück um lift anheben, auf dem letzten wieder absenken.
    Kurze gerade Anschlüsse bleiben auf Tiefe."""
    total = sum(q.length for q in prims)
    if total < 1e-9:
        return
    if rise and fall and total < 3.0 and all(q.kind == "L" for q in prims):
        for i, q in enumerate(prims):
            e.feed_xy(q.p1[0], q.p1[1], f if i == 0 else None)
        return
    lr = min(math.pi / 2 * max((q.length / abs(q.sweep) for q in prims if q.kind == "A"), default=1.0),
             total / 2 if rise and fall else total)
    cuts = []
    if rise:
        cuts.append(lr)
    if fall:
        cuts.append(total - lr)
    pieces, s = [], 0.0
    for q in prims:  # an den Knickpunkten des Höhenverlaufs teilen
        for cpos in sorted(cuts):
            if s + 1e-9 < cpos < s + q.length - 1e-9:
                a, b = q.split((cpos - s) / q.length)
                pieces.append(a)
                s += a.length
                q = b
        pieces.append(q)
        s += q.length

    def zat(pos):
        up = min(1.0, pos / lr) if rise else 1.0
        dn = min(1.0, (total - pos) / lr) if fall else 1.0
        return z + lift * min(up, dn)
    s = 0.0
    for i, q in enumerate(pieces):
        za = zat(s)
        s += q.length
        _out(e, q, f if i == 0 else None, za, zat(s))


def rough_272(e: Emit, reg, tool: Tool, p: P, data: P, open_bnd: bool, stock=None, islands=None):
    return adaptive_272(e, reg, tool, p, data, open_bnd, stock, islands)


def floor_273(e: Emit, reg, tool: Tool, p: P, data: P, open_bnd=False, stock=None, islands=None):
    """Boden schlichten. Q595 = 0 (gleiche Bahnabstände): konturparallele Ringe im Abstand k = Q370·R
    (_floor_rings). Q595 = 1 (gleicher Eingriff): derselbe Bahnplaner wie 272 mit dem Ziel eines
    gleichmäßigen Eingriffs; beim Einstieg und in Engstellen kann der Sollwert überschritten werden.
    Über dem Boden wird nur das Bodenaufmaß erwartet (vorher geräumt): eingetaucht wird wie bisher ab
    Sicherheitshöhe im Vorschub Q253, nie im Eilgang."""
    from . import adaptive as ad
    angle_in = tool.angle
    tool, bad_angle = _plunge_tool(tool)
    if int(p.n(595, 1)) == 0:
        if bad_angle:
            e.warn.append(_bad_angle_text().format(fmt(angle_in)))
        elif not tool.angle:
            e.warn.append(_t("Eintauchwinkel ANGLE fehlt in der Werkzeugtabelle – Werkzeug taucht senkrecht ein"))
        return _floor_rings(e, reg, tool, p, data, open_bnd, islands)
    R = tool.r()
    allow = data.n(368, 0)
    surf, depth = data.n(203), data.n(201)
    bottom = surf + depth
    safe = surf + p.n(200, 2)
    clear = max(data.n(260, safe), safe)
    k = min(max(p.n(370, 1.0), 0.04), 1.9) * R
    climb = p.n(351, 1) >= 0
    ra = max(p.n(577, 0.2), 0.05) * R
    rho_min = max(data.n(578, 0.2), 0.05) * R
    # offene Begrenzung: die Werkzeugmitte darf bis R + 1,2 über die Kante hinaus (dort steht das Werkzeug
    # ganz neben dem Rohteil), Inseln halten R + Aufmaß
    allowed, solid = _work_area(reg, R, allow, k, open_bnd, stock, over=R + 1.2, islands=islands)
    if not allowed:
        raise CycleError(_t("Werkzeug zu groß für die Kontur"))
    if stock is not None and not open_bnd:
        _stock_warnings(e, reg, solid, [])
    plans = _plan(tool, allowed, solid, R, k, climb, 0.95 * R if tool.angle else 0.0, rho_min, ra)
    if stock is not None and not open_bnd:
        _stock_warnings(e, reg, solid, plans)
    _entry_warnings(e, tool, plans, R, angle_in if bad_angle else None)
    f = p.f(385)
    f_plunge = _num_feed(f, p.n(568, 0.3))
    f_pre = p.f(253) if p.n(253, 0) < 99999 else None
    top = min(safe, bottom + data.n(369, 0) + 0.2)
    fw = _Feed(f)
    e.rapid_z(clear)
    for pl in plans:
        _emit_plan(e, pl, bottom, top, safe, tool, climb, fw, f, f_plunge, f_pre, 0.2, rapid_down=False)
    e.rapid_z(clear)


def _floor_rings(e: Emit, reg, tool: Tool, p: P, data: P, open_bnd=False, islands=None):
    """273 mit gleichen Bahnabständen: konturparallele Ringe von innen nach außen, als Geraden und Bögen.
    Einfahren über eine Helix oder geprüfte Pendelrampe. Ohne ANGLE bzw. bei nachweislich fehlendem
    Platz senkrecht mit Warnung; erfolglose Einstiegssuche führt zum Abbruch. Ringwechsel über Bögen
    (Radius Q577·R) tangential
    aus dem alten in den neuen Ring; geht das nicht innerhalb der Fläche, Rückzug und neu einfahren."""
    from . import adaptive as ad
    from .cyclegen import _helix_in, _helix_start_angle
    R = tool.r()
    allow = data.n(368, 0)
    surf, depth = data.n(203), data.n(201)
    bottom = surf + depth
    safe = surf + p.n(200, 2)
    clear = max(data.n(260, safe), safe)
    # Ringabstand höchstens R: darüber bliebe in der Mitte zwischen den innersten Bahnen Boden stehen
    k = min(max(p.n(370, 1.0), 0.04), 1.0) * R
    ra = max(p.n(577, 0.2), 0.05) * R
    if open_bnd:
        # offene Begrenzung: außerhalb der Begrenzung ist Luft – die Werkzeugmitte darf bis R − 0,2 über die
        # Kante hinaus, nur die Inseln halten R + Aufmaß (sonst bleibt am Rand und in schmalen Stegen zwischen
        # Kante und Insel Boden stehen)
        outer, holes = _open_parts(reg, islands)   # Inseln auch an oder über der Begrenzung geschützt
        centers = offset(outer, -(R - 0.2))
        floor = outer
        if holes:
            keep = offset(holes, -(R + allow))
            centers = ad.difference(centers, keep)
            floor = ad.difference(outer, offset(holes, -allow))
        ref = centers
        levels = loops_for(ad.offset(centers, ad.WALL_MARGIN), 0.0, k, ccw_pocket=True)
        # Ringe der äußersten Ebene weglassen, die nur Luft schneiden (Boden schon von den anderen überdeckt)
        if len(levels) > 1:
            inner = [q for _, polys, _ in levels[1:] for q in polys]
            done = ad.buffer_open(inner, R)
            kept = []
            for q in levels[0][1]:
                others = [o for o in levels[0][1] if o is not q]
                cov = ad.union(done, ad.buffer_open(others, R)) if others else done
                need = ad.difference(ad.intersect(floor, ad.buffer_open([q], R)), cov)
                if need and ad.offset(need, 0.02):
                    kept.append(q)
            levels[0] = (levels[0][0], kept, levels[0][2])
    else:
        ref = offset(reg, R + allow)
        levels = loops_for(ad.offset(ref, ad.WALL_MARGIN), 0.0, k, ccw_pocket=True)
    if not levels:
        raise CycleError(_t("Werkzeug zu groß für die Kontur"))
    if ad.skipped_passage(ref, R):
        _skipped_passage_warning(e)
    allowed = levels[0][2]
    entry_comps = ad.components(allowed)
    lim = ad.Region(ref)   # jedes ausgegebene Element wird gegen die zulässige Fläche geprüft (prims_within)
    rings = [poly for _, polys, _ in reversed(levels) for poly in polys]
    f = p.f(385)
    f_plunge = _num_feed(f, p.n(568, 0.3))
    f_pre = p.f(253) if p.n(253, 0) < 99999 else None
    top = min(safe, bottom + data.n(369, 0) + 0.2)
    fw = _Feed(f)

    def free(prims):
        return ad.prims_within(prims, lim)

    def start_on(ring, aim):
        """Ring so drehen, dass er an der Ecke beginnt, die dem Zielpunkt am nächsten liegt."""
        pts = _rotate_to_nearest(ring, aim)
        prims = ad.fit_arcs(pts)
        if not free(prims):   # ein Bogen verließe die zulässige Fläche: dort Sehnen behalten
            prims = ad.fit_arcs(pts, ok=lambda a: free([a]))
        if not free(prims):
            prims = [ad.Prim("L", a, b) for a, b in zip(pts, pts[1:])]
        return [q for q in prims if q.length > 1e-9]

    def enter(prims):
        """Neu einfahren: Helix auf der Innenseite, die tangential im Ringanfang endet."""
        s0, h = prims[0].p0, prims[0].heading(False)
        e.rapid_z(safe)
        if tool.angle:
            for rh in (0.95 * R, 0.8 * R, 0.6 * R, 0.45 * R, 0.35 * R, 0.25 * R, 0.15 * R):
                c = (s0[0] - h[1] * rh, s0[1] + h[0] * rh)   # links der Fahrtrichtung = in der Fläche
                # der Helixkreis wird wie jedes andere Element gegen die zulässige Fläche geprüft
                # (zwei Halbkreise, prims_within) – nicht nur an Stichpunkten
                m = (2 * c[0] - s0[0], 2 * c[1] - s0[1])
                if free([ad.Prim("A", s0, m, c, math.pi), ad.Prim("A", m, s0, c, math.pi)]):
                    end_at = math.atan2(s0[1] - c[1], s0[0] - c[0])
                    a0 = _helix_start_angle(tool, rh, top, bottom, True, end_at)
                    e.rapid_xy(c[0] + rh * math.cos(a0), c[1] + rh * math.sin(a0))
                    e.feed_z(top, f_pre or f_plunge)
                    _helix_in(e, tool, c[0], c[1], rh, top, bottom, f_plunge, True, start_at=a0)
                    return
            # Wiederverwendung der Sehnensuche und der Pendelausgabe des adaptiven Zweigs.
            # Der Anschluss an den Ring ist Teil des Nachweises, nicht nur die Rampe selbst.
            comp = next((c for c in entry_comps if inside(c, s0)), None)
            candidates = []
            if comp:
                chord = ad._longest_chord(comp, s0, more=True)
                if chord:
                    candidates.extend([chord, tuple(reversed(chord))])
            # Lokale Alternative, wenn eine lange Sehne hinter einer Insel liegt: die erste Ringsehne.
            candidates.append((prims[0].p1, s0))
            for a, b in candidates:
                if math.dist(a, b) < 0.3:
                    continue
                path = [ad.Prim("L", a, b), ad.Prim("L", b, a), ad.Prim("L", b, s0)]
                if not free(path):
                    continue
                _ramp_in(e, tool, a, b, top, bottom, safe, f_plunge, f_pre)
                if math.dist(b, s0) > 1e-9:
                    e.feed_xy(*s0, f_plunge)
                fw.reset()
                return
            # Wie im adaptiven Zweig: nur eine in jeder Richtung <0,3 mm große Werkzeugmittenfläche
            # gilt als nachweislich zu klein. Eine erfolglose Suche in größeren Flächen ist kein Beweis.
            if comp:
                xs = [x for path in comp for x, y in path]
                ys = [y for path in comp for x, y in path]
                no_room = math.hypot(max(xs) - min(xs), max(ys) - min(ys)) / ad.SCALE < 0.3
            else:
                no_room = False
            if not no_room:
                raise CycleError(_t("Bahnplaner findet bei X{0} Y{1} weder Helix noch Rampe zum Eintauchen (kein "
                                    "Nachweis, dass keine möglich ist) – Zyklus nicht berechnet"
                                    ).format(fmt(s0[0]), fmt(s0[1])))
            warning = _t("Kein Platz für Helix oder Rampe (Werkzeug füllt die Tasche aus) – Werkzeug taucht "
                         "senkrecht ein")
            if warning not in e.warn:
                e.warn.append(warning)
        if not free([ad.Prim("L", s0, s0)]):
            raise CycleError(_t("Bahn verlässt die zulässige Fläche – Zyklus nicht berechnet"))
        e.rapid_xy(*s0)
        e.feed_z(top, f_pre or f_plunge)
        e.feed_z(bottom, f_plunge)

    e.rapid_z(clear)
    cur = head = None
    todo = list(rings)
    while todo:
        if cur is None:
            ring = todo.pop(0)
            prims = start_on(ring, None)
            if not prims:
                continue
            enter(prims)
        else:
            # nächster Ring: der früheste (innerste) erreichbare – Reihenfolge innen -> außen bleibt je
            # Teilfläche erhalten, Wechsel der Teilfläche erst, wenn kein Ring mehr erreichbar ist
            aim = (cur[0] + head[0] * (k + 2 * ra), cur[1] + head[1] * (k + 2 * ra))
            pick = None
            for i, ring in enumerate(todo[:6]):
                prims = start_on(ring, aim)
                if not prims:
                    continue
                s0, h = prims[0].p0, prims[0].heading(False)
                if math.dist(cur, s0) > 3 * k + 6 * ra + 2 * R:
                    continue
                cands = [c for c in ad.dubins(cur, head, s0, h, ra)[:3]
                         if sum(q.length for q in c) <= 2.5 * math.dist(cur, s0) + 4 * ra]
                for link in cands + [[ad.Prim("L", cur, s0)]]:
                    link = [q for q in link if q.length > 1e-9]
                    if link and free(link):
                        pick = (i, prims, link)
                        break
                if pick:
                    break
            if pick:
                i, prims, link = pick
                todo.pop(i)
                _emit_prims(e, link, fw)
            else:
                i = min(range(len(todo)), key=lambda j: min(math.dist(cur, q) for q in todo[j]))
                prims = start_on(todo.pop(i), cur)
                if not prims:
                    continue
                fw.reset()
                enter(prims)
        _emit_prims(e, prims, fw)
        cur, head = prims[-1].p1, prims[-1].heading(True)
    e.rapid_z(safe)
    e.rapid_z(clear)


def _wall_passes(e: Emit, reg, dist, approach, levels_z, safe, clear, f_in, f_mill, climb, f_pre=None):
    """Konturparallele Wandbahnen im Abstand dist, Anfahren aus der Fläche heraus."""
    lv = loops_for(reg, dist, 1.0, ccw_pocket=climb)
    if not lv:
        raise CycleError(_t("Werkzeug zu groß für die Kontur"))
    inner = offset(reg, dist + approach)
    inner_pts = [p for path in inner for p in _flt(path)]
    e.rapid_z(clear)
    for poly in lv[0][1]:
        start = poly[0]
        if inner_pts:
            ap = min(inner_pts, key=lambda q: (q[0] - start[0]) ** 2 + (q[1] - start[1]) ** 2)
        else:
            ap = start
        for z in levels_z:
            e.rapid_xy(*ap)
            e.rapid_z(safe)
            e.feed_z(z, f_pre or f_in)
            e.feed_xy(*start, f_mill)
            for pt in poly[1:]:
                e.feed_xy(*pt)
            e.feed_xy(*ap)
            e.rapid_z(safe)
    e.rapid_z(clear)


def side_274(e: Emit, reg, tool: Tool, p: P, data: P):
    R = tool.r()
    surf, depth = data.n(203), data.n(201)
    bottom = surf + depth
    safe = surf + p.n(200, 2)
    clear = max(data.n(260, safe), safe)
    zs = _levels(surf, bottom, p.n(338, 0))
    ra = max(R * 0.2, 0.5)
    f = p.f(385)
    _wall_passes(e, reg, R + p.n(14, 0), ra, zs, safe, clear, f, f, p.n(351, 1) >= 0,
                 p.f(253) if p.n(253, 0) < 99999 else None)


def chamfer_277(e: Emit, reg, tool: Tool, p: P, data: P):
    surf = data.n(203)
    tip = p.n(353)
    if tip >= 0:
        raise CycleError(_t("Q353 Tiefe Werkzeugspitze muss negativ sein"))
    half = p.n(354, 0) or (tool.t_angle / 2 if tool.t_angle else 0)
    if not half:
        raise CycleError(_t("Fasenwinkel: Q354 angeben oder T-ANGLE in der Werkzeugtabelle eintragen"))
    rs = abs(tip) * math.tan(math.radians(half))  # Kegelradius an der Oberfläche
    d = rs - p.n(359)
    if d <= 0.01:
        raise CycleError(_t("Werkzeugspitze zu flach für die Fasenbreite (Q353 tiefer oder Q359 kleiner)"))
    safe = surf + p.n(200, 2)
    clear = max(data.n(260, safe), safe)
    f = p.f(207)
    _wall_passes(e, reg, d, max(d * 0.5, 0.5), [surf + tip], safe, clear, f, f, p.n(351, 1) >= 0,
                 p.f(253) if p.n(253, 0) < 99999 else None)


def _check_input(num, p: P, data: P):
    """Eingaben von 272/273, die sonst still zu einer falschen oder gefährlichen Bahn führen."""
    depth = data.n(201)
    if depth >= 0:
        raise CycleError(_t("Tiefe Q201 muss negativ sein"))
    if p.n(200, 2) < 0:
        raise CycleError(_t("Sicherheitsabstand Q200 darf nicht negativ sein"))
    if data.n(368, 0) < 0:
        raise CycleError(_t("Aufmaß Seite Q368 darf nicht negativ sein"))
    q369 = data.n(369, 0)
    if q369 < 0 or q369 >= abs(depth):
        raise CycleError(_t("Aufmaß Tiefe Q369 muss zwischen 0 und der Tiefe Q201 liegen"))
    if p.n(568, 0.5) <= 0:
        raise CycleError(_t("Faktor Eintauchen Q568 muss größer als 0 sein"))


def ocm_cycle(num: int, p: P, data: P, reg, tool: Tool, e: Emit, open_bnd: bool, stock=None, islands=None):
    """stock: Rohteil-Rechteck (xmin, ymin, xmax, ymax) im Werkstücksystem oder None. Damit erkennen
    272/273, welche Teile einer Tasche außerhalb des Rohteils liegen (offene Seite).
    islands: Inselkonturen (Clipper-Pfade) für die offene Begrenzung; ohne Angabe gelten die Inseln,
    die region_from_polys an reg mitgibt (siehe _open_parts)."""
    e.rel = False
    if num in (272, 273):
        _check_input(num, p, data)
    if num == 272:
        rough_272(e, reg, tool, p, data, open_bnd, stock, islands)
    elif num == 273:
        floor_273(e, reg, tool, p, data, open_bnd, stock, islands)
    elif num == 274:
        side_274(e, reg, tool, p, data)
    elif num == 277:
        chamfer_277(e, reg, tool, p, data)
    else:
        raise CycleError(_t('Konturtaschen-Zyklus {0} nicht vorgesehen').format(num))
    if p.n(438, -1) > 0:
        e.warn.append(_t("Q438 Ausräumwerkzeug (Restmaterial) wird noch nicht ausgewertet"))
