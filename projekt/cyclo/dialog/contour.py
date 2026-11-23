"""Konturen aus Dialog-Unterprogrammen (für SL-Zyklen 14/20-25 und Konturtaschen).

Ein Kontur-Unterprogramm ``LBL n ... LBL 0`` wird in Elemente zerlegt:
    ("L", p0, p1)                 Gerade
    ("A", p0, p1, center, ccw)    Kreisbogen
Unterstützt: L, CC, C, CR, CT, RND, CHF; absolut und inkremental (IX/IY).
Tasche oder Insel nach Dialog-Regel: Tasche = Kontur innen umfahren
(z. B. Uhrzeigersinn mit RR), Insel = außen umfahren (Uhrzeigersinn mit RL).
"""

from __future__ import annotations

from ..i18n import _t

import math
from dataclasses import dataclass

from .parser import Block


class ContourError(Exception):
    pass


@dataclass
class Contour:
    label: object
    elements: list
    comp: str  # RL | RR | R0
    closed: bool

    @property
    def area(self) -> float:
        pts = self.polyline(0.01)
        return 0.5 * sum(pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1] for i in range(len(pts) - 1))

    @property
    def is_pocket(self) -> bool:
        ccw = self.area > 0
        if self.comp == "RL":
            return ccw
        if self.comp == "RR":
            return not ccw
        return True  # ohne Korrektur: als Tasche behandeln

    def polyline(self, tol=0.005) -> list[tuple[float, float]]:
        pts = []
        for e in self.elements:
            if not pts:
                pts.append(e[1])
            if e[0] == "L":
                pts.append(e[2])
            else:
                pts += arc_points(e[1], e[2], e[3], e[4], tol)[1:]
        return pts


def arc_sweep(p0, p1, c, ccw) -> float:
    a0 = math.atan2(p0[1] - c[1], p0[0] - c[0])
    a1 = math.atan2(p1[1] - c[1], p1[0] - c[0])
    sw = a1 - a0
    if ccw:
        while sw <= 1e-9:
            sw += 2 * math.pi
    else:
        while sw >= -1e-9:
            sw -= 2 * math.pi
    return sw


def arc_points(p0, p1, c, ccw, tol=0.005):
    r = math.hypot(p0[0] - c[0], p0[1] - c[1])
    sw = arc_sweep(p0, p1, c, ccw)
    if r < 1e-9:
        return [p0, p1]
    step = 2 * math.acos(max(-1.0, min(1.0, 1 - tol / r))) if r > tol else math.pi / 4
    n = max(2, int(math.ceil(abs(sw) / max(step, 1e-3))))
    a0 = math.atan2(p0[1] - c[1], p0[0] - c[0])
    pts = [(c[0] + r * math.cos(a0 + sw * i / n), c[1] + r * math.sin(a0 + sw * i / n)) for i in range(n + 1)]
    pts[-1] = p1
    return pts


def _num(v, line):
    n = v.number()
    if n is None:
        raise ContourError(_t('Zeile {0}: Q-Parameter in Konturen werden noch nicht unterstützt').format(line + 1))
    return n


def _end_tangent(e):
    if e[0] == "L":
        d = (e[2][0] - e[1][0], e[2][1] - e[1][1])
    else:
        c, p = e[3], e[2]
        r = (p[0] - c[0], p[1] - c[1])
        d = (-r[1], r[0]) if e[4] else (r[1], -r[0])
    n = math.hypot(*d) or 1.0
    return d[0] / n, d[1] / n


def _start_tangent(e):
    if e[0] == "L":
        d = (e[2][0] - e[1][0], e[2][1] - e[1][1])
    else:
        c, p = e[3], e[1]
        r = (p[0] - c[0], p[1] - c[1])
        d = (-r[1], r[0]) if e[4] else (r[1], -r[0])
    n = math.hypot(*d) or 1.0
    return d[0] / n, d[1] / n


def contour_from_blocks(label, blocks: list[Block]) -> Contour:
    """Elemente eines Kontur-Unterprogramms (Sätze zwischen LBL n und LBL 0)."""
    pos = [None, None]
    cc = None
    comp = "R0"
    elems = []
    corners = []  # (index des Elements davor, kind, size)
    for b in blocks:
        k = b.kind
        if k in ("STRUCT", "COMMENT"):
            continue
        if k in ("L", "C", "CR", "CT", "CC"):
            tgt = list(pos)
            for c in b.data.get("coords", []):
                if c.axis not in "XY":
                    if k != "CC":
                        raise ContourError(_t('Zeile {0}: keine Koordinaten in der Spindelachse in SL-Konturen').format(b.line + 1))
                    continue
                i = 0 if c.axis == "X" else 1
                v = _num(c.value, b.line)
                if c.incremental:
                    base = (cc[i] if (k == "CC" and cc) else pos[i])
                    if base is None:
                        raise ContourError(_t('Zeile {0}: inkrementale Angabe ohne Bezug').format(b.line + 1))
                    v = base + v
                tgt[i] = v
            if k == "CC":
                if None in tgt:
                    raise ContourError(_t('Zeile {0}: Kreismittelpunkt unvollständig').format(b.line + 1))
                cc = tuple(tgt)
                continue
            rc = b.data.get("radius_comp")
            if rc in ("RL", "RR") and comp == "R0":
                comp = rc
            if None in pos:
                if None in tgt:
                    raise ContourError(_t('Zeile {0}: im ersten Satz der Kontur beide Achsen programmieren').format(b.line + 1))
                pos = tgt
                continue
            p0, p1 = tuple(pos), tuple(tgt)
            if k == "L":
                if math.hypot(p1[0] - p0[0], p1[1] - p0[1]) > 1e-9:
                    elems.append(("L", p0, p1))
            elif k == "C":
                if cc is None:
                    raise ContourError(_t('Zeile {0}: C ohne CC').format(b.line + 1))
                elems.append(("A", p0, p1, cc, b.data["dir"] == "+"))
            elif k == "CR":
                r = _num(b.data["radius"], b.line)
                ccw = b.data["dir"] == "+"
                d = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
                if abs(r) < d / 2 - 1e-9:
                    raise ContourError(_t('Zeile {0}: CR-Radius zu klein').format(b.line + 1))
                h = math.sqrt(max(r * r - d * d / 4, 0))
                mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
                nx, ny = -(p1[1] - p0[1]) / d, (p1[0] - p0[0]) / d  # linke Normale
                # kleiner Bogen (R>0): Mittelpunkt auf der Seite, um die gedreht wird
                side = 1 if ccw else -1
                if r < 0:
                    side = -side
                c = (mx + side * h * nx, my + side * h * ny)
                elems.append(("A", p0, p1, c, ccw))
            elif k == "CT":
                if not elems:
                    raise ContourError(_t('Zeile {0}: CT braucht ein vorheriges Element').format(b.line + 1))
                t = _end_tangent(elems[-1])
                n = (-t[1], t[0])
                dv = (p1[0] - p0[0], p1[1] - p0[1])
                den = 2 * (dv[0] * n[0] + dv[1] * n[1])
                if abs(den) < 1e-12:
                    elems.append(("L", p0, p1))
                else:
                    r = (dv[0] ** 2 + dv[1] ** 2) / den
                    c = (p0[0] + n[0] * r, p0[1] + n[1] * r)
                    elems.append(("A", p0, p1, c, r > 0))
            pos = list(p1)
        elif k in ("RND", "CHF"):
            corners.append((len(elems) - 1, k, _num(b.data["size"], b.line)))
        elif k in ("LBL", "END_PGM"):
            continue
        else:
            raise ContourError(_t('Zeile {0}: {1} ist in Konturunterprogrammen nicht erlaubt').format(b.line + 1, k))
    if not elems:
        raise ContourError(_t('LBL {0}: Kontur ohne Elemente').format(label))
    closed = math.hypot(elems[-1][2][0] - elems[0][1][0], elems[-1][2][1] - elems[0][1][1]) < 1e-6
    # RND/CHF einsetzen (zwischen zwei Geraden)
    for idx, kind, size in reversed(corners):
        if idx < 0:
            continue
        nxt = idx + 1 if idx + 1 < len(elems) else (0 if closed else None)
        if nxt is None:
            raise ContourError(_t('{0} am Konturende ohne Folgeelement').format(kind))
        e1, e2 = elems[idx], elems[nxt]
        if e1[0] != "L" or e2[0] != "L":
            raise ContourError(_t('{0}: vorerst nur zwischen zwei Geraden').format(kind))
        p1 = e1[2]
        u = (e1[1][0] - p1[0], e1[1][1] - p1[1])
        v = (e2[2][0] - p1[0], e2[2][1] - p1[1])
        lu, lv = math.hypot(*u), math.hypot(*v)
        u, v = (u[0] / lu, u[1] / lu), (v[0] / lv, v[1] / lv)
        ang = math.acos(max(-1.0, min(1.0, u[0] * v[0] + u[1] * v[1])))
        d = size / math.tan(ang / 2) if kind == "RND" else size
        if d > min(lu, lv) + 1e-9:
            raise ContourError(_t('{0} {1:g} zu groß').format(kind, size))
        t1 = (p1[0] + u[0] * d, p1[1] + u[1] * d)
        t2 = (p1[0] + v[0] * d, p1[1] + v[1] * d)
        mid = []
        if kind == "RND":
            bis = (u[0] + v[0], u[1] + v[1])
            bl = math.hypot(*bis)
            dc = size / math.sin(ang / 2)
            c = (p1[0] + bis[0] / bl * dc, p1[1] + bis[1] / bl * dc)
            d1 = (-u[0], -u[1])
            ccw = (d1[0] * v[1] - d1[1] * v[0]) > 0
            mid = [("A", t1, t2, c, ccw)]
        else:
            mid = [("L", t1, t2)]
        elems[idx] = ("L", e1[1], t1)
        elems[nxt] = ("L", t2, e2[2])
        elems[idx + 1:idx + 1] = mid if nxt != 0 else []
        if nxt == 0:
            elems.extend(mid)
    return Contour(label, elems, comp, closed)


def find_label_blocks(blocks: list[Block], label) -> list[Block]:
    """Sätze eines Unterprogramms LBL label ... LBL 0."""
    out, inside = [], False
    for b in blocks:
        if b.kind == "LBL":
            if inside:
                break
            if b.data["label"] == label or str(b.data["label"]) == str(label):
                inside = True
            continue
        if inside:
            out.append(b)
    if not inside:
        raise ContourError(_t('LBL {0} nicht gefunden').format(label))
    return out
