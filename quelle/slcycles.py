"""SL-Zyklen: 21 VORBOHREN, 22 AUSRAEUMEN, 23 SCHLICHTEN TIEFE, 24 SCHLICHTEN SEITE, 25 KONTUR-ZUG.

Geometrie: Gesamtkontur = Vereinigung aller Taschen minus Vereinigung aller Inseln
(Zyklus 14). Ausräumen konturparallel mit pyclipper-Versatz (runde Ecken), Zustellung
seitlich k = Q2 * R, Tiefen von Q5 in Q10-Schritten bis Q1 (+Aufmaß Q4).
Drehsinn Q9: +1 Gleichlauf (Tasche gegen, Insel im Uhrzeigersinn), -1 Gegenlauf.

Vereinfachungen (vermerkt): Q8 (Innenrundung) wird über runde
Versätze ersetzt; Q18 Vorräumwerkzeug und Q401/Q404 werden noch nicht ausgewertet;
Verbindungsfahrten außerhalb der Fläche werden über Sicherheitsabstand geführt.
"""

from __future__ import annotations

from ..i18n import _t

import math

from .contour import Contour, arc_sweep
from .cyclegen import CycleError, Emit, P, Tool, fmt

try:
    import pyclipper
except ImportError:  # pragma: no cover
    pyclipper = None

SCALE = 1000.0


def _need_clipper():
    if pyclipper is None:
        raise CycleError(_t("Python-Paket 'pyclipper' fehlt (pip install pyclipper / dnf install python3-pyclipper)"))


def _int(path):
    return [(int(round(x * SCALE)), int(round(y * SCALE))) for x, y in path]


def _flt(path):
    return [(x / SCALE, y / SCALE) for x, y in path]


def region(contours: list[Contour]):
    """Fläche (Clipper-Pfade, ganzzahlig) aus Taschen und Inseln."""
    _need_clipper()
    pockets = [_int(c.polyline()) for c in contours if c.is_pocket]
    islands = [_int(c.polyline()) for c in contours if not c.is_pocket]
    if not pockets:
        raise CycleError(_t("Zyklus 14: keine Tasche gefunden (Umlaufsinn/RL/RR prüfen)"))
    pc = pyclipper.Pyclipper()
    pc.AddPaths(pockets, pyclipper.PT_SUBJECT, True)
    if islands:
        pc.AddPaths(islands, pyclipper.PT_CLIP, True)
    return pc.Execute(pyclipper.CT_DIFFERENCE, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)


def offset(paths, d):
    if not paths:
        return []
    po = pyclipper.PyclipperOffset(2.0, 0.005 * SCALE)
    po.AddPaths(paths, pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
    return po.Execute(-d * SCALE)


def inside(paths, pt) -> bool:
    p = (int(round(pt[0] * SCALE)), int(round(pt[1] * SCALE)))
    n = 0
    for path in paths:
        r = pyclipper.PointInPolygon(p, path)
        if r == -1:
            return True
        if r == 1:
            n += 1 if pyclipper.Orientation(path) else -1
    return n > 0


def loops_for(reg, d0, k, ccw_pocket=True):
    """Konturparallele Bahnen: Liste von Ebenen (außen -> innen), je Ebene geschlossene Polygone."""
    levels = []
    d = d0
    while True:
        lv = offset(reg, d)
        if not lv:
            break
        polys = []
        for path in lv:
            pts = _flt(path)
            # pyclipper: Außenkonturen gegen, Inseln im Uhrzeigersinn = Gleichlauf
            if not ccw_pocket:
                pts = list(reversed(pts))
            pts.append(pts[0])
            polys.append(pts)
        levels.append((d, polys, lv))
        d += k
        if len(levels) > 5000:
            raise CycleError(_t("zu viele Bahnen – Zustellung prüfen"))
    return levels


def _rotate_to_nearest(poly, pt):
    if pt is None:
        return poly
    ring = poly[:-1]
    i = min(range(len(ring)), key=lambda j: (ring[j][0] - pt[0]) ** 2 + (ring[j][1] - pt[1]) ** 2)
    ring = ring[i:] + ring[:i]
    return ring + [ring[0]]


def _segment_inside(allowed, a, b, n=8) -> bool:
    return all(inside(allowed, (a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n)) for i in range(n + 1))


def clearing_paths(reg, R, allow_side, k, climb=True):
    """Polygonfolge zum Ausräumen von innen nach außen + Fläche der zulässigen Werkzeugmitte."""
    d0 = R + allow_side
    levels = loops_for(reg, d0, k, ccw_pocket=climb)
    if not levels:
        raise CycleError(_t("Werkzeug zu groß für die Kontur"))
    allowed = levels[0][2]
    seq = []
    for d, polys, _ in reversed(levels):
        seq += polys
    return seq, allowed


def _levels(top, bottom, step):
    step = abs(step)
    if step <= 0 or step >= top - bottom:
        return [bottom]
    out, z = [], top
    while z - step > bottom + 1e-6:
        z -= step
        out.append(z)
    out.append(bottom)
    return out


def plunge_points(seq, allowed):
    pts, cur = [], None
    for poly in seq:
        poly = _rotate_to_nearest(poly, cur)
        if cur is None or not _segment_inside(allowed, cur, poly[0]):
            pts.append(poly[0])
        cur = poly[0]
    return pts


def mill_level(e: Emit, seq, allowed, z, safe_z, f_plunge, f_mill, first_level):
    cur = None
    for poly in seq:
        poly = _rotate_to_nearest(poly, cur)
        start = poly[0]
        if cur is None or not _segment_inside(allowed, cur, start):
            if cur is not None:
                e.rapid_z(safe_z)
            e.rapid_xy(*start)
            e.feed_z(z, f_plunge)
        else:
            e.feed_xy(*start, f_mill)
        for i, pt in enumerate(poly[1:]):
            e.feed_xy(*pt, f_mill if i == 0 else None)
        cur = poly[-1]


def sl_cycle(num, p: P, d20: P, contours: list[Contour], tool: Tool, tools: dict, e: Emit):
    _need_clipper()
    e.rel = False
    surf = d20.n(5)
    depth = d20.n(1)
    if depth >= 0:
        raise CycleError(_t("Zyklus 20: Frästiefe Q1 muss negativ sein"))
    safe_z = surf + d20.n(6)
    clear_z = d20.n(7)
    climb = d20.n(9, 1) >= 0
    reg = region(contours)
    R = tool.r()
    if num == 22:
        k = max(d20.n(2, 1), 0.0001) * R
        seq, allowed = clearing_paths(reg, R, d20.n(3), k, climb)
        bottom = surf + depth + d20.n(4)
        e.rapid_z(clear_z)
        for i, z in enumerate(_levels(surf, bottom, p.n(10))):
            mill_level(e, seq, allowed, z, safe_z, p.f(11), p.f(12), i == 0)
            e.rapid_z(safe_z)
        e.rapid_z(clear_z)
        if p.n(18, 0):
            e.warn.append(_t("Q18 Vorräumwerkzeug (Restmaterial) wird noch nicht ausgewertet"))
    elif num == 21:
        t13 = int(p.n(13, 0))
        rr = (tools.get(t13) or {}).get("R") if t13 else None
        rr = rr if rr else R
        k = max(d20.n(2, 1), 0.0001) * rr
        seq, allowed = clearing_paths(reg, rr, d20.n(3), k, climb)
        pts = plunge_points(seq, allowed)
        bottom = surf + depth + d20.n(4)
        e.rapid_z(clear_z)
        for x, y in pts:
            e.rapid_xy(x, y)
            e.rapid_z(safe_z)
            z = surf
            for zz in _levels(surf, bottom, p.n(10)):
                e.feed_z(zz, p.f(11))
                if zz > bottom + 1e-6:
                    e.rapid_z(safe_z)
                    e.rapid_z(zz + 0.2)
            e.rapid_z(safe_z)
        e.rapid_z(clear_z)
    elif num == 23:
        k = max(d20.n(2, 1), 0.0001) * R
        seq, allowed = clearing_paths(reg, R, d20.n(3), k, climb)
        e.rapid_z(clear_z)
        mill_level(e, seq, allowed, surf + depth, safe_z, p.f(11), p.f(12), True)
        e.rapid_z(clear_z)
    elif num == 24:
        climb24 = p.n(9, 1) >= 0
        levels = loops_for(reg, R + p.n(14, 0), 1.0, ccw_pocket=climb24)
        if not levels:
            raise CycleError(_t("Werkzeug zu groß für die Kontur"))
        polys = levels[0][1]
        e.rapid_z(clear_z)
        for poly in polys:
            for z in _levels(surf, surf + depth, p.n(10)):
                e.rapid_xy(*poly[0])
                e.rapid_z(safe_z)
                e.feed_z(z, p.f(11))
                for i, pt in enumerate(poly[1:]):
                    e.feed_xy(*pt, p.f(12) if i == 0 else None)
                e.rapid_z(safe_z)
        e.rapid_z(clear_z)
    else:
        raise CycleError(_t('Zyklus {0} nicht vorgesehen').format(num))


def _reverse(el):
    return [("L", s[2], s[1]) if s[0] == "L" else ("A", s[2], s[1], s[3], not s[4]) for s in reversed(el)]


def _rot_about(pt, c, ang):
    ca, sa = math.cos(ang), math.sin(ang)
    dx, dy = pt[0] - c[0], pt[1] - c[1]
    return c[0] + dx * ca - dy * sa, c[1] + dx * sa + dy * ca


def contour_train(p: P, contours: list[Contour], tool: Tool, e: Emit, ct: P | None = None):
    """25 KONTUR-ZUG: Kontur mit Radiuskorrektur (LinuxCNC G41.1/G42.1) abfahren.

    Seite aus der Kontur (RL/RR) bzw. aus 270 Q391; Q15 +1 Gleichlauf / −1 Gegenlauf
    bestimmt die Fahrtrichtung (bei M3 ist RL in Konturrichtung Gleichlauf, sonst wird die
    Kontur rückwärts mit getauschter Seite gefahren). Mit 270: An-/Wegfahren tangential
    auf Kreisbogen (Q390=1, Q392/Q393), tangential auf Gerade (2) oder senkrecht (3), Q394.
    """
    e.rel = False
    if len(contours) != 1:
        raise CycleError(_t("Zyklus 25: genau ein Konturunterprogramm in Zyklus 14 angeben"))
    c = contours[0]
    R = tool.r()
    allow = p.n(3, 0)
    surf, depth = p.n(5), p.n(1)
    safe = surf + p.n(6, 2) if 6 in p else surf + 2
    clear = p.n(7)
    comp = c.comp
    if ct is not None:
        comp = {0: "R0", 1: "RL", 2: "RR"}.get(int(ct.n(391, 0)), "R0")
    el = list(c.elements)
    climb = p.n(15, 1) >= 0
    if comp in ("RL", "RR") and climb != (comp == "RL"):
        el, comp = _reverse(el), ("RR" if comp == "RL" else "RL")
    Rc = R + allow
    p0, pend = el[0][1], el[-1][2]
    t0, t1 = _tan(el[0], start=True), _tan(el[-1], start=False)
    side = -1 if comp == "RR" else 1
    n0 = (-t0[1] * side, t0[0] * side)
    n1 = (-t1[1] * side, t1[0] * side)
    approach, depart = [], []  # (Startpunkt, Segment) im Konturkoordinatensystem
    kind = int(ct.n(390, 1)) if ct is not None else 0
    if kind == 1:
        r, a = ct.n(392, 0), math.radians(ct.n(393, 90))
        if r <= 0 or a <= 0:
            raise CycleError(_t("Zyklus 270: Anfahrradius Q392 und Mittelpunktswinkel Q393 müssen > 0 sein"))
        if comp != "R0" and r <= Rc:
            raise CycleError(_t('Zyklus 270: Anfahrradius Q392={0:g} muss größer als Werkzeugradius+Aufmaß sein').format(r))
        ccw = side > 0
        ca = (p0[0] + n0[0] * r, p0[1] + n0[1] * r)
        start = _rot_about(p0, ca, -a if ccw else a)
        approach = [start, ("A", p0, ca, ccw)]
        ce = (pend[0] + n1[0] * r, pend[1] + n1[1] * r)
        end = _rot_about(pend, ce, a if ccw else -a)
        depart = [("A", end, ce, ccw)]
    elif kind in (2, 3):
        d = ct.n(394, 0) or ct.n(392, 0) or Rc
        if kind == 2:
            start = (p0[0] - t0[0] * d, p0[1] - t0[1] * d)
            end = (pend[0] + t1[0] * d, pend[1] + t1[1] * d)
        else:
            start = (p0[0] + n0[0] * d, p0[1] + n0[1] * d)
            end = (pend[0] + n1[0] * d, pend[1] + n1[1] * d)
        approach = [start, ("L", p0)]
        depart = [("L", end)]
    if approach:
        start = approach[0]
        lead = 2 * Rc + 2 if comp != "R0" else 0.0
        pre = (start[0] + n0[0] * lead, start[1] + n0[1] * lead)
        last = depart[-1][1]
        post = (last[0] + n1[0] * lead, last[1] + n1[1] * lead)
    else:  # ohne 270: schräg von außen an den Konturanfang
        lead = 2 * Rc + 2
        pre = (p0[0] - t0[0] * lead + n0[0] * lead, p0[1] - t0[1] * lead + n0[1] * lead)
        post = (pend[0] + t1[0] * lead, pend[1] + t1[1] * lead)
    g = {"RL": "G41.1", "RR": "G42.1"}.get(comp)
    if g and e.mirrored:  # Spiegeln: Seite tauscht
        g = {"G41.1": "G42.1", "G42.1": "G41.1"}[g]

    def seg(s):
        if s[0] == "L":
            e.feed_xy(*s[1])
        else:
            e.arc(s[1][0], s[1][1], s[2][0], s[2][1], s[3])

    e.rapid_z(clear)
    for z in _levels(surf, surf + depth, p.n(10)):
        e.rapid_xy(*pre)
        e.rapid_z(safe)
        e.feed_z(z, p.f(11))
        if g:
            e.raw(f"{g} D{fmt(2 * Rc)}")
        if approach:
            e.feed_xy(*approach[0], p.f(12))
            seg(approach[1])
        else:
            e.feed_xy(*p0, p.f(12))
        for s in el:
            if s[0] == "L":
                e.feed_xy(*s[2])
            else:
                e.arc(s[2][0], s[2][1], s[3][0], s[3][1], s[4])
        for s in depart:
            seg(s)
        if g:
            e.raw(f"G40 G1 {e._xy(*post)}")
            e.cur = post
        else:
            e.feed_xy(*post)
        e.rapid_z(safe)
    e.rapid_z(clear)


def _tan(el, start):
    from .contour import _end_tangent, _start_tangent

    return _start_tangent(el) if start else _end_tangent(el)


__all__ = ["sl_cycle", "contour_train", "region", "arc_sweep"]
