"""Adaptives Räumen (272 KT RAEUMEN) mit begrenzter Eingriffsbreite k = Q370 · R.

Ablauf je Teilfläche C der zulässigen Werkzeugmitte (Fläche um R + Aufmaß verkleinert):

1. Geschlossene Tasche: Helix im Mittelpunkt des größten einbeschriebenen Kreises von C, dann eine
   archimedische Spirale (Zuwachs k je Umlauf) bis zur Wand, dort ein Vollkreis.
   Offene Begrenzung: Start neben dem Rohteil, ohne Eintauchen ins Material.
2. Wachsende Fronten: Front n+1 = (Front n um k erweitert) ∩ C. Gefräst wird der Rand der neuen
   Front, soweit dort noch Material liegt (Teilstücke leicht in geräumtes Gebiet verlängert).
   Jeder Bahnpunkt liegt höchstens k vor dem schon geräumten Bereich – auch in Ecken, Engstellen
   und um Inseln. Läuft der Anfang eines Stücks stirnseitig ins Material (Wand vor der Front),
   wird erst die Front gefräst und der Anfang danach neu bewertet.
3. Verbindungen innerhalb geräumter Fläche leicht angehoben, sonst über den Sicherheitsabstand.
"""

from __future__ import annotations

import math

import numpy as np

from .slcycles import SCALE, _flt, _int, inside, offset, pyclipper  # noqa: F401

TOL_MAT = 0.02   # dünnere Materialreste werden nicht eigens angefahren
STEP = 0.25      # Abtastung der Wandbahnen


# --------------------------------------------------------------------------- Clipper-Helfer
def buffer_open(polylines, r):
    po = pyclipper.PyclipperOffset(2.0, 0.005 * SCALE)
    n = 0
    for pl in polylines:
        if len(pl) >= 2:
            po.AddPath(_int(pl), pyclipper.JT_ROUND, pyclipper.ET_OPENROUND)
            n += 1
    return po.Execute(r * SCALE) if n else []


def disc(cx, cy, r, n=48):
    return [_int([(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n))
                  for i in range(n)])]


def union(a, b):
    if not a:
        return b
    if not b:
        return a
    pc = pyclipper.Pyclipper()
    pc.AddPaths(a, pyclipper.PT_SUBJECT, True)
    pc.AddPaths(b, pyclipper.PT_CLIP, True)
    return pc.Execute(pyclipper.CT_UNION, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)


def components(paths):
    """Zusammenhängende Teilflächen: Liste von Pfadlisten (Außenkontur + Löcher)."""
    if not paths:
        return []
    pc = pyclipper.Pyclipper()
    pc.AddPaths(paths, pyclipper.PT_SUBJECT, True)
    tree = pc.Execute2(pyclipper.CT_UNION, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)
    out = []

    def walk(node):
        for ch in node.Childs:
            if not ch.IsHole:
                comp = [ch.Contour] + [h.Contour for h in ch.Childs]
                out.append(comp)
                for h in ch.Childs:
                    walk(h)
    walk(tree)
    return out


# --------------------------------------------------------------------------- Geometrie mit numpy
def _edges(paths):
    a, b = [], []
    for path in paths:
        pts = np.asarray(_flt(path), dtype=float)
        a.append(pts)
        b.append(np.roll(pts, -1, axis=0))
    return np.concatenate(a), np.concatenate(b)


def _inside_np(pts, A, B):
    """Gerade/ungerade-Regel (Clipper-Ergebnisse überlappen nicht)."""
    res = np.zeros(len(pts), dtype=bool)
    for s in range(0, len(pts), 2000):
        P = pts[s:s + 2000, None, :]
        y1, y2 = A[None, :, 1], B[None, :, 1]
        cond = (y1 > P[..., 1]) != (y2 > P[..., 1])
        with np.errstate(divide="ignore", invalid="ignore"):
            xin = A[None, :, 0] + (P[..., 1] - y1) * (B[None, :, 0] - A[None, :, 0]) / (y2 - y1)
        res[s:s + 2000] = (np.count_nonzero(cond & (P[..., 0] < xin), axis=1) % 2) == 1
    return res


def _dist_np(pts, A, B):
    out = np.empty(len(pts))
    AB = B - A
    L2 = np.maximum((AB ** 2).sum(1), 1e-12)
    for s in range(0, len(pts), 1000):
        P = pts[s:s + 1000, None, :]
        t = np.clip(((P - A[None]) * AB[None]).sum(-1) / L2[None], 0, 1)
        proj = A[None] + t[..., None] * AB[None]
        out[s:s + 1000] = np.sqrt(((P - proj) ** 2).sum(-1)).min(1)
    return out


def max_inscribed(comp):
    """(Mittelpunkt, Radius) des größten einbeschriebenen Kreises (Rasterverfeinerung)."""
    A, B = _edges(comp)
    lo, hi = A.min(0), A.max(0)
    best, rbest = None, -1.0
    span = float(max(hi - lo))
    h = max(span / 60, 0.05)
    cx0, cy0, w = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, span / 2 + h
    for _ in range(4):
        xs = np.arange(cx0 - w, cx0 + w + h / 2, h)
        ys = np.arange(cy0 - w, cy0 + w + h / 2, h)
        G = np.array(np.meshgrid(xs, ys)).reshape(2, -1).T
        G = G[_inside_np(G, A, B)]
        if len(G):
            d = _dist_np(G, A, B)
            i = int(d.argmax())
            if d[i] > rbest:
                best, rbest = (float(G[i, 0]), float(G[i, 1])), float(d[i])
        if best is None:
            break
        cx0, cy0, w, h = best[0], best[1], 3 * h, h / 4
    return best, max(rbest, 0.0)


# --------------------------------------------------------------------------- Bahnen
def spiral(c, r0, r1, k, ccw, tol=0.005):
    """Archimedische Spirale von Radius r0 (Winkel 0) bis r1, danach Vollkreis auf r1."""
    sg = 1 if ccw else -1
    pts, th = [], 0.0
    while True:
        r = min(r0 + k * th / (2 * math.pi), r1)
        pts.append((c[0] + r * math.cos(sg * th), c[1] + r * math.sin(sg * th)))
        if r >= r1 - 1e-9:
            break
        th += min(0.2, 2 * math.sqrt(2 * tol / max(r, 0.1)))
    th_end = th + 2 * math.pi
    dth = min(0.2, 2 * math.sqrt(2 * tol / max(r1, 0.1)))
    while th < th_end - 1e-9:
        th = min(th + dth, th_end)
        pts.append((c[0] + r1 * math.cos(sg * th), c[1] + r1 * math.sin(sg * th)))
    return pts


def _densify(ring, step=STEP):
    out = []
    n = len(ring)
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        m = max(1, int(math.ceil(math.dist(a, b) / step)))
        out += [(a[0] + (b[0] - a[0]) * j / m, a[1] + (b[1] - a[1]) * j / m) for j in range(m)]
    return out


def simplify(pts, tol=1e-4):
    """Kollineare Zwischenpunkte entfernen."""
    if len(pts) < 3:
        return list(pts)
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, b, c = out[-1], pts[i], pts[i + 1]
        cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        if abs(cross) > tol * max(math.dist(a, c), 1e-9) or (b[0] - a[0]) * (c[0] - b[0]) + (b[1] - a[1]) * (c[1] - b[1]) < 0:
            out.append(b)
    out.append(pts[-1])
    return out


def _cut_runs_open(pts, core, ext):
    """Teilstücke eines offenen Polygonzugs, auf denen noch Material liegt (verlängert)."""
    if not core:
        return [(list(pts), False)]
    A, B = _edges(core)
    need = ~_inside_np(np.asarray(pts), A, B)
    ne, n, out, i = max(1, int(round(ext / STEP))), len(pts), [], 0
    while i < n:
        if need[i]:
            j = i
            while j < n and need[j]:
                j += 1
            out.append((list(pts[max(0, i - ne):min(n, j + ne)]), False))
            i = j
        else:
            i += 1
    return out


def _cut_runs(ring, core, ext):
    """Teilstücke einer geschlossenen Bahn, auf denen noch Material liegt (mit Verlängerung).
    -> Liste (Punkte, geschlossen?)"""
    pts = _densify(ring)
    if not core:
        return [(pts + [pts[0]], True)]
    A, B = _edges(core)
    need = ~_inside_np(np.asarray(pts), A, B)
    if not need.any():
        return []
    if need.all():
        return [(pts + [pts[0]], True)]
    i0 = int(np.argmin(need))  # Start in geräumtem Gebiet
    pts = pts[i0:] + pts[:i0]
    need = np.concatenate([need[i0:], need[:i0]])
    n, ne = len(pts), max(1, int(round(ext / STEP)))
    runs, i = [], 0
    while i < n:
        if need[i]:
            j = i
            while j < n and need[j]:
                j += 1
            runs.append([i, j - 1])
            i = j
        else:
            i += 1
    # verlängern, ohne in das Nachbarstück zu laufen
    out = []
    for r_i, (a, b) in enumerate(runs):
        lo = runs[r_i - 1][1] + 1 if r_i else 0
        hi = runs[r_i + 1][0] - 1 if r_i + 1 < len(runs) else n - 1
        a2, b2 = max(lo, a - ne), min(hi, b + ne)
        if r_i == 0 and len(runs) == 1:
            a2, b2 = max(0, a - ne), min(n - 1, b + ne)
        out.append((pts[a2:b2 + 1], False))
    return out


def engagement(pts, cleared, R, n=19):
    """Umschlingung (Grad) der vorderen Werkzeughälfte je Bahnpunkt gegen Geräumtes (erster Punkt 0)."""
    P = np.asarray(pts, dtype=float)
    out = np.zeros(len(P))
    if len(P) < 2:
        return out
    T = np.diff(P, axis=0)
    L = np.linalg.norm(T, axis=1)
    T = T / np.maximum(L, 1e-12)[:, None]
    ang = np.linspace(-math.pi / 2, math.pi / 2, n)
    c, s_ = np.cos(ang), np.sin(ang)
    U = np.stack([T[:, None, 0] * c - T[:, None, 1] * s_, T[:, None, 0] * s_ + T[:, None, 1] * c], -1)
    Q = (P[1:, None, :] + (R - 0.05) * U).reshape(-1, 2)
    if cleared:
        A, B = _edges(cleared)
        mat = ~_inside_np(Q, A, B)
    else:
        mat = np.ones(len(Q), bool)
    out[1:] = mat.reshape(len(P) - 1, n).mean(1) * 180
    out[1:][L < 1e-9] = 0
    return out


def douglas_peucker(pts, tol=0.005):
    """Polygonzug vereinfachen (Abweichung höchstens tol)."""
    if len(pts) < 3:
        return list(pts)
    P = np.asarray(pts, dtype=float)
    keep = np.zeros(len(P), bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(P) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = P[i], P[j]
        ab = b - a
        L = np.hypot(*ab)
        Q = P[i + 1:j]
        if L < 1e-12:
            d = np.hypot(*(Q - a).T)
        else:
            d = np.abs(ab[0] * (Q[:, 1] - a[1]) - ab[1] * (Q[:, 0] - a[0])) / L
        m = int(d.argmax())
        if d[m] > tol:
            keep[i + 1 + m] = True
            stack += [(i, i + 1 + m), (i + 1 + m, j)]
    return [tuple(map(float, p)) for p in P[keep]]


class Segment:
    __slots__ = ("pts", "closed", "front", "late")

    def __init__(self, pts, closed, front, late=False):
        self.pts, self.closed, self.front, self.late = pts, closed, front, late


def _area(paths):
    return sum(pyclipper.Area(p) for p in paths) / SCALE ** 2


def intersect(a, b):
    if not a or not b:
        return []
    pc = pyclipper.Pyclipper()
    pc.AddPaths(a, pyclipper.PT_SUBJECT, True)
    pc.AddPaths(b, pyclipper.PT_CLIP, True)
    return pc.Execute(pyclipper.CT_INTERSECTION, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)


def plan_component(comp, R, k, climb, rh_max, init=None):
    """2D-Plan einer Teilfläche (zulässige Werkzeugmitte): Helix, Spirale, dann Wachstumsfronten.

    Front n+1 = (Front n um k erweitert) ∩ Fläche; gefräst wird der Rand der neuen Front, soweit
    dort noch Material liegt. Jeder Punkt der Front liegt höchstens k vom bereits geräumten Kern
    entfernt – die Eingriffsbreite bleibt auch in Ecken, Engstellen und um Inseln bei höchstens k."""
    c, r_in = max_inscribed(comp)
    rh = min(rh_max, r_in)
    sp = []
    if init is not None:  # offene Fläche: außerhalb des Materials beginnen
        cleared, front = init
        rh, c = 0.0, c
    elif rh > 0.3:
        r1 = max(r_in - 1e-3, rh)
        sp = spiral(c, rh, r1, k, climb)
        cleared = union(disc(c[0], c[1], rh + R, 96), buffer_open([sp], R))
        front = intersect(disc(c[0], c[1], r1 - 1e-3, 192), comp)
    else:
        rh = 0.0
        cleared = disc(c[0], c[1], R, 96)
        front = intersect(disc(c[0], c[1], 0.01, 8), comp)
    outside = difference(_box(comp, 10), offset(comp, -R))  # jenseits der Wand: kein Material
    cleared = union(cleared, outside)
    total = _area(comp)
    e_lim = min(math.degrees(math.acos(max(-1.0, 1 - k / R))) + 40, 160)
    segs_by_front = []
    n = 0
    while front and _area(front) < total - 1e-3 and n < 5000:
        n += 1
        grown = intersect(offset(front, -k), comp)
        if not grown or _area(grown) <= _area(front) + 1e-4:
            break
        core = offset(cleared, R - TOL_MAT)
        queue = []
        for path in grown:
            ring = _flt(path)
            if not climb:
                ring = list(reversed(ring))
            for pts, closed in _cut_runs(ring, core, min(R, 2.0)):
                if len(pts) >= 2:
                    queue.append([pts, closed, False])
        segs = []
        while queue:
            pts, closed, retried = queue.pop(0)
            if retried:  # nach dem Rest der Front erneut prüfen
                core = offset(cleared, R - TOL_MAT)
                runs = _cut_runs_open(pts, core, min(R, 2.0))
            else:
                runs = [(pts, closed)]
            for pts2, closed2 in runs:
                if len(pts2) < 2:
                    continue
                E = engagement(pts2, cleared, R)
                i = 0
                if not closed2 and not retried:
                    hot = np.nonzero(E > e_lim)[0]
                    if len(hot):
                        h0 = int(hot[0])
                        h1 = h0
                        while h1 < len(E) and E[h1] > e_lim:
                            h1 += 1
                        seglen = np.linalg.norm(np.diff(np.asarray(pts2), axis=0), axis=1)
                        cum = np.concatenate([[0.0], np.cumsum(seglen)])
                        if cum[h0] < 0.5 * cum[-1] and h1 < len(E) - 1:
                            i = h1
                if 0 < i < len(pts2) - 1:
                    # Anfang läuft stirnseitig ins Material (Wand vor der Front): erst die Front fräsen
                    queue.append([pts2[:i + 1], False, True])
                    pts2 = pts2[i:]
                segs.append(Segment(pts2, closed2, n, retried))
                cleared = union(cleared, buffer_open([pts2], R))
        if segs:
            segs_by_front.append(segs)
        front = grown
    # Reihenfolge: Front für Front, innerhalb der Front das nächstgelegene Stück
    end = sp[-1] if sp else (segs_by_front[0][0].pts[0] if init is not None and segs_by_front else c)
    order = []
    for segs in segs_by_front:
        left = list(segs)
        while left:
            best = None
            early = [sg for sg in left if not sg.late] or left
            for sg in early:
                if sg.closed:
                    ring = sg.pts[:-1]
                    i = min(range(len(ring)), key=lambda q: (ring[q][0] - end[0]) ** 2 + (ring[q][1] - end[1]) ** 2)
                    dd = math.dist(ring[i], end)
                else:
                    i, dd = None, math.dist(sg.pts[0], end)
                if best is None or dd < best[0]:
                    best = (dd, sg, i)
            _, sg, i = best
            if sg.closed:
                ring = sg.pts[:-1]
                ring = ring[i:] + ring[:i]
                sg.pts = ring + [ring[0]]
            left.remove(sg)
            order.append(sg)
            end = sg.pts[-1]
    for sg in order:
        sg.pts = douglas_peucker(sg.pts)
    return dict(comp=comp, outside=outside, center=c, r_in=r_in, rh=rh, cleared0=init[0] if init is not None else None, spiral=douglas_peucker(sp, 0.002) if sp else [], segments=order)


def plan(allowed, R, k, climb, rh_max):
    return [plan_component(comp, R, k, climb, rh_max) for comp in components(allowed)]


def difference(a, b):
    if not a or not b:
        return a
    pc = pyclipper.Pyclipper()
    pc.AddPaths(a, pyclipper.PT_SUBJECT, True)
    pc.AddPaths(b, pyclipper.PT_CLIP, True)
    return pc.Execute(pyclipper.CT_DIFFERENCE, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)


def _box(paths, margin):
    xs = [p[0] for path in paths for p in path]
    ys = [p[1] for path in paths for p in path]
    m = int(margin * SCALE)
    return [[(min(xs) - m, min(ys) - m), (max(xs) + m, min(ys) - m), (max(xs) + m, max(ys) + m),
             (min(xs) - m, max(ys) + m)]]


def plan_open(material, R, allow, k, climb):
    """Offene Begrenzung (Material = Begrenzung − Inseln): Fronten wachsen von außen nach innen.
    Das Werkzeug taucht neben dem Material ein; Inseln (Löcher der Fläche) bleiben um R + Aufmaß frei."""
    outer, holes = [], []
    for comp in components(material):
        outer.append(comp[0])
        holes += [list(reversed(h)) for h in comp[1:]]
    keep_out = offset(holes, -(R + allow)) if holes else []
    allowed = difference(offset(outer, -(R + allow + 2 * k)), keep_out)
    if not allowed:
        return []
    box = _box(allowed, 10)
    stock = union(outer, [])
    cleared = difference(box, stock)  # außerhalb des Rohteils ist nichts zu fräsen
    free = difference(allowed, offset(stock, -(R + 0.2)))  # Werkzeug berührt kein Material
    return [plan_component(comp, R, k, climb, 0.0, init=(cleared, intersect(free, comp)))
            for comp in components(allowed)]


def segment_free(cleared_core, a, b, step=0.5):
    """Gerade a-b verläuft vollständig in geräumter Fläche (Werkzeug schneidet nicht)."""
    n = max(1, int(math.dist(a, b) / step))
    return all(inside(cleared_core, (a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n))
               for i in range(n + 1))


def free_link(core, a, b, center):
    """Verbindung a -> b innerhalb geräumter Fläche: gerade oder über einen Zwischenpunkt
    Richtung Flächenmitte. -> Punktliste (ohne a) oder None."""
    if segment_free(core, a, b):
        return [b]
    for t in (0.2, 0.4, 0.6, 0.8):
        for w in ((a[0] + (center[0] - a[0]) * t, a[1] + (center[1] - a[1]) * t),
                  (b[0] + (center[0] - b[0]) * t, b[1] + (center[1] - b[1]) * t)):
            if segment_free(core, a, w) and segment_free(core, w, b):
                return [w, b]
    return None


# --------------------------------------------------------------------------- weiche Verbindungen
class Prim:
    """Bahnelement: Gerade ("L") oder Kreisbogen ("A", Mittelpunkt c, Bogenwinkel sweep, + = gegen Uhrzeiger)."""
    __slots__ = ("kind", "p0", "p1", "c", "sweep", "length")

    def __init__(self, kind, p0, p1, c=None, sweep=0.0):
        self.kind, self.p0, self.p1, self.c, self.sweep = kind, p0, p1, c, sweep
        self.length = math.dist(p0, p1) if kind == "L" else abs(sweep) * math.dist(p0, c)

    def at(self, f):
        if self.kind == "L":
            return (self.p0[0] + (self.p1[0] - self.p0[0]) * f, self.p0[1] + (self.p1[1] - self.p0[1]) * f)
        r = math.dist(self.p0, self.c)
        a = math.atan2(self.p0[1] - self.c[1], self.p0[0] - self.c[0]) + self.sweep * f
        return (self.c[0] + r * math.cos(a), self.c[1] + r * math.sin(a))

    def split(self, f):
        m = self.at(f)
        if self.kind == "L":
            return Prim("L", self.p0, m), Prim("L", m, self.p1)
        return Prim("A", self.p0, m, self.c, self.sweep * f), Prim("A", m, self.p1, self.c, self.sweep * (1 - f))


def _unit(v):
    n = math.hypot(*v)
    return (v[0] / n, v[1] / n) if n > 1e-12 else (1.0, 0.0)


def _lft(v):
    return (-v[1], v[0])


def _arc(p, c, q, left):
    a0 = math.atan2(p[1] - c[1], p[0] - c[0])
    a1 = math.atan2(q[1] - c[1], q[0] - c[0])
    sw = (a1 - a0) % (2 * math.pi) if left else -((a0 - a1) % (2 * math.pi))
    if abs(sw) > 2 * math.pi - 1e-7:
        sw = 0.0
    return Prim("A", p, q, c, sw) if abs(sw) > 1e-9 and math.dist(p, q) > 1e-9 else None


def dubins(p0, h0, p1, h1, r):
    """Kürzeste Wege Bogen–Gerade–Bogen (Radius r) von p0/Richtung h0 nach p1/Richtung h1,
    nach Länge sortiert. -> Liste von Prim-Listen"""
    h0, h1 = _unit(h0), _unit(h1)
    out = []
    for s0 in (True, False):        # True = Linkskurve
        for s1 in (True, False):
            n0, n1 = _lft(h0), _lft(h1)
            c0 = (p0[0] + (r if s0 else -r) * n0[0], p0[1] + (r if s0 else -r) * n0[1])
            c1 = (p1[0] + (r if s1 else -r) * n1[0], p1[1] + (r if s1 else -r) * n1[1])
            v = (c1[0] - c0[0], c1[1] - c0[1])
            D = math.hypot(*v)
            if s0 == s1:
                if D < 1e-9:
                    continue
                h = _unit(v)
            else:
                if D < 2 * r:
                    continue
                phi = math.atan2(v[1], v[0])
                th = phi + (1 if s0 else -1) * math.asin(2 * r / D)
                h = (math.cos(th), math.sin(th))
            lh = _lft(h)
            t0 = (c0[0] - (r if s0 else -r) * lh[0], c0[1] - (r if s0 else -r) * lh[1])
            t1 = (c1[0] - (r if s1 else -r) * lh[0], c1[1] - (r if s1 else -r) * lh[1])
            prims = [_arc(p0, c0, t0, s0), Prim("L", t0, t1) if math.dist(t0, t1) > 1e-9 else None,
                     _arc(t1, c1, p1, s1)]
            prims = [q for q in prims if q is not None]
            out.append((sum(q.length for q in prims), prims))
    out.sort(key=lambda x: x[0])
    return [p for _, p in out]


def prims_free(core, prims, step=0.3, skip_end=0.0, allowed=None):
    """Bahnelemente in geräumter Fläche; das letzte Stück (skip_end) darf ins Material einlaufen,
    muss aber innerhalb der zulässigen Fläche (allowed) bleiben."""
    if not core:
        return False
    pts, tail = [], []
    end = prims[-1].p1
    for q in prims:
        n = max(1, int(q.length / step))
        for p in (q.at(i / n) for i in range(n + 1)):
            (pts if math.dist(p, end) >= skip_end else tail).append(p)
    if tail and skip_end > 0:
        if allowed is None:
            return False
        A, B = _edges(allowed)
        if not _inside_np(np.asarray(tail), A, B).all():
            return False
    if not pts:
        return True
    A, B = _edges(core)
    return bool(_inside_np(np.asarray(pts), A, B).all())


def smooth_link(core, p0, h0, p1, h1, r, center=None, allowed=None):
    """Weiche Verbindung durch geräumte Fläche (Bögen Radius r, wie Aus-/Einfahrbögen) oder None.
    Geht es nicht direkt, über einen Zwischenpunkt Richtung Flächenmitte."""
    if math.dist(p0, p1) < 1e-6:
        return []

    def direct(a, ha, b, hb):
        for rr in (r, r / 2):
            for prims in dubins(a, ha, b, hb, rr):
                if prims_free(core, prims, skip_end=1.5 * rr if b is p1 else 0.0, allowed=allowed):
                    return prims
        return None
    res = direct(p0, h0, p1, h1)
    if res is not None or center is None:
        return res
    for t in (0.2, 0.4, 0.6, 0.8):
        for w in ((p0[0] + (center[0] - p0[0]) * t, p0[1] + (center[1] - p0[1]) * t),
                  (p1[0] + (center[0] - p1[0]) * t, p1[1] + (center[1] - p1[1]) * t)):
            hw = (p1[0] - w[0], p1[1] - w[1])
            a = direct(p0, h0, w, hw)
            if a is None:
                continue
            b = direct(w, hw, p1, h1)
            if b is not None:
                return a + b
    return None


def lead_arc(core, p, h, r, left, into, allowed=None):
    """Viertelkreis zur geräumten Seite: into=False Ausfahren ab p, into=True Einfahren nach p."""
    h = _unit(h)
    n = _lft(h) if left else (h[1], -h[0])
    c = (p[0] + r * n[0], p[1] + r * n[1])
    if into:  # Bogen endet tangential in p
        q = (c[0] - r * h[0], c[1] - r * h[1])
        prims = [_arc(q, c, p, left)]
    else:
        q = (c[0] + r * h[0], c[1] + r * h[1])
        prims = [_arc(p, c, q, left)]
    prims = [x for x in prims if x is not None]
    if prims and prims_free(core, prims, skip_end=min(1.2 * r, 2.0) if into else 0.0, allowed=allowed):
        return prims
    if into and r < 8:  # Einfahren: größeren Bogen aus der geräumten Fläche versuchen
        return lead_arc(core, p, h, r * 2, left, into, allowed)
    return lead_arc(core, p, h, r / 2, left, into, allowed) if not into and r > 0.3 else None
