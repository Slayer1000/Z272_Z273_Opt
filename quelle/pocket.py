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


def region_from_polys(pockets, islands, boundary=None):
    """Clipper-Fläche: (Begrenzung ∪ Taschen) − Inseln."""
    _need_clipper()
    subj = [_int(_ccw(p)) for p in pockets]
    if boundary is not None:
        subj.append(_int(_ccw(boundary)))
    pc = pyclipper.Pyclipper()
    pc.AddPaths(subj, pyclipper.PT_SUBJECT, True)
    if islands:
        pc.AddPaths([_int(_ccw(p)) for p in islands], pyclipper.PT_CLIP, True)
    return pc.Execute(pyclipper.CT_DIFFERENCE, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)


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


def adaptive_272(e: Emit, reg, tool: Tool, p: P, data: P, open_bnd=False):
    """Adaptives Räumen mit gleichbleibender Eingriffsbreite (siehe adaptive.py). Geschlossene Tasche:
    Helix + Spirale; offene Begrenzung: Eintauchen neben dem Material, Fronten von außen."""
    from . import adaptive as ad
    from .cyclegen import _helix_in, _helix_start_angle
    R = tool.r()
    allow = data.n(368, 0)
    surf, depth = data.n(203), data.n(201)
    if depth >= 0:
        raise CycleError(_t("Tiefe Q201 muss negativ sein"))
    bottom = surf + depth + data.n(369, 0)
    safe = surf + p.n(200, 2)
    clear = max(data.n(260, safe), safe)
    k = max(p.n(370, 0.4), 0.04) * R
    climb = p.n(351, 1) >= 0
    if open_bnd:
        plans = ad.plan_open(reg, R, allow, k, climb)
        for pl in plans:
            pl["open"] = True
    else:
        allowed = offset(reg, R + allow)
        if not allowed:
            raise CycleError(_t("Werkzeug zu groß für die Kontur"))
        rh_max = 0.95 * R if tool.angle else 0.0
        plans = ad.plan(allowed, R, k, climb, rh_max)
    if not plans:
        raise CycleError(_t("Werkzeug zu groß für die Kontur"))
    f_mill = p.f(207)
    f_plunge = _num_feed(f_mill, p.n(568, 0.5))
    f_pre = p.f(253) if p.n(253, 0) < 99999 else None
    s = p.n(576, 0)
    s_plunge = s * p.n(579, 1.0) if s else 0
    if s:
        e.raw(f"S{fmt(s)}")
    if not tool.angle and not open_bnd:
        e.warn.append(_t("Eintauchwinkel ANGLE fehlt in der Werkzeugtabelle – Werkzeug taucht senkrecht ein"))
    lift = 0.2
    ra = max(0.2 * R, 0.5)  # Radius der Aus-/Einfahr- und Verbindungsbögen
    e.rapid_z(clear)
    prev_z = surf
    for zi, z in enumerate(_levels(surf, bottom, p.n(202))):
        for pl in plans:
            c, rh = pl["center"], pl["rh"]
            top = prev_z + 0.5 if zi else min(safe, surf + 1.0)
            if s_plunge and s_plunge != s:
                e.raw(f"S{fmt(s_plunge)}")
            if pl.get("open"):
                cleared = pl["cleared0"]
                e.rapid_z(safe)
                e.cur = None  # erstes Stück: neben dem Material eintauchen
            elif rh > 0:
                a0 = _helix_start_angle(tool, rh, top, z, climb, 0.0)
                e.rapid_xy(c[0] + rh * math.cos(a0), c[1] + rh * math.sin(a0))
                e.rapid_z(safe)
                e.feed_z(top, f_pre or f_plunge)
                _helix_in(e, tool, c[0], c[1], rh, top, z, f_plunge, climb, start_at=a0)
                cleared = ad.disc(c[0], c[1], rh + R, 96)
            else:
                e.rapid_xy(*c)
                e.rapid_z(safe)
                e.feed_z(top, f_pre or f_plunge)
                e.feed_z(z, f_plunge)
                cleared = ad.disc(c[0], c[1], R, 96)
            if s_plunge and s_plunge != s:
                e.raw(f"S{fmt(s)}")
            cleared = ad.union(cleared, pl["outside"])
            last_h = None
            if pl["spiral"]:
                for i, pt in enumerate(pl["spiral"][1:]):
                    e.feed_xy(*pt, f_mill if i == 0 else None)
                sp = pl["spiral"]
                last_h = (sp[-1][0] - sp[-2][0], sp[-1][1] - sp[-2][1])
                cleared = ad.union(cleared, ad.buffer_open([pl["spiral"]], R))
            allowed_l = offset(pl["comp"], -0.01)
            for seg in pl["segments"]:
                core = offset(cleared, R - ad.TOL_MAT)
                core_l = ad.intersect(core, allowed_l)  # Verbindungen: geräumt und innerhalb der Wand
                start = seg.pts[0]
                entry = None
                if seg.closed and not inside(core_l, start):
                    # geschlossene Bahn ganz im Material: von innen (geräumte Seite) anfahren
                    a, b = seg.pts[0], seg.pts[1]
                    tx, ty = b[0] - a[0], b[1] - a[1]
                    ln = math.hypot(tx, ty) or 1.0
                    nx, ny = (-ty / ln, tx / ln) if climb else (ty / ln, -tx / ln)
                    entry = (a[0] + nx * k, a[1] + ny * k)
                tgt = entry or start
                h_in = ((start[0] - tgt[0], start[1] - tgt[1]) if entry else
                        (seg.pts[1][0] - start[0], seg.pts[1][1] - start[1]))
                cur = e.cur
                link = (ad.smooth_link(core_l, cur, last_h, tgt, h_in, ra, c, allowed_l)
                        if cur is not None and last_h is not None else None)
                if link is None and cur is not None:
                    via = ad.free_link(core_l, cur, tgt, c)
                    link = [ad.Prim("L", a, b) for a, b in zip([cur] + via[:-1], via)] if via else None
                if link is not None:
                    _emit_link(e, link, z, lift, f_mill)
                elif not inside(core_l, tgt):
                    # Startpunkt liegt im Material: neben ihm in geräumter Fläche eintauchen,
                    # dann von der geräumten Seite seitlich anfahren
                    hn = math.hypot(*h_in) or 1.0
                    n_in = (-h_in[1] / hn, h_in[0] / hn) if climb else (h_in[1] / hn, -h_in[0] / hn)
                    ent = None
                    for dd in (k, 1.5 * k, 2 * k, 3 * k, 4 * k, 6 * k):
                        for back in (0.0, 1.0, 2.0):  # etwas zurück entlang der Bahn: tangential einlaufen
                            cand = (tgt[0] + n_in[0] * dd - h_in[0] / hn * back * dd,
                                    tgt[1] + n_in[1] * dd - h_in[1] / hn * back * dd)
                            if not inside(core_l, cand):
                                continue
                            hc = (tgt[0] - cand[0], tgt[1] - cand[1])
                            for prims in ad.dubins(cand, hc, tgt, h_in, ra):
                                if ad.prims_free(core_l, prims, skip_end=k + 0.5, allowed=allowed_l):
                                    ent = (cand, prims)
                                    break
                            if ent:
                                break
                        if ent:
                            break
                    e.rapid_z(safe)
                    if ent is not None:
                        e.rapid_xy(*ent[0])
                        e.rapid_z(min(safe, z + 1.0))
                        e.feed_z(z, f_plunge)
                        _emit_link(e, ent[1], z, 0.0, f_mill, rise=False, fall=False)
                    else:  # kein geräumter Platz in der Nähe: langsam senkrecht eintauchen
                        e.rapid_xy(*tgt)
                        e.rapid_z(min(safe, top))
                        e.feed_z(z, f_plunge)
                else:
                    lead = ad.lead_arc(core_l, tgt, h_in, ra, climb, into=True, allowed=allowed_l)
                    hn = math.hypot(*h_in) or 1.0
                    back = (tgt[0] - 2.0 * h_in[0] / hn, tgt[1] - 2.0 * h_in[1] / hn)
                    ramp = not lead and inside(core_l, back)
                    e.rapid_z(safe)
                    e.rapid_xy(*(lead[0].p0 if lead else back if ramp else tgt))
                    e.rapid_z(min(safe, z + 1.0))
                    if lead:  # weich auf Tiefe einfahren
                        e.feed_z(z + lift, f_plunge)
                        _emit_link(e, lead, z, lift, f_mill, rise=False)
                    elif ramp:  # schräg in Fahrtrichtung auf Tiefe
                        e.feed_xy(*tgt, f_plunge, z=z)
                    else:
                        e.feed_z(z, f_plunge)
                if entry:
                    e.feed_xy(*start, f_mill)
                for i, pt in enumerate(seg.pts[1:]):
                    e.feed_xy(*pt, f_mill if i == 0 else None)
                last_h = (seg.pts[-1][0] - seg.pts[-2][0], seg.pts[-1][1] - seg.pts[-2][1])
                cleared = ad.union(cleared, ad.buffer_open([seg.pts], R))
            # tangential ausfahren und dabei abheben
            out = (ad.lead_arc(ad.intersect(offset(cleared, R - ad.TOL_MAT), offset(pl["comp"], -0.01)), e.cur, last_h, ra, climb, into=False)
                   if e.cur is not None and last_h is not None else None)
            if out:
                _emit_link(e, out, z, lift, f_mill, fall=False)
            else:
                e.feed_z(z + lift, f_mill)
            e.rapid_z(safe)
        prev_z = z
    e.rapid_z(clear)


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
        s += q.length
        zz = zat(s)
        if q.kind == "L" or math.dist(q.p0, q.p1) < 1e-3:
            # sehr kurzer Bogen: als Gerade – gleiche Endpunkte im G-Code wären sonst ein Vollkreis
            e.feed_xy(q.p1[0], q.p1[1], f if i == 0 else None, z=zz)
        else:
            e.arc(q.p1[0], q.p1[1], q.c[0], q.c[1], q.sweep > 0, f if i == 0 else None, z=zz)


def rough_272(e: Emit, reg, tool: Tool, p: P, data: P, open_bnd: bool):
    return adaptive_272(e, reg, tool, p, data, open_bnd)


def floor_273(e: Emit, reg, tool: Tool, p: P, data: P, open_bnd=False):
    R = tool.r()
    surf, depth = data.n(203), data.n(201)
    bottom = surf + depth
    safe = surf + p.n(200, 2)
    clear = max(data.n(260, safe), safe)
    k = max(p.n(370, 1.0), 0.04) * R
    if open_bnd:
        # offene Begrenzung: außerhalb der Begrenzung ist Luft – die Werkzeugmitte darf bis R − 0,2 über die
        # Kante hinaus, nur die Inseln halten R + Aufmaß (sonst bleibt am Rand und in schmalen Stegen zwischen
        # Kante und Insel Boden stehen)
        from . import adaptive as ad
        outer, holes = [], []
        for comp in ad.components(reg):
            outer.append(comp[0])
            holes += [list(reversed(h)) for h in comp[1:]]
        centers = offset(outer, -(R - 0.2))
        if holes:
            centers = ad.difference(centers, offset(holes, -(R + data.n(368, 0))))
        levels = loops_for(centers, 0.0, k, ccw_pocket=True)
    else:
        levels = loops_for(reg, R + data.n(368, 0), k, ccw_pocket=True)
    if not levels:
        raise CycleError(_t("Werkzeug zu groß für die Kontur"))
    allowed = levels[0][2]
    rings = [poly for _, polys, _ in reversed(levels) for poly in polys]
    f = p.f(385)
    f_plunge = _num_feed(f, p.n(568, 0.3))
    e.rapid_z(clear)
    cur = None
    for ring in rings:
        ring = _rotate_to_nearest(ring, cur)
        if cur is None or not _segment_inside(allowed, cur, ring[0]):
            if cur is not None:
                e.rapid_z(safe)
            e.rapid_xy(*ring[0])
            e.rapid_z(safe)
            e.feed_z(bottom + data.n(369, 0) + 0.2, p.f(253) if p.n(253, 0) < 99999 else f_plunge)
            e.feed_z(bottom, f_plunge)
        else:
            e.feed_xy(*ring[0], f)
        for i, pt in enumerate(ring[1:]):
            e.feed_xy(*pt, f if i == 0 else None)
        cur = ring[-1]
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


def ocm_cycle(num: int, p: P, data: P, reg, tool: Tool, e: Emit, open_bnd: bool):
    e.rel = False
    if num == 272:
        rough_272(e, reg, tool, p, data, open_bnd)
    elif num == 273:
        floor_273(e, reg, tool, p, data, open_bnd)
    elif num == 274:
        side_274(e, reg, tool, p, data)
    elif num == 277:
        chamfer_277(e, reg, tool, p, data)
    else:
        raise CycleError(_t('Konturtaschen-Zyklus {0} nicht vorgesehen').format(num))
    if p.n(438, -1) > 0:
        e.warn.append(_t("Q438 Ausräumwerkzeug (Restmaterial) wird noch nicht ausgewertet"))
