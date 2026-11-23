"""Bahngeometrie für Taschenzyklen: geschlossene Ringe aus Strecken/Bögen, tangentiale Übergänge.

Segmentformat wie in cyclegen: ("L", x, y) | ("A", x, y, cx, cy, ccw) jeweils vom vorherigen Punkt.
"""

from __future__ import annotations

import math

EPS = 1e-9


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def _mul(a, s):
    return (a[0] * s, a[1] * s)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _len(a):
    return math.hypot(a[0], a[1])


def _unit(a):
    n = _len(a)
    return (a[0] / n, a[1] / n) if n > EPS else (1.0, 0.0)


def _left(a):
    return (-a[1], a[0])


class Loop:
    """Geschlossene Bahn: Startpunkt + Segmente. Bietet nächsten Punkt, Tangente und Aufschneiden."""

    def __init__(self, start, segs):
        self.start = (float(start[0]), float(start[1]))
        self.prims = []  # (kind, p0, p1, center, ccw, length, a0, sweep)
        p = self.start
        for s in segs:
            q = (float(s[1]), float(s[2]))
            if s[0] == "L":
                ln = _len(_sub(q, p))
                if ln > EPS:
                    self.prims.append(("L", p, q, None, None, ln, 0.0, 0.0))
            else:
                c = (float(s[3]), float(s[4]))
                ccw = bool(s[5])
                r = _len(_sub(p, c))
                a0 = math.atan2(p[1] - c[1], p[0] - c[0])
                a1 = math.atan2(q[1] - c[1], q[0] - c[0])
                sw = a1 - a0
                if ccw:
                    while sw <= EPS:
                        sw += 2 * math.pi
                else:
                    while sw >= -EPS:
                        sw -= 2 * math.pi
                if abs(sw) > 2 * math.pi - 1e-7 and _len(_sub(p, q)) > 1e-6:
                    sw = math.copysign(abs(sw) - 2 * math.pi, sw)
                self.prims.append(("A", p, q, c, ccw, r * abs(sw), a0, sw))
            p = q
        self.length = sum(pr[5] for pr in self.prims)

    # --- Abfragen
    def _point_on(self, pr, u):
        """Punkt bei Anteil u (0…1) des Elements und Tangente (Einheitsvektor in Fahrtrichtung)."""
        kind, p0, p1, c, ccw, ln, a0, sw = pr
        if kind == "L":
            d = _unit(_sub(p1, p0))
            return _add(p0, _mul(_sub(p1, p0), u)), d
        a = a0 + sw * u
        r = _len(_sub(p0, c))
        pt = (c[0] + r * math.cos(a), c[1] + r * math.sin(a))
        t = (-math.sin(a), math.cos(a)) if sw > 0 else (math.sin(a), -math.cos(a))
        return pt, t

    def nearest(self, q):
        """(Elementindex, Anteil u, Punkt, Tangente) des nächstgelegenen Bahnpunkts zu q."""
        best = None
        for i, pr in enumerate(self.prims):
            kind, p0, p1, c, ccw, ln, a0, sw = pr
            if kind == "L":
                d = _sub(p1, p0)
                u = max(0.0, min(1.0, _dot(_sub(q, p0), d) / max(_dot(d, d), EPS)))
            else:
                a = math.atan2(q[1] - c[1], q[0] - c[0])
                rel = (a - a0) if sw > 0 else (a0 - a)
                rel %= 2 * math.pi
                u = rel / abs(sw) if rel <= abs(sw) else (0.0 if (2 * math.pi - rel) < (rel - abs(sw)) else 1.0)
                u = max(0.0, min(1.0, u))
            pt, t = self._point_on(pr, u)
            dist = _len(_sub(q, pt))
            if best is None or dist < best[0] - 1e-12:
                best = (dist, i, u, pt, t)
        return best[1], best[2], best[3], best[4]

    def at_start_tangent(self):
        return self._point_on(self.prims[0], 0.0)[1]

    def rotated(self, i, u):
        """Gleiche Bahn, beginnend bei Element i, Anteil u. -> (Startpunkt, Segmente)."""
        pt, _ = self._point_on(self.prims[i], u)
        out = []
        order = list(range(i, len(self.prims))) + list(range(0, i))
        head = self.prims[i]
        # Rest des Startelements
        out.append(self._seg_from(head, u, 1.0))
        for k in order[1:]:
            out.append(self._seg_from(self.prims[k], 0.0, 1.0))
        if u > 1e-9:
            out.append(self._seg_from(head, 0.0, u))
        out = [s for s in out if s is not None]
        return pt, out

    def _seg_from(self, pr, u0, u1):
        if u1 - u0 < 1e-12:
            return None
        kind, p0, p1, c, ccw, ln, a0, sw = pr
        q, _ = self._point_on(pr, u1)
        if kind == "L":
            return ("L", q[0], q[1])
        return ("A", q[0], q[1], c[0], c[1], ccw)

    def samples(self, step=0.5):
        pts = [self.start]
        for pr in self.prims:
            n = max(1, int(pr[5] / step))
            for k in range(1, n + 1):
                pts.append(self._point_on(pr, k / n)[0])
        return pts


def _arc_through(p, t, q):
    """Bogen ab p mit Tangente t durch q: ("A", q, Mittelpunkt, ccw) oder ("L", q) bei Gerade."""
    v = _sub(q, p)
    n = _left(t)
    vn = _dot(v, n)
    if abs(vn) < 1e-9 * max(1.0, _len(v)):
        return ("L", q[0], q[1])
    s = _dot(v, v) / (2 * vn)
    c = _add(p, _mul(n, s))
    return ("A", q[0], q[1], c[0], c[1], vn > 0)


def biarc(p0, t0, p1, t1):
    """Zwei tangential verbundene Bögen von p0 (Richtung t0) nach p1 (Richtung t1).
    Gibt Segmentliste zurück oder None, wenn kein brauchbarer Biarc existiert."""
    t0, t1 = _unit(t0), _unit(t1)
    v = _sub(p1, p0)
    if _len(v) < 1e-9:
        return []
    t = _add(t0, t1)
    tt = _dot(t0, t1)
    denom = 2.0 * (1.0 - tt)
    vt = _dot(v, t)
    if abs(denom) < 1e-9:  # parallele Tangenten
        vt1 = _dot(v, t1)
        if vt1 <= 1e-9:
            return None
        d = _dot(v, v) / (4.0 * vt1)
    else:
        disc = vt * vt + denom * _dot(v, v)
        d = (-vt + math.sqrt(max(disc, 0.0))) / denom
    if d <= 1e-9:
        return None
    pm = _mul(_add(_add(p0, _mul(t0, d)), _sub(p1, _mul(t1, d))), 0.5)
    a1 = _arc_through(p0, t0, pm)
    # Tangente in pm am Ende des ersten Bogens
    if a1[0] == "L":
        tm = t0
    else:
        c = (a1[3], a1[4])
        r = _sub(pm, c)
        tm = _unit(_left(r)) if a1[5] else _unit((r[1], -r[0]))
    a2 = _arc_through(pm, tm, p1)
    return [a1, a2]


def sample_segs(start, segs, step=0.25):
    """Punkte entlang einer Segmentliste (für Prüfungen)."""
    return Loop(start, segs).samples(step) if segs else [start]


def merge_lines(start, segs):
    """Aufeinanderfolgende gleichgerichtete Strecken zusammenfassen."""
    out, froms = [], []
    p = start
    for s in segs:
        if s[0] == "L" and out and out[-1][0] == "L" and froms[-1] is not None:
            a, b = froms[-1], out[-1][1:3]
            u, v = _sub(b, a), _sub((s[1], s[2]), b)
            lu, lv = _len(u), _len(v)
            if lu > EPS and lv > EPS and abs(u[0] * v[1] - u[1] * v[0]) < 1e-9 * lu * lv and _dot(u, v) > 0:
                out[-1] = s
                p = (s[1], s[2])
                continue
        out.append(s)
        froms.append(p)
        p = (s[1], s[2])
    return out


def max_sweep(start, segs):
    """Größter Bogenwinkel (Bogenmaß) einer Segmentliste – erkennt Schleifen im Übergang."""
    return max((abs(pr[7]) for pr in Loop(start, segs).prims), default=0.0) if segs else 0.0
