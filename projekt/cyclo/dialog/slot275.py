"""275 KONTURNUT WIRBELFRAESEN: Nut entlang einer Kontur (Zyklus 14, optional 270).

Kontur ohne Korrektur (R0) = Nutmitte; mit RL/RR (aus der Kontur oder 270 Q391) ist
die Kontur eine Nutwand, die Nut liegt links (RL) bzw. rechts (RR) davon.

Schruppen: Wirbelfräsen als Folge von Vollkreisen (Radius Nutbreite/2 − Aufmaß − R),
deren Mittelpunkte um Q436 entlang der Nutmitte vorrücken; Eintauchen helixförmig mit
dem Eintauchwinkel des Werkzeugs, ohne ANGLE senkrecht mit Q206. Schlichten: Nutwände
als geschlossene Bahn um die Nutmitte (runde Enden), Zustellung Q338.
Q351 +1 Gleichlauf (Kreise gegen den Uhrzeigersinn), −1 Gegenlauf.
"""

from __future__ import annotations

from ..i18n import _t

import math

from .contour import Contour
from .cyclegen import CycleError, Emit, P, Tool, _levels, heights
from .slcycles import SCALE, _flt, _int, _need_clipper

try:
    import pyclipper
except ImportError:  # pragma: no cover
    pyclipper = None


def _closed(poly) -> bool:
    return math.dist(poly[0], poly[-1]) < 1e-6


def _clean(poly):
    out = [poly[0]]
    for p in poly[1:]:
        if math.dist(p, out[-1]) > 1e-6:
            out.append(p)
    return out


def offset_line(poly, d):
    """Polylinie um d nach links (d > 0) bzw. rechts versetzen (Gehrung, für Nutmitte aus Nutwand)."""
    poly = _clean(poly)
    closed = _closed(poly)
    n = len(poly)
    segs = []
    for i in range(n - 1):
        (x0, y0), (x1, y1) = poly[i], poly[i + 1]
        ln = math.hypot(x1 - x0, y1 - y0)
        nx, ny = -(y1 - y0) / ln, (x1 - x0) / ln
        segs.append(((x0 + nx * d, y0 + ny * d), (x1 + nx * d, y1 + ny * d)))
    out = [segs[0][0]] if not closed else []
    pairs = list(zip(segs, segs[1:])) + ([(segs[-1], segs[0])] if closed else [])
    for (a0, a1), (b0, b1) in pairs:
        dax, day = a1[0] - a0[0], a1[1] - a0[1]
        dbx, dby = b1[0] - b0[0], b1[1] - b0[1]
        den = dax * dby - day * dbx
        if abs(den) < 1e-12:
            out.append(a1)
            continue
        t = ((b0[0] - a0[0]) * dby - (b0[1] - a0[1]) * dbx) / den
        out.append((a0[0] + dax * t, a0[1] + day * t))
    if closed:
        out.append(out[0])
    else:
        out.append(segs[-1][1])
    return out


def sample(poly, step):
    """Punkte mit Richtung im Abstand step entlang der Polylinie (Anfang und Ende inklusive)."""
    poly = _clean(poly)
    lens = [math.dist(poly[i], poly[i + 1]) for i in range(len(poly) - 1)]
    total = sum(lens)
    if total <= 0:
        raise CycleError(_t("Kontur hat die Länge 0"))
    n = max(1, math.ceil(total / step - 1e-9))
    out, i, acc = [], 0, 0.0
    for k in range(n + 1):
        s = total * k / n
        while i < len(lens) - 1 and acc + lens[i] < s - 1e-9:
            acc += lens[i]
            i += 1
        (x0, y0), (x1, y1) = poly[i], poly[i + 1]
        t = (s - acc) / lens[i] if lens[i] else 0.0
        t = min(max(t, 0.0), 1.0)
        out.append(((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t), ((x1 - x0) / lens[i], (y1 - y0) / lens[i])))
    return out, total


def wall_loops(center, d, climb):
    """Geschlossene Bahn(en) im Abstand d um die Nutmitte, Umlaufsinn für Gleich-/Gegenlauf."""
    po = pyclipper.PyclipperOffset(2.0, 0.005 * SCALE)
    po.AddPath(_int(center), pyclipper.JT_ROUND, pyclipper.ET_CLOSEDLINE if _closed(center) else pyclipper.ET_OPENROUND)
    loops = []
    for path in po.Execute(d * SCALE):
        pts = _flt(path)
        if not climb:
            pts = pts[::-1]
        loops.append(pts + [pts[0]])
    return loops


def _plunge(e: Emit, c, u, rho, z_from, z_to, tool: Tool, f, ccw):
    """Am Kreis um c eintauchen (Helix mit ANGLE, sonst senkrecht); endet im Startpunkt c + rho*u."""
    sx, sy = c[0] + rho * u[0], c[1] + rho * u[1]
    if tool.angle and tool.angle > 0 and rho > 0.05:
        pitch = 2 * math.pi * rho * math.tan(math.radians(tool.angle))
        z = z_from
        while z > z_to + 1e-6:
            z = max(z - pitch, z_to)
            e.arc(sx, sy, c[0], c[1], ccw, f, z=z)
    else:
        e.feed_z(z_to, f)


def trochoid_slot(p: P, contours: list[Contour], tool: Tool, e: Emit, ct: P | None = None):
    _need_clipper()
    e.rel = False
    if len(contours) != 1:
        raise CycleError(_t("Zyklus 275: genau ein Konturunterprogramm in Zyklus 14 angeben"))
    c = contours[0]
    R = tool.r()
    width = p.n(219)
    allow, allow_z = p.n(368, 0), p.n(369, 0)
    if width < 2 * R - 1e-9:
        raise CycleError(_t('Nutbreite Q219={0:g} kleiner als Werkzeugdurchmesser {1:g}').format(width, 2 * R))
    surf, safe, second = heights(p)
    depth = p.n(201)
    if depth >= 0:
        raise CycleError(_t("Tiefe Q201 muss negativ sein"))
    mode = int(p.n(215, 0))
    climb = p.n(351, 1) >= 0
    step = p.n(436, 0) or 0.3 * R
    comp = c.comp
    if ct is not None:
        comp = {0: "R0", 1: "RL", 2: "RR"}.get(int(ct.n(391, 0)), "R0")
    center = c.polyline()
    if comp == "RL":
        center = offset_line(center, width / 2)
    elif comp == "RR":
        center = offset_line(center, -width / 2)
    rho = width / 2 - allow - R
    if rho < -1e-9:
        raise CycleError(_t("Werkzeug zu groß für Nutbreite und Aufmaß"))
    rho = max(rho, 0.0)
    pts, _ = sample(center, step)
    bottom = surf + depth
    ccw = climb
    e.rapid_z(second)

    def trochoid_level(z_prev, z, f_mill):
        (c0, u0) = pts[0]
        e.rapid_xy(c0[0] + rho * u0[0], c0[1] + rho * u0[1])
        e.rapid_z(safe if z_prev >= surf - 1e-9 else z_prev + p.n(200))
        e.feed_z(z_prev, p.f(206))
        _plunge(e, c0, u0, rho, z_prev, z, tool, p.f(206), ccw)
        first = True
        for cc, u in pts:
            sx, sy = cc[0] + rho * u[0], cc[1] + rho * u[1]
            e.feed_xy(sx, sy, f_mill if first else None)
            if rho > 0.05:
                e.arc(sx, sy, cc[0], cc[1], ccw, f_mill if first else None)
            first = False
        e.rapid_z(safe)

    if mode in (0, 1):
        z_prev = surf
        for z in _levels(surf, bottom + allow_z, p.n(202)):
            trochoid_level(z_prev, z, p.f(207))
            z_prev = z
    if mode in (0, 2):
        if allow_z > 0:  # Boden: eine Wirbelbahn auf Endtiefe
            trochoid_level(bottom + allow_z, bottom, p.f(385))
        loops = wall_loops(center, width / 2 - R, climb)
        if not loops:
            raise CycleError(_t("Werkzeug zu groß für die Nutbreite"))
        for z in _levels(surf, bottom, p.n(338)):
            for loop in loops:
                # vom nächstgelegenen Punkt der Nutmitte aus anfahren
                k = min(range(len(loop) - 1), key=lambda i: min(math.dist(loop[i], q) for q, _ in pts[::4] or pts))
                loop = loop[k:-1] + loop[:k] + [loop[k]]
                mid = min((q for q, _ in pts), key=lambda q: math.dist(q, loop[0]))
                e.rapid_xy(*mid)
                e.rapid_z(safe)
                e.feed_z(z, p.f(206))
                e.feed_xy(*loop[0], p.f(385))
                for q in loop[1:]:
                    e.feed_xy(*q)
                e.feed_xy(*mid)
                e.rapid_z(safe)
    e.rapid_z(second)
