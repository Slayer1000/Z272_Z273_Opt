"""Werkzeug und Halter als Körper für die Anzeige in der Simulation.

``profile(td, holder)`` liefert die Umrisse ab der Werkzeugspitze nach oben (Höhe h entlang der
Werkzeugachse, Radius r), getrennt nach Teilen (Schneide, Schaft, Halter). ``faces(...)`` dreht sie
zu Flächen und setzt sie an die Spitze – mit Schwenkwinkel B wie die Abtragssimulation
(Achse = (-sin B, 0, cos B)).
"""

from __future__ import annotations

import math

import numpy as np

CUT, SHANK, HOLDER = "cut", "shank", "holder"


def _tip(td: dict, R: float):
    """Spitzenform als Punktliste (h, r) von der Achse bis zum vollen Radius."""
    typ = str(td.get("TYPE") or "")
    name = str(td.get("NAME") or "").upper()
    r2 = float(td.get("R2") or 0.0)
    if typ in ("ball", "probe") or (not typ and ("KUGEL" in name or "BALL" in name)):
        return [(R - R * math.cos(a), R * math.sin(a)) for a in np.linspace(0, math.pi / 2, 9)]
    if typ in ("drill", "center", "chamfer", "engrave") or (not typ and td.get("T_ANGLE")):
        ang = float(td.get("T_ANGLE") or 118.0)
        h = R / math.tan(math.radians(max(min(ang, 179.0), 1.0)) / 2)
        return [(0.0, 0.0), (h, R)]
    if 0 < r2 < R:   # Eckenradius (Torus)
        return [(0.0, 0.0), (0.0, R - r2)] + [
            (r2 - r2 * math.cos(a), R - r2 + r2 * math.sin(a)) for a in np.linspace(0, math.pi / 2, 6)[1:]]
    return [(0.0, 0.0), (0.0, R)]


def profile(td: dict, holder=None, with_holder=True):
    """[(Teil, [(h, r), …])] ab der Spitze. holder: Halterkontur (z0, z1, r0, r1) ab Bezugslinie."""
    R = max(float(td.get("R") or 0.0), 0.5)
    L = float(td.get("L") or 0.0)
    lc = float(td.get("LCUTS") or 0.0)
    segs = [s for s in (holder or ()) if max(s[2], s[3]) > 0] if with_holder else []
    h_low = min((L + s[1] for s in segs), default=None) if segs and L > 0 else None
    top = h_low if h_low is not None else (L if L > 0 else 6 * R)
    lc = min(lc, top) if lc > 0 else min(top, max(4 * R, 10.0))
    tip = _tip(td, R)
    lc = max(lc, tip[-1][0])
    out = [(CUT, tip + [(lc, R)])]
    if top > lc + 1e-6:
        rs = R * 0.92 if not td.get("LCUTS") else R   # ohne LCUTS-Angabe: Schaft leicht abgesetzt zeigen
        out.append((SHANK, [(lc, rs), (top, rs)]))
    if h_low is not None:
        for z0, z1, r0, r1 in sorted(segs, key=lambda s: s[1]):
            out.append((HOLDER, [(L + z1, r1), (L + z0, r0)]))
    return out


def faces(prof, tip, b_deg=0.0, n=20):
    """Flächen (Teil, Punkte, Normale nach außen) des Rotationskörpers an der Spitze ``tip`` (x, y, z)."""
    b = math.radians(b_deg)
    ax = np.array((-math.sin(b), 0.0, math.cos(b)))
    ex = np.array((math.cos(b), 0.0, math.sin(b)))   # senkrecht zur Achse in der XZ-Ebene
    ey = np.array((0.0, 1.0, 0.0))
    t = np.asarray(tip[:3], dtype=float)
    ang = np.linspace(0, 2 * math.pi, n, endpoint=False)
    rad = np.cos(ang)[:, None] * ex + np.sin(ang)[:, None] * ey      # Einheitsrichtungen quer zur Achse
    # eine durchgehende Umrisslinie (Absätze als Ringflächen, oben geschlossen)
    chain = []   # (h0, r0, h1, r1, Teil)
    last = None
    for part, pts in prof:
        if last is not None and (abs(last[0] - pts[0][0]) > 1e-9 or abs(last[1] - pts[0][1]) > 1e-9):
            chain.append((last[0], last[1], pts[0][0], pts[0][1], part if pts[0][1] >= last[1] else last[2]))
        for (h0, r0), (h1, r1) in zip(pts, pts[1:]):
            chain.append((h0, r0, h1, r1, part))
        last = (pts[-1][0], pts[-1][1], part)
    if last is not None and last[1] > 0:
        chain.append((last[0], last[1], last[0], 0.0, last[2]))
    out = []
    for h0, r0, h1, r1, part in chain:
        p0 = t + ax * h0 + r0 * rad
        p1 = t + ax * h1 + r1 * rad
        for k in range(n):
            k2 = (k + 1) % n
            q = np.array([p0[k], p0[k2], p1[k2], p1[k]])
            # Normale nach außen: radial (Mantel), längs der Achse (Absätze), geneigt (Kegel)
            mid = (rad[k] + rad[k2]) / 2
            nrm = mid * (h1 - h0) - ax * (r1 - r0)
            ln = np.linalg.norm(nrm)
            out.append((part, q, nrm / ln if ln > 1e-12 else ax))
    return out
